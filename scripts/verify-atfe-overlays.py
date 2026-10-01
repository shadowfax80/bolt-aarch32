#!/usr/bin/env python3
"""Replay ATFE file-slice patches from a pinned base without changing live source.

Export only patch-touched base files, apply the complete series in a fresh Git
directory, and compare every result with the live tree. Reject additional source
changes. This proves source contents, not a clean full build or binary provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

PIN = 'bcc08884995ff3cbee70749524621803b9bd258a'
METADATA = {'.applied-overlay-patches', '.overlay-source-ok'}


def git(directory, *args):
    process = subprocess.run(['git', '-C', str(directory), *map(str, args)], capture_output=True)
    if process.returncode:
        raise ValueError(process.stderr.decode('utf-8', 'replace').strip())
    return process.stdout


def safe_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or '.git' in path.parts or ':' in value:
        raise ValueError('unsafe overlay path: ' + value)
    return value


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files(source, paths):
    result = {}
    for name in sorted(paths):
        path = source / name
        if not path.resolve().is_relative_to(source) or path.is_symlink():
            raise ValueError('source path is not a regular in-tree file: ' + name)
        if path.exists() and not path.is_file():
            raise ValueError('source path is not a file: ' + name)
        result[name] = digest(path) if path.exists() else None
    return result


def changes(source, base):
    tracked = {safe_path(p.decode()) for p in git(source, 'diff', '--name-only', '-z', base, '--').split(b'\0') if p}
    untracked = {safe_path(p.decode()) for p in git(source, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if p}
    return tracked | (untracked - METADATA)


def replay(source, base, patch_dir, out):
    source, patch_dir, out = source.resolve(), patch_dir.resolve(), out.resolve()
    if out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError('replay output must be separate from the live source tree')
    if out.exists():
        raise ValueError('replay output already exists; preserve it and use a fresh directory')
    base = git(source, 'rev-parse', '--verify', base + '^{commit}').decode().strip()
    head = git(source, 'rev-parse', 'HEAD').decode().strip()
    patches = sorted(patch_dir.glob('*.patch'))
    if not patches:
        raise ValueError('ATFE patch series is empty')
    hashes = {p.name: digest(p) for p in patches}
    paths = set()
    for patch in patches:
        for row in git(source, 'apply', '--numstat', '-z', patch).split(b'\0'):
            if not row:
                continue
            fields = row.split(b'\t', 2)
            if len(fields) != 3:
                raise ValueError('unsupported rename/binary patch path format')
            paths.add(safe_path(fields[2].decode()))
    if not paths:
        raise ValueError('overlay series changes no files')
    changed = changes(source, base)
    uncovered = sorted(changed - paths)
    before = source_files(source, paths | changed)
    out.mkdir(parents=True)
    scratch = out / 'replayed-source'
    scratch.mkdir()
    git(scratch, 'init', '-q')
    git(scratch, 'config', 'core.autocrlf', 'false')
    entries = git(source, 'ls-tree', '-r', '-z', base, '--', *sorted(paths))
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        description, raw_name = entry.split(b'\t', 1)
        mode, kind, object_id = description.decode().split()
        name = safe_path(raw_name.decode())
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('unsupported base object: ' + name)
        path = scratch / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git(source, 'cat-file', 'blob', object_id))
        os.chmod(path, 0o755 if mode == '100755' else 0o644)
    for index, patch in enumerate(patches, 1):
        git(scratch, 'apply', '--check', patch)
        git(scratch, 'apply', patch)
        (out / f'{index:04d}-applied.txt').write_text(patch.name + '\n' + hashes[patch.name] + '\n')
    expected = source_files(scratch, paths)
    after = source_files(source, paths | changed)
    if before != after or changed != changes(source, base) or head != git(source, 'rev-parse', 'HEAD').decode().strip():
        raise ValueError('live source changed during replay; no result certified')
    if hashes != {p.name: digest(p) for p in sorted(patch_dir.glob('*.patch'))}:
        raise ValueError('overlay series changed during replay; no result certified')
    mismatches = [name for name in sorted(paths) if expected[name] != after[name]]
    identity = dict(base_commit=base, patch_sha256=hashes, source_files=expected)
    result = dict(schema=1, success=not uncovered and not mismatches, live_source_preserved=True,
                  live_head=head, **identity, uncovered_source_changes=uncovered, mismatched_source_files=mismatches,
                  source_identity_sha256=hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
                  scope='pinned base plus complete patch series; source contents only, not clean full build/binary provenance')
    (out / 'replay.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--base', default=PIN)
    parser.add_argument('--patch-dir', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = replay(args.source, args.base, args.patch_dir, args.out)
    print(json.dumps({k: v for k, v in result.items() if k not in ('patch_sha256', 'source_files')}, indent=2))
    print(args.out / 'replay.json')
    return 0 if result['success'] else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit(f'error: overlay replay failed: {error}')
