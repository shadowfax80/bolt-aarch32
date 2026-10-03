"""Fail-closed ARM counter artifact binding. Manifests detect mixing, not forgery."""
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys

from profile_identity import elf_metadata, sha256, read_json


def converter():
    name = '_bound_counter_converter'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name('ram-dump-to-fdata.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def note(blob, section, vendor, kind):
    data = blob[section['offset']:section['offset'] + section['size']]
    if section['kind'] != 7 or len(data) < 12:
        raise ValueError('invalid instrumentation note')
    ns, ds, tag = struct.unpack_from('<III', data)
    start = 12 + (ns + 3) // 4 * 4
    if (tag != kind or data[12:12 + ns] != vendor + b'\0'
            or start + ds > len(data) or any(data[start + ds:])):
        raise ValueError('invalid instrumentation note framing')
    return data[start:start + ds]


def inspect(original, instrumented, mapping):
    source_sections, source_symbols = elf_metadata(Path(original).read_bytes())
    blob = Path(instrumented).read_bytes()
    sections, symbols = elf_metadata(blob)
    def section(name):
        hits = [s for s in sections if s['name'] == name]
        if len(hits) != 1:
            raise ValueError('missing/ambiguous section: ' + name)
        return hits[0]
    def unique(name, candidates):
        base = re.sub(r'/[0-9]+$', '', name)
        hits = [s for s in candidates if s['kind'] == 2 and s['name'] == name]
        if not hits and base != name:
            hits = [s for s in candidates if s['kind'] == 2 and s['name'] == base]
        if len(hits) != 1:
            raise ValueError('ambiguous/missing source function: ' + name)
        return hits[0]
    if note(blob, section('.bolt.arm.source'), b'BOLTARM', 0x41524d02).hex() != sha256(original):
        raise ValueError('original ELF differs from the exact BOLT input digest')
    maps = {}
    for line in Path(mapping).read_text(encoding='utf-8').splitlines():
        fields = line.split()
        if len(fields) != 4 or fields[0] in maps:
            raise ValueError('invalid/duplicate function map row')
        name = fields[0]
        old, new, size = (int(x, 16) for x in fields[1:])
        src, dst = unique(name, source_symbols), unique(name, symbols)
        if old != src['address'] or new != dst['address'] or size != dst['size'] or src['thumb'] != dst['thumb']:
            raise ValueError('function map disagrees with exact ELFs: ' + name)
        maps[name] = dict(source=src, emitted=dst)
    if not maps:
        raise ValueError('empty function map')
    raw = note(blob, section('.bolt.arm.profile'), b'BOLTARM', 0x41524d01)
    if len(raw) < 8 or raw[:4] != b'BAP1':
        raise ValueError('missing explicit descriptor owner identity')
    count = struct.unpack_from('<I', raw, 4)[0]
    owners, pos = [], 8
    if count > (len(raw) - 8) // 22:
        raise ValueError('truncated descriptor owners')
    for _ in range(count):
        if pos + 21 > len(raw):
            raise ValueError('truncated descriptor owner')
        address, size, thumb, length = struct.unpack_from('<QQBI', raw, pos)
        pos += 21
        if not length or pos + length > len(raw) or thumb not in (0, 1):
            raise ValueError('invalid descriptor owner name/ISA')
        name = raw[pos:pos + length].decode('utf-8'); pos += length
        if any(c.isspace() for c in name) or name not in maps:
            raise ValueError('descriptor owner is absent from exact map')
        src = maps[name]['source']
        if (address, size, bool(thumb)) != (src['address'], src['size'], src['thumb']):
            raise ValueError('descriptor owner disagrees with original ELF')
        owners.append(dict(name=name, **{k: src[k] for k in ('address', 'size', 'thumb')}))
    if pos != len(raw) or len({o['name'] for o in owners}) != len(owners):
        raise ValueError('trailing/duplicate descriptor owners')
    counters = section('.bolt.instr.counters')
    def word(address):
        hits = [s for s in sections if s['kind'] != 8 and s['address'] <= address and address + 4 <= s['address'] + s['size']]
        if len(hits) != 1:
            raise ValueError('getter address is not uniquely file backed')
        s = hits[0]
        return struct.unpack_from('<I', blob, s['offset'] + address - s['address'])[0]
    def getter(name):
        sym = unique(name, symbols)
        a, b = word(sym['address']), word(sym['address'] + 4)
        if (a & 0xfff0f000 != 0xe3000000 or b & 0xfff0f000 != 0xe3400000
                or word(sym['address'] + 8) != 0xe5900000 or word(sym['address'] + 12) != 0xe12fff1e):
            raise ValueError('unsupported ARM counter getter')
        imm = lambda x: ((x >> 4) & 0xf000) | (x & 0xfff)
        return imm(a) | imm(b) << 16
    locations, number = getter('__bolt_instr_locations_getter'), getter('__bolt_num_counters_getter')
    num = word(number)
    if (not num or locations % 8 or locations < counters['address']
            or locations + num * 8 > counters['address'] + counters['size']
            or number < counters['address'] or number + 4 > counters['address'] + counters['size']
            or not (number + 4 <= locations or locations + num * 8 <= number)):
        raise ValueError('counter array/count do not fit their exact section')
    if word(getter('__bolt_instr_num_funcs_getter')) != len(owners):
        raise ValueError('function count disagrees with descriptor owners')
    tables = section('.bolt.instr.tables')
    table_data = note(blob, tables, b'BOLT', 2)
    if len(table_data) < 12 or struct.unpack_from('<II', table_data) != (0, 0):
        raise ValueError('indirect call metadata is unsupported for verified ARM counters')
    mod = converter()
    ctx = mod.parse_tables_note(blob, tables['offset'], tables['size'])
    funcs, offset = [], 0
    while offset < len(ctx.func_descriptions):
        f, end = mod.FunctionDescription.parse(ctx.func_descriptions, offset)
        if end <= offset or end > len(ctx.func_descriptions):
            raise ValueError('truncated function descriptor')
        funcs.append(f); offset = end
    if len(funcs) != len(owners):
        raise ValueError('descriptor/owner count mismatch')
    seen = set()
    for f, owner in zip(funcs, owners):
        if f.num_calls or f.num_entry_nodes:
            raise ValueError('call-profiling metadata is unsupported for verified ARM counters')
        for e in f.edges:
            for loc in (e.from_loc, e.to_loc):
                name = mod.serialize_loc(ctx.strings, loc).split()[1]
                if name != owner['name'] or not 0 <= loc.offset < owner['size']:
                    raise ValueError('counter location is outside its exact source owner')
        mod.validate_function(ctx, f, [0] * num, owner_name=owner['name'])
        refs = [n.counter for n in f.leaf_nodes] + [e.counter for e in f.edges if e.counter != mod.INFERRED]
        if len(set(refs)) != len(refs) or seen.intersection(refs):
            raise ValueError('duplicate counter ownership')
        seen.update(refs)
    if seen != set(range(num)):
        raise ValueError('incomplete exact counter coverage')
    layout = dict(address=counters['address'], size=counters['size'], locations=locations, count_address=number, count=num)
    return dict(owners=owners, function_map=maps, counter_layout=layout), ctx, funcs


def source_identity(replay, patch_dir):
    report = read_json(replay)
    patches = {p.name: sha256(p) for p in sorted(Path(patch_dir).glob('*.patch'))}
    identity = {k: report[k] for k in ('base_commit', 'patch_sha256', 'source_files')}
    import hashlib
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if (not patches or not report.get('success') or not report.get('live_source_preserved')
            or report.get('uncovered_source_changes') or report.get('mismatched_source_files')
            or patches != report['patch_sha256'] or digest != report['source_identity_sha256']):
        raise ValueError('ambiguous/stale source replay or patch identity')
    return digest, patches


def seal(original, elf, mapping, image, toolchain, patch_dir, replay):
    from profile_identity import check_load_image
    check_load_image(elf, image)
    metadata, _, _ = inspect(original, elf, mapping)
    source, patches = source_identity(replay, patch_dir)
    paths = dict(original=original, elf=elf, mapping=mapping, image=image, replay=replay)
    return dict(schema=1, kind='arm-counter-build', verified_binding=True,
                artifacts={k: sha256(v) for k, v in paths.items()}, metadata=metadata,
                source_identity_sha256=source, patches=patches,
                tools={n: sha256(Path(toolchain) / n) for n in ('llvm-bolt', 'llvm-readelf', 'llvm-nm', 'llvm-objdump', 'llvm-objcopy')})


def check_build(build, original, elf, mapping, image, toolchain, patch_dir, replay):
    if build != seal(original, elf, mapping, image, toolchain, patch_dir, replay):
        raise ValueError('counter build artifacts/tools/source differ from pre-capture seal')


def check_capture(path, dump, original, elf, mapping, toolchain, patch_dir, replay):
    capture = read_json(path)
    build = capture['build']
    if (capture.get('kind') != 'arm-counter-capture' or capture.get('verified_binding') is not True
            or capture['payload_sha256'] != sha256(dump)
            or build.get('schema') != 1 or build.get('kind') != 'arm-counter-build' or build.get('verified_binding') is not True
            or set(build.get('tools', {})) != {'llvm-bolt', 'llvm-readelf', 'llvm-nm', 'llvm-objdump', 'llvm-objcopy'}
            or set(build.get('artifacts', {})) != {'original', 'elf', 'mapping', 'image', 'replay'}):
        raise ValueError('counter capture is unbound or stale')
    for name, path in [('original', original), ('elf', elf), ('mapping', mapping), ('replay', replay)]:
        if build['artifacts'][name] != sha256(path):
            raise ValueError('counter capture artifact mismatch: ' + name)
    source, patches = source_identity(replay, patch_dir)
    if source != build['source_identity_sha256'] or patches != build['patches']:
        raise ValueError('counter capture source/patch mismatch')
    for name, digest in build['tools'].items():
        if sha256(Path(toolchain) / name) != digest:
            raise ValueError('counter capture tool mismatch: ' + name)
    metadata, ctx, funcs = inspect(original, elf, mapping)
    if metadata != build['metadata']:
        raise ValueError('counter capture metadata disagrees with exact ELFs/map')
    layout = metadata['counter_layout']; data = Path(dump).read_bytes()
    if (len(data) != layout['size'] or capture['range'] != {k: layout[k] for k in ('address', 'size')}
            or struct.unpack_from('<I', data, layout['count_address'] - layout['address'])[0] != layout['count']):
        raise ValueError('counter capture extent/count mismatch')
    return capture, ctx, funcs
