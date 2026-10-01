#!/usr/bin/env python3
"""Portable identity checks for Pi sampling builds, captures and BOLT profiles.

Hashes detect accidental stale/mixed artifacts; manifests are not signatures.
Only seal an image before collecting it, never retrospectively certify a dump.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise ValueError('unsupported identity manifest')
    return value


def write_json(path, value):
    destination = Path(path).resolve()
    staged = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent, delete=False) as stream:
            staged = stream.name
            json.dump(value, stream, indent=2)
            stream.write('\n')
        os.replace(staged, destination)
    finally:
        if staged and os.path.exists(staged):
            os.unlink(staged)


def elf_metadata(blob):
    """Read bounded ARM ELF32 section and symbol tables without host LLVM tools."""
    if (len(blob) < 52 or blob[:7] != b'\x7fELF\x01\x01\x01'
            or struct.unpack_from('<HH', blob, 16) != (2, 40)):
        raise ValueError('expected a static little-endian ARM ELF32 executable')
    phoff, shoff = struct.unpack_from('<II', blob, 28)
    phsize, phnum, shsize, shnum, names_index = struct.unpack_from('<HHHHH', blob, 42)
    if (phsize != 32 or shsize != 40 or not phnum or not shnum or names_index >= shnum
            or phoff + phsize * phnum > len(blob) or shoff + shsize * shnum > len(blob)):
        raise ValueError('malformed ELF header tables')
    loads = [struct.unpack_from('<8I', blob, phoff + i * phsize) for i in range(phnum)]
    loads = [p for p in loads if p[0] == 1]
    headers = [struct.unpack_from('<10I', blob, shoff + i * shsize) for i in range(shnum)]

    def data(header):
        off, size = header[4:6]
        if off + size > len(blob):
            raise ValueError('truncated ELF section')
        return blob[off:off + size]

    def string(table, offset):
        end = table.find(b'\0', offset)
        if not 0 <= offset < len(table) or end < 0:
            raise ValueError('invalid ELF string')
        return table[offset:end].decode('utf-8')

    names = data(headers[names_index])
    sections = []
    for header in headers:
        n, kind, flags, address, offset, size, *_ = header
        section = dict(name=string(names, n), kind=kind, flags=flags, address=address, offset=offset, size=size)
        if flags & 2 and kind != 8 and size:
            data(header)
            matches = [p for p in loads if p[2] <= address and address + size <= p[2] + p[4]
                       and p[1] + address - p[2] == offset]
            if len(matches) != 1:
                raise ValueError('allocated ELF section has no unique file-backed LOAD')
            section['physical'] = matches[0][3] + address - matches[0][2]
        sections.append(section)
    symbols = []
    for header in headers:
        if header[1] != 2:
            continue
        if header[9] != 16 or header[5] % 16 or header[6] >= len(headers):
            raise ValueError('malformed ELF symbol table')
        strings = data(headers[header[6]])
        table = data(header)
        for off in range(0, header[5], 16):
            n, value, size, info, other, index = struct.unpack_from('<IIIBBH', table, off)
            if info & 15 not in (1, 2) or not index or index >= len(sections) or not size:
                continue
            address = value & ~1 if info & 15 == 2 else value
            section = sections[index]
            if not section['address'] <= address < address + size <= section['address'] + section['size']:
                raise ValueError('symbol is outside its ELF section')
            symbols.append(dict(name=string(strings, n), address=address, size=size,
                                thumb=bool(value & 1), kind=info & 15))
    return sections, symbols


def seal_samples(elf, image, toolchain, patch_dir):
    elf_blob, image_blob = Path(elf).read_bytes(), Path(image).read_bytes()
    sections, symbols = elf_metadata(elf_blob)
    loaded = [s for s in sections if 'physical' in s]
    if not loaded:
        raise ValueError('ELF has no uploaded sections')
    base = min(s['physical'] for s in loaded)
    end = max(s['physical'] + s['size'] for s in loaded)
    if len(image_blob) != end - base:
        raise ValueError('binary length does not match ELF load image')
    for s in loaded:
        off = s['physical'] - base
        if image_blob[off:off + s['size']] != elf_blob[s['offset']:s['offset'] + s['size']]:
            raise ValueError('uploaded binary differs from ELF section ' + s['name'])
    buffers = [s for s in symbols if s['name'] == 'bolt_sample_buf' and s['kind'] == 1]
    if len(buffers) != 1 or buffers[0]['size'] != 0x80000:
        raise ValueError('expected one 512 KiB bolt_sample_buf object')
    functions = [s for s in symbols if s['kind'] == 2]
    tools = {name: sha256(Path(toolchain) / name) for name in ('llvm-bolt', 'perf2bolt', 'llvm-objcopy')}
    patches = {p.name: sha256(p) for p in sorted(Path(patch_dir).glob('*.patch'))}
    if not patches:
        raise ValueError('ATFE patch digests are required')
    return dict(schema=1, kind='pi-sampling-build', elf_sha256=sha256(elf), binary_sha256=sha256(image),
                source_elf_sha256=sha256(elf), sample_buffer={k: buffers[0][k] for k in ('address', 'size')},
                functions=functions, tools=tools, patches=patches,
                scope='image identity only; PC sampling is not an exact edge-count profile')


def check_build(manifest, image, elf):
    if (manifest.get('kind') != 'pi-sampling-build' or manifest.get('schema') != 1
            or sha256(image) != manifest['binary_sha256'] or sha256(elf) != manifest['elf_sha256']
            or manifest['source_elf_sha256'] != manifest['elf_sha256']):
        raise ValueError('sampling image/ELF does not match its sealed build')
    sections, symbols = elf_metadata(Path(elf).read_bytes())
    buffers = [s for s in symbols if s['name'] == 'bolt_sample_buf' and s['kind'] == 1]
    if len(buffers) != 1 or {k: buffers[0][k] for k in ('address', 'size')} != manifest['sample_buffer']:
        raise ValueError('sample buffer does not match the ELF')
    if [s for s in symbols if s['kind'] == 2] != manifest['functions']:
        raise ValueError('function metadata does not match the ELF')


def check_capture(path, payload, elf, kind):
    capture = read_json(path)
    if (capture.get('kind') != kind or capture.get('verified_binding') is not True
            or capture['payload_sha256'] != sha256(payload)
            or capture['build']['elf_sha256'] != sha256(elf)):
        raise ValueError('capture payload/ELF does not match its identity manifest')
    if capture['build']['kind'] != 'pi-sampling-build' or kind != 'pi-pc-capture':
        raise ValueError('unsupported capture binding')
    if capture['build']['source_elf_sha256'] != sha256(elf):
        raise ValueError('PC profile source differs from captured ELF')
    _, symbols = elf_metadata(Path(elf).read_bytes())
    if [s for s in symbols if s['kind'] == 2] != capture['build']['functions']:
        raise ValueError('capture source function identities do not match ELF')
    return capture


def validate_sample_fdata(path, functions, selected=None):
    """perf2bolt no-LBR locations must identify real source function byte ranges."""
    by_name = {}
    for row in functions:
        by_name.setdefault(row['name'], []).append(row)
    if selected is not None:
        if not selected or len(set(selected)) != len(selected) or any(len(by_name.get(name, [])) != 1 for name in selected):
            raise ValueError('profile scope requires distinct, unambiguous source function names')
    lines = Path(path).read_text().splitlines()
    if not lines or lines[0] != 'no_lbr':
        raise ValueError('expected perf2bolt no-LBR profile')
    if not any(line.strip() for line in lines[1:]):
        raise ValueError('sample profile has no named source locations')
    kept = ['no_lbr']
    excluded = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 4 or fields[0] != '1':
            raise ValueError('unsupported sampled profile location')
        _, name, offset, count = fields
        offset_value, count_value = int(offset, 16), int(count)
        if offset_value < 0 or count_value <= 0:
            raise ValueError('invalid sampled profile offset/count')
        # BOLT disambiguates local symbols with /<number>. Accept only an
        # unambiguous source symbol; ambiguous duplicate locals need a map.
        local = re.fullmatch(r'(.+)/[0-9]+', name)
        if selected is not None and name not in selected and (not local or local[1] not in selected):
            excluded[name] = excluded.get(name, 0) + count_value
            continue
        candidates = by_name.get(name, []) or (by_name.get(local[1], []) if local else [])
        if len(candidates) != 1 or not 0 <= offset_value < candidates[0]['size']:
            raise ValueError('profile location is outside an unambiguous source function: ' + name)
        kept.append(line)
    if len(kept) == 1:
        raise ValueError('sample profile has no locations in the requested source scope')
    if selected is not None:
        Path(path).write_text('\n'.join(kept) + '\n')
    return dict(selected_functions=selected, excluded_profile_counts=excluded)


def check_profile(elf, profile, manifest_path=None):
    manifest = read_json(manifest_path or str(profile) + '.manifest.json')
    if (manifest.get('kind') != 'bolt-profile' or manifest.get('verified_binding') is not True
            or manifest['source_elf_sha256'] != sha256(elf) or manifest['profile_sha256'] != sha256(profile)):
        raise ValueError('profile is unbound or belongs to another image')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    seal = sub.add_parser('seal-samples')
    seal.add_argument('--elf', required=True)
    seal.add_argument('--image', required=True)
    seal.add_argument('--toolchain', required=True)
    seal.add_argument('--patch-dir', required=True)
    seal.add_argument('--out')
    check = sub.add_parser('check-profile')
    check.add_argument('--elf', required=True)
    check.add_argument('--profile', required=True)
    args = parser.parse_args()
    if args.command == 'seal-samples':
        write_json(args.out or args.image + '.manifest.json', seal_samples(args.elf, args.image, args.toolchain, args.patch_dir))
    else:
        check_profile(args.elf, args.profile)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, struct.error) as error:
        raise SystemExit(f'error: invalid artifact identity: {error}')
