"""T2/6d: the SMP checker and smp_verify.py must reject incomplete, misplaced
or wrong per-core results, and refuse unreviewed or mismatched inputs before
anything is uploaded to the Pi."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from bolt_bench_smp_check import CONC_SET, check  # noqa: E402
from qemu_bench_oracle import CONTRACTS, reference_results  # noqa: E402

EXPECTED = {k: (v if isinstance(v, str) else f'0x{v:08x}') for k, v in reference_results().items()}


def log(ncpu=4, reps=2, mutate=None):
    rows = [f'bolt_bench: smp cpus={ncpu} reps={reps} set={len(CONC_SET)}']
    for c in range(ncpu):
        rows.append(f'bolt_bench: smp seq cpu={c} on={c} begin')
        rows += [f'bolt_bench: {k} sink={v}' for k, v in EXPECTED.items()]
        rows.append(f'bolt_bench: smp seq cpu={c} on={c} end')
    for c in range(ncpu):
        rows.append(f'bolt_bench: smp conc cpu={c} on={c},{c}')
        rows += [f'bolt_bench: smp conc cpu={c} rep={r} {n} sink={EXPECTED[n]}'
                 for r in range(reps) for n in CONC_SET]
    rows.append('bolt_bench: smp done')
    text = '\n'.join(rows) + '\n'
    return mutate(text) if mutate else text


class SmpChecker(unittest.TestCase):
    def test_complete_run_passes(self):
        errors, summary = check(log(), 4)
        self.assertEqual(errors, [])
        self.assertEqual(summary['conc_results'], 4 * 2 * len(CONC_SET))

    def test_rejections(self):
        first = next(iter(EXPECTED))
        cases = {
            'too few cores': (log(ncpu=2), 4),
            'wrong core (seq)': (log(mutate=lambda t: t.replace('seq cpu=2 on=2 begin', 'seq cpu=2 on=0 begin')), 4),
            'wrong core (conc)': (log(mutate=lambda t: t.replace('conc cpu=3 on=3,3', 'conc cpu=3 on=3,1')), 4),
            'wrong sink': (log(mutate=lambda t: t.replace(f'{first} sink={EXPECTED[first]}', f'{first} sink=0xdeadbeef', 1)), 4),
            'wrong conc sink': (log(mutate=lambda t: t.replace(f'rep=1 hot_loop sink={EXPECTED["hot_loop"]}', 'rep=1 hot_loop sink=0x00000000', 1)), 4),
            'missing conc row': (log(mutate=lambda t: t.replace(f'bolt_bench: smp conc cpu=1 rep=0 switch sink={EXPECTED["switch"]}\n', '', 1)), 4),
            'duplicate conc row': (log(mutate=lambda t: t.replace('bolt_bench: smp done', f'bolt_bench: smp conc cpu=0 rep=0 switch sink={EXPECTED["switch"]}\nbolt_bench: smp done')), 4),
            'incomplete': (log(mutate=lambda t: t.replace('bolt_bench: smp done', '')), 4),
            'two runs': (log() + log(), 4),
            'missing seq core': (log(mutate=lambda t: t.replace('smp seq cpu=1 on=1 end', '')), 4),
        }
        for name, (text, min_cpus) in cases.items():
            with self.subTest(name):
                errors, _ = check(text, min_cpus)
                self.assertTrue(errors, name)


class SmpVerifyPreflight(unittest.TestCase):
    """smp_verify.py must refuse before any Pi access (no serial port here)."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='smp-preflight-'))
        (self.dir / 'baseline.bin').write_bytes(b'base')
        (self.dir / 'baseline_full.bin').write_bytes(b'cand')
        self.loader = self.dir / 'loader.img'
        self.loader.write_bytes(b'loader')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def manifest(self, input_sha, redirected, bins_ok=True):
        h = lambda b: hashlib.sha256(b).hexdigest()
        (self.dir / 'full_manifest.json').write_text(json.dumps(dict(
            input_sha256=input_sha, redirected=[dict(name=n, output=0x1000, output_size=16) for n in redirected],
            baseline_binary_sha256=h(b'base') if bins_ok else '0' * 64, binary_sha256=h(b'cand'))))

    def run_verify(self, required):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/pi4/smp_verify.py'), str(self.dir),
                               '--require-executed', required, '--fast-loader', str(self.loader),
                               '--port', 'NONE'], capture_output=True, text=True, timeout=60)

    def smp_hash(self):
        return next(h for h, c in CONTRACTS.items() if c.get('smp'))

    def test_unreviewed_input(self):
        self.manifest('0' * 64, ['bolt_bench_interwork'])
        p = self.run_verify('bolt_bench_interwork')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('no reviewed independent oracle contract', p.stdout + p.stderr)

    def test_contract_without_smp(self):
        plain = next(h for h, c in CONTRACTS.items() if c.get('platform') == 'pi4' and not c.get('smp'))
        self.manifest(plain, ['bolt_bench_interwork'])
        p = self.run_verify('bolt_bench_interwork')
        self.assertIn('does not cover the SMP harness', p.stdout + p.stderr)

    def test_required_must_cover_redirects(self):
        self.manifest(self.smp_hash(), ['bolt_bench_interwork', 'bolt_bench_spill_ret'])
        p = self.run_verify('bolt_bench_interwork')
        self.assertIn('covering every selected redirect', p.stdout + p.stderr)

    def test_required_must_run_on_every_core(self):
        self.manifest(self.smp_hash(), ['bolt_bench_memcpy'])
        p = self.run_verify('bolt_bench_memcpy')
        self.assertIn('not in the concurrent set', p.stdout + p.stderr)

    def test_images_must_match_manifest(self):
        self.manifest(self.smp_hash(), ['bolt_bench_interwork'], bins_ok=False)
        p = self.run_verify('bolt_bench_interwork')
        self.assertIn('do not match the build manifest', p.stdout + p.stderr)
        self.assertFalse(list(self.dir.glob('smp-verify-*')), 'no evidence directory before checks pass')


if __name__ == '__main__':
    unittest.main()
