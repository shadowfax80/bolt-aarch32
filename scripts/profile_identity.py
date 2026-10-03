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
import shutil


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


def publish_files(files):
    """Stage the whole bundle before replacing anything; roll back caught I/O errors.

    A process/power failure between replacements is not a transaction. Hash-bound
    consumers reject such mixed generations. Validation must precede this call.
    """
    destinations = [Path(p).resolve() for p in files]
    if len(set(destinations)) != len(destinations):
        raise ValueError('duplicate publication path')
    with tempfile.TemporaryDirectory(dir=destinations[0].parent) as directory:
        staged, previous, replaced = {}, {}, []
        for i, (path, data) in enumerate(zip(destinations, files.values())):
            stage = Path(directory) / (str(i) + '.new')
            stage.write_bytes(data)
            staged[path] = stage
            backup = Path(directory) / (str(i) + '.old')
            if path.exists():
                shutil.copyfile(path, backup)
                previous[path] = backup
            else:
                previous[path] = None
        try:
            for path in destinations:
                os.replace(staged[path], path)
                replaced.append(path)
        except BaseException:
            for path in reversed(replaced):
                if previous[path] is None:
                    path.unlink(missing_ok=True)
                else:
                    os.replace(previous[path], path)
            raise


def check_load_image(elf, image):
    elf_blob, image_blob = Path(elf).read_bytes(), Path(image).read_bytes()
    sections, _ = elf_metadata(elf_blob)
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
    _, symbols = elf_metadata(Path(elf).read_bytes())
    functions = [s for s in symbols if s['kind'] == 2]
    valid_digest = lambda value: isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
    if manifest.get('profile_type') == 'pc-samples':
        build = manifest.get('build', {})
        if (build.get('schema') != 1 or build.get('kind') != 'pi-sampling-build'
                or build.get('elf_sha256') != manifest['source_elf_sha256']
                or build.get('source_elf_sha256') != manifest['source_elf_sha256']
                or not valid_digest(build.get('binary_sha256'))
                or set(build.get('tools', {})) != {'llvm-bolt', 'perf2bolt', 'llvm-objcopy'}
                or not all(valid_digest(v) for v in build['tools'].values())
                or manifest.get('perf2bolt_sha256') != build['tools']['perf2bolt']
                or not build.get('patches') or not all(valid_digest(v) for v in build['patches'].values())
                or not valid_digest(manifest.get('capture_manifest_sha256'))):
            raise ValueError('incomplete sampling profile identity receipt')
        if manifest['build']['functions'] != functions:
            raise ValueError('profile source metadata disagrees with ELF')
        validate_sample_fdata(profile, functions)
    elif manifest.get('profile_type') == 'arm-counters':
        build = manifest.get('build', {})
        if (build.get('schema') != 1 or build.get('kind') != 'arm-counter-build' or build.get('verified_binding') is not True
                or build.get('artifacts', {}).get('original') != manifest['source_elf_sha256']
                or set(build.get('artifacts', {})) != {'original', 'elf', 'mapping', 'image', 'replay'}
                or not all(valid_digest(v) for v in build['artifacts'].values())
                or set(build.get('tools', {})) != {'llvm-bolt', 'llvm-readelf', 'llvm-nm', 'llvm-objdump', 'llvm-objcopy'}
                or not all(valid_digest(v) for v in build['tools'].values())
                or not build.get('patches') or not all(valid_digest(v) for v in build['patches'].values())
                or not valid_digest(build.get('source_identity_sha256'))
                or not valid_digest(manifest.get('capture_manifest_sha256'))):
            raise ValueError('incomplete counter profile identity receipt')
        owners = build.get('metadata', {}).get('owners', [])
        if not owners or len({o['name'] for o in owners}) != len(owners):
            raise ValueError('missing/duplicate counter profile owners')
        for owner in owners:
            base = re.sub(r'/[0-9]+$', '', owner['name'])
            hits = [f for f in functions if f['name'] == owner['name']]
            if not hits and base != owner['name']:
                hits = [f for f in functions if f['name'] == base]
            if len(hits) != 1 or any(owner[k] != hits[0][k] for k in ('address', 'size', 'thumb')):
                raise ValueError('counter profile owner disagrees with source ELF')
        owner_names = {o['name'] for o in owners}
        for line in Path(profile).read_text(encoding='utf-8').splitlines():
            fields = line.split()
            if len(fields) != 8 or any(fields[i] not in owner_names for i in (1, 4)):
                raise ValueError('counter profile references an unsealed owner')
        validate_counter_fdata(Path(profile).read_text(encoding='utf-8'), functions)
    else:
        raise ValueError('unsupported/missing verified profile type')
    return manifest


def validate_counter_fdata(text, functions):
    by_name = {}
    for f in functions:
        by_name.setdefault(f['name'], []).append(f)
    for line in text.splitlines():
        f = line.split()
        if len(f) != 8 or f[0] != '1' or f[3] != '1' or f[6] != '0' or not 0 < int(f[7]) < 1 << 64:
            raise ValueError('unsupported counter fdata record')
        for name, offset in [(f[1], f[2]), (f[4], f[5])]:
            base = re.sub(r'/[0-9]+$', '', name)
            candidates = by_name.get(name, []) or by_name.get(base, [])
            if len(candidates) != 1 or not 0 <= int(offset, 16) < candidates[0]['size']:
                raise ValueError('counter fdata location outside exact source function')
    if not text.strip():
        raise ValueError('counter profile has no measured locations')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    seal = sub.add_parser('seal-samples')
    seal.add_argument('--elf', required=True)
    seal.add_argument('--image', required=True)
    seal.add_argument('--toolchain', required=True)
    seal.add_argument('--patch-dir', required=True)
    seal.add_argument('--out')
    counters = sub.add_parser('seal-counters')
    for name in ('original', 'elf', 'map', 'image', 'toolchain', 'patch-dir', 'source-replay'):
        counters.add_argument('--' + name, required=True)
    counters.add_argument('--out')
    check = sub.add_parser('check-profile')
    check.add_argument('--elf', required=True)
    check.add_argument('--profile', required=True)
    args = parser.parse_args()
    if args.command == 'seal-samples':
        write_json(args.out or args.image + '.manifest.json', seal_samples(args.elf, args.image, args.toolchain, args.patch_dir))
    elif args.command == 'seal-counters':
        from counter_identity import seal as seal_counters
        write_json(args.out or args.image + '.manifest.json', seal_counters(
            args.original, args.elf, args.map, args.image, args.toolchain, args.patch_dir, args.source_replay))
    else:
        check_profile(args.elf, args.profile)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, struct.error) as error:
        raise SystemExit(f'error: invalid artifact identity: {error}')
