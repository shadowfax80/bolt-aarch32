"""K14: BOLT-safe masking-site capture. Applies to an LK tree that has lk-perf
overlays 0001-0015 (argument: LK tree root)."""
import sys
from pathlib import Path

LK = Path(sys.argv[1])
h = LK / 'arch/arm/include/arch/arch_interrupts.h'
s = h.read_text()
old_decl = 'void arm_irqmask_begin(uint32_t site);\n'
assert s.count(old_decl) == 1
s = s.replace(old_decl, old_decl + '''/* lk-perf K14: open a region at the caller's own location (its return
 * address). The inline `mov rX, pc` this replaces read the PC as data, which
 * makes every function that inlines arch_disable_ints() position-dependent:
 * BOLT (and any other code mover) has to refuse it. */
void arm_irqmask_begin_here(void);
''')
old_a = '''            if (arm_irqmask_on && opened) {
                uint32_t site;
                __asm__ volatile("mov %0, pc" : "=r"(site));
                arm_irqmask_begin(site);
            }'''
new_a = '''            if (arm_irqmask_on && opened)
                arm_irqmask_begin_here();'''
old_b = '''    if (arm_irqmask_on && opened) {
        uint32_t site;
        __asm__ volatile("mov %0, pc" : "=r"(site));
        arm_irqmask_begin(site);
    }'''
new_b = '''    if (arm_irqmask_on && opened)
        arm_irqmask_begin_here();'''
assert s.count(old_a) == 1 and s.count(old_b) == 1
s = s.replace(old_a, new_a).replace(old_b, new_b)
h.write_text(s)

c = LK / 'arch/arm/arm/irqmask.c'
t = c.read_text()
anchor = 'void arm_irqmask_begin(uint32_t site) {'
assert t.count(anchor) == 1
i = t.index(anchor)
j = t.index('\n}\n', i) + 3
t = t[:j] + '''
/* K14: the site is the instruction after the call, inside the function that
 * masked; bit 0 (Thumb) cleared, as the old PC read gave a plain address. */
__NO_INLINE void arm_irqmask_begin_here(void) {
    arm_irqmask_begin((uint32_t)(uintptr_t)__builtin_return_address(0) & ~1u);
}
''' + t[j:]
c.write_text(t)
print('ok')
