import pytest
from unittest.mock import MagicMock, patch
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts' / 'pi4'))

from build_thumb_startup import check_image, require, address_offset, trampoline

def setup_mocks(blob_len=200, raw_len=200):
    elf = MagicMock()
    raw = MagicMock()
    blob = bytearray(b'\x00' * blob_len)
    data = bytearray(b'\x00' * raw_len)
    elf.read_bytes.return_value = bytes(blob)
    raw.read_bytes.return_value = bytes(data)

    # Defaults
    sections = [
        {'name': '.text', 'physical': 0x8000, 'address': 0x8000, 'size': blob_len, 'offset': 0}
    ]
    symbols = []

    return elf, raw, blob, data, sections, symbols

def make_movw(val):
    imm4 = (val >> 12) & 0xf
    imm12 = val & 0xfff
    return 0xe300c000 | (imm4 << 16) | imm12

def make_movt(val):
    imm4 = (val >> 12) & 0xf
    imm12 = val & 0xfff
    return 0xe340c000 | (imm4 << 16) | imm12

def create_valid_blob(instrumented=False):
    # Fixed-load base is 0x8000, end is 0x80c8 (200 bytes).
    elf, raw, blob, data, sections, symbols = setup_mocks(200, 200)

    # Write ELF entry at offset 24
    entry_point = 0x8020
    struct.pack_into('<I', blob, 24, entry_point)

    # Let boot_pointer be at 0x8040
    boot_pointer = 0x8040
    struct.pack_into('<I', blob, boot_pointer - 0x8000, entry_point)

    if instrumented:
        trampoline_val = 0x8060
        tramp_a = make_movw(trampoline_val & 0xffff)
        tramp_b = make_movt(trampoline_val >> 16)
        tramp_c = 0xe12fff1c  # BX r12

        struct.pack_into('<III', blob, entry_point - 0x8000, tramp_a, tramp_b, tramp_c)

        thumb_entry_val = 0x8081
        tramp2_a = make_movw(thumb_entry_val & 0xffff)
        tramp2_b = make_movt(thumb_entry_val >> 16)
        tramp2_c = 0xe12fff1c  # BX r12

        struct.pack_into('<III', blob, trampoline_val - 0x8000, tramp2_a, tramp2_b, tramp2_c)

    # Sync data and blob
    elf.read_bytes.return_value = bytes(blob)
    raw.read_bytes.return_value = bytes(blob) # raw should match blob for loaded sections

    row = {
        'entry': entry_point,
        'boot_pointer': boot_pointer,
        'instrumented': instrumented,
    }

    if instrumented:
        row.update({
            'trampoline': trampoline_val,
            'thumb_entry': thumb_entry_val,
            'original_thumb_entry': 0x80a1, # Must be != thumb_entry and & 1 == 1
        })

    return elf, raw, row, blob, sections, symbols

@patch('build_thumb_startup.elf_metadata')
def test_check_image_happy_path(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob(instrumented=False)
    mock_elf_metadata.return_value = (sections, symbols)
    check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_happy_path_instrumented(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob(instrumented=True)
    mock_elf_metadata.return_value = (sections, symbols)
    check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_wrong_fixed_load_region(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob()
    sections[0]['physical'] = 0x9000
    mock_elf_metadata.return_value = (sections, symbols)
    with pytest.raises(ValueError, match='wrong fixed-load region'):
        check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_wrong_raw_image_size(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob()
    raw.read_bytes.return_value = bytes(b'\x00' * (sections[0]['size'] - 10))
    mock_elf_metadata.return_value = (sections, symbols)
    with pytest.raises(ValueError, match='wrong raw image size'):
        check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_fixture_requires_v_eq_p(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob()
    sections[0]['address'] = 0x9000
    mock_elf_metadata.return_value = (sections, symbols)
    with pytest.raises(ValueError, match='fixture requires V=P'):
        check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_elf_raw_mismatch(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob()
    data = bytearray(raw.read_bytes.return_value)
    data[0] = 0xff
    raw.read_bytes.return_value = bytes(data)
    mock_elf_metadata.return_value = (sections, symbols)
    with pytest.raises(ValueError, match='ELF/raw mismatch'):
        check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_elf_entry_changed(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob()
    row['entry'] = 0x1234
    mock_elf_metadata.return_value = (sections, symbols)
    with pytest.raises(ValueError, match='ELF entry changed'):
        check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_boot_shim_does_not_enter(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob()
    struct.pack_into('<I', blob, row['boot_pointer'] - 0x8000, 0x1234)
    elf.read_bytes.return_value = bytes(blob)
    raw.read_bytes.return_value = bytes(blob)
    mock_elf_metadata.return_value = (sections, symbols)
    with pytest.raises(ValueError, match='boot shim does not enter actual ELF entry'):
        check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_wrong_arm_runtime_entry_route(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob(instrumented=True)
    row['trampoline'] = 0x8090
    mock_elf_metadata.return_value = (sections, symbols)
    with pytest.raises(ValueError, match='wrong ARM runtime entry route'):
        check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_wrong_thumb_destination(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob(instrumented=True)
    row['thumb_entry'] = 0x8091
    mock_elf_metadata.return_value = (sections, symbols)
    with pytest.raises(ValueError, match='wrong Thumb destination/ISA bit'):
        check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_missing_thumb_bit(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob(instrumented=True)
    row['thumb_entry'] = 0x8080 # Even number, missing bit 0
    tramp2_a = make_movw(0x8080 & 0xffff)
    tramp2_b = make_movt(0x8080 >> 16)
    tramp2_c = 0xe12fff1c
    struct.pack_into('<III', blob, row['trampoline'] - 0x8000, tramp2_a, tramp2_b, tramp2_c)
    elf.read_bytes.return_value = bytes(blob)
    raw.read_bytes.return_value = bytes(blob)

    mock_elf_metadata.return_value = (sections, symbols)
    with pytest.raises(ValueError, match='missing Thumb bit'):
        check_image(elf, raw, row)

@patch('build_thumb_startup.elf_metadata')
def test_check_image_entry_not_rewritten(mock_elf_metadata):
    elf, raw, row, blob, sections, symbols = create_valid_blob(instrumented=True)
    row['original_thumb_entry'] = row['thumb_entry']
    mock_elf_metadata.return_value = (sections, symbols)
    with pytest.raises(ValueError, match='entry was not rewritten'):
        check_image(elf, raw, row)
