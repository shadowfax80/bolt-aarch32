"""Apply lk-perf's kernel overlays (not its Pi port) to the bolt-aarch32 LK
tree in ~/bolt-b1. gic_v2.c is merged by hand: bolt-aarch32's own sample hook
sits where lk-perf's goes, so both hooks are kept."""
import subprocess
from pathlib import Path

LK = Path('/home/user/bolt-b1/third_party/lk')
OV = Path('/home/user/lk-perf/overlay/lk')
PATCHES = ['0001', '0002', '0003', '0005', '0009', '0010', '0012', '0013', '0014', '0015']
GIC = 'dev/interrupt/arm_gic/gic_v2.c'

for n in PATCHES:
    p = next(OV.glob(f'{n}-*.patch'))
    r = subprocess.run(['git', 'apply', f'--exclude={GIC}', str(p)], cwd=LK,
                       capture_output=True, text=True)
    print(('ok   ' if r.returncode == 0 else 'FAIL ') + p.name, r.stderr.strip()[:300])
    if r.returncode:
        raise SystemExit(1)

g = LK / GIC
s = g.read_text()
old = '''__WEAK void bolt_sample_on_irq(struct iframe *frame, unsigned int vector) {}
'''
assert s.count(old) == 1
s = s.replace(old, old + '''
// lk-perf hook (lk-perf overlay 0001), kept beside bolt-aarch32's: the
// lk-perf profiler (app/profiler) overrides it.
__WEAK void profiler_on_tick(struct iframe *frame, unsigned int vector) {}

#if ARCH_arm
#include <arch/arch_interrupts.h>
#endif
''')
old = '''    bolt_sample_on_irq(frame, vector);
'''
assert s.count(old) == 1
s = s.replace(old, '''#ifdef ARM_IRQMASK_IRQ_SITE
    /* lk-perf: the handler runs masked; account it as an IRQ region */
    arm_irqmask_irq_enter(vector);
#endif
    bolt_sample_on_irq(frame, vector);
    profiler_on_tick(frame, vector);
''')
g.write_text(s)
print('gic_v2.c merged')
