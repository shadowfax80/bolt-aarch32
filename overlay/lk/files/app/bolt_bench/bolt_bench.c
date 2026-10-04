#include <app.h>
#include <arch/ops.h>
#include <arch/atomic.h>
#include <lib/cmdline.h>
#include <lib/console.h>
#include <lk/console_cmd.h>
#include <kernel/mp.h>
#include <kernel/thread.h>
#include <lk/debug.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BOLT_BENCH_ITERS 1000000u
#define BOLT_BENCH_MEMCPY_ROUNDS 512u
/* Real per-iteration function-call overhead (prologue/epilogue, and for
 * some of these an ARM<->Thumb mode switch) makes BOLT_BENCH_ITERS too
 * expensive under QEMU's software ARM emulation -- at 1M iterations these
 * ran 17-34M "cycles" each (bolt_bench_interwork_tail/icf/indirect_call/
 * regpressure), long enough that a profiling boot timed out before every
 * bolt_bench_* counter got a chance to increment. bolt_bench_interwork
 * and bolt_bench_spill_ret already used a smaller count (10k/100k) for
 * the same reason; this follows that precedent. */
#define BOLT_BENCH_ITERS_CALL 20000u

static uint8_t bench_src[4096] __attribute__((aligned(64)));
static uint8_t bench_dst[4096] __attribute__((aligned(64)));

/* (void)-casting a pure loop's accumulator does not stop the optimizer from
 * eliminating the loop entirely -- (void) silences the unused-variable
 * warning but proves nothing about observability to the compiler. A
 * volatile write is a real, unremovable side effect and is the only thing
 * here that reliably keeps a pure-arithmetic loop's body in the binary.
 * One sink per core (T2): `bolt_bench smp` runs workloads on every core at
 * once, and each core must see only its own result. The workload code is
 * unchanged; the name resolves to the current core's slot. */
static volatile uint32_t g_bolt_bench_sink_cpu[SMP_MAX_CPUS];
#define g_bolt_bench_sink (g_bolt_bench_sink_cpu[arch_curr_cpu_num()])

/* Timed regions run with interrupts masked for clean numbers -- except while `bolt_sample`
 * is on: the PC sampler is interrupt-driven (an IRQ on this non-secure Pi), so it would see
 * none of a masked region (measured: ~1/8 of the expected samples, all at its edges). A
 * profiling run does not need clean timing. */
static volatile uint32_t g_bolt_sampling;
static inline void bench_ints_off(void) {
    if (!g_bolt_sampling)
        arch_disable_ints();
}
static inline void bench_ints_on(void) {
    if (!g_bolt_sampling)
        arch_enable_ints();
}

/* Result check: each workload's final value, printed after it returns, so a
 * rewritten image can be compared with the original workload by workload. */
static void print_sink(const char *name) {
    printf("bolt_bench: %s sink=0x%08x\n", name, (unsigned)g_bolt_bench_sink);
}

/* Set while `bolt_bench smp` runs workloads concurrently: per-run banners
 * from four cores would interleave; results are printed after the join. */
static volatile int g_bench_quiet;

static void bench_banner(const char *name, lk_time_t cycles) {
    if (g_bench_quiet)
        return;
    printf("bolt_bench: %s done (%llu cycles)\n", name, (unsigned long long)cycles);
}

/* Cortex-A72 (Pi 4B) PMU event counters, read via PL1 CP15. The cycle counter
 * is already running (arch_cycle_count() reads PMCCNTR directly); this adds
 * four architectural events so a run shows *why* a layout/inlining change
 * moved cycles, not just that it did. What BOLT and LTO change is exactly
 * instruction-side behavior: L1I refills and branch mispredicts. */
#define BOLT_PMU_NCTR 5
/* Set 0: what changed. Set 1: more front-end / branch detail. `bolt_bench <wl> 1` selects
 * set 1; the workload is deterministic, so two passes give ten events.
 * Only events the Pi 4B's Cortex-A72 really counts are used (swept 160 events with
 * `bolt_bench pmu_probe`, 2026-09-30): it counts the speculative _SPEC events but NOT the
 * _RETIRED branch events (0x0C, 0x0D, 0x0E, 0x21, 0x22), STALL_FRONTEND/BACKEND (0x23/0x24)
 * or any TLB event -- those read 0. `taken` is therefore PC_WRITE_SPEC (speculatively
 * executed taken branches, calls and returns), and there is no front-end stall counter:
 * L1I refills and IPC stand in for it. */
static const uint32_t bolt_pmu_sets[2][BOLT_PMU_NCTR] = {
    {
        0x01, /* L1I_CACHE_REFILL */
        0x03, /* L1D_CACHE_REFILL */
        0x08, /* INST_RETIRED */
        0x10, /* BR_MIS_PRED */
        0x76, /* PC_WRITE_SPEC: taken branches, calls and returns (speculative) */
    },
    {
        0x14, /* L1I_CACHE (accesses) */
        0x12, /* BR_PRED (predictable branches speculatively executed) */
        0x1B, /* INST_SPEC (instructions speculatively executed) */
        0x79, /* BR_RETURN_SPEC */
        0x16, /* L2D_CACHE (accesses) */
    },
};
static uint32_t bolt_pmu_events[BOLT_PMU_NCTR];
static int g_pmu_set_req;
static int g_pmu_set_cur = -1;
/* Input variant for held-out-input tests (`bolt_bench <wl> <pmu set> <variant>`). Profiles
 * are always trained on variant 0; measuring variants 1 and 2 shows whether a PGO/BOLT gain
 * survives inputs the profile never saw. 1 = same distribution, new data (other seeds);
 * 2 = shifted distribution (different code is hot). Only stair and pgo_lab use it. */
static uint32_t g_input_variant;
/* Set 2: arbitrary events chosen at run time (`bolt_bench pmu_probe <hex> ...`), used to
 * find out which events this core really counts. */
static uint32_t g_pmu_custom[BOLT_PMU_NCTR];

struct bolt_pmu {
    uint32_t v[BOLT_PMU_NCTR];
};

static inline void bolt_pmu_select(uint32_t idx) {
    __asm__ volatile("mcr p15, 0, %0, c9, c12, 5" ::"r"(idx)); /* PMSELR */
    __asm__ volatile("isb" ::: "memory");
}

/* The PMU is banked per core, and the shell thread that runs a workload can be
 * on any core (WITH_SMP): arming only the core that ran the first command left
 * every later command on another core reading zeros while the cycle counter
 * (enabled per core by LK itself) kept counting. Arm all of them. */
static void bolt_pmu_init_this_cpu(void *unused) {
    for (uint32_t i = 0; i < BOLT_PMU_NCTR; i++) {
        bolt_pmu_select(i);
        __asm__ volatile("mcr p15, 0, %0, c9, c13, 1" ::"r"(bolt_pmu_events[i])); /* PMXEVTYPER */
    }
    /* enable event counters 0..4; keep bit 31 (the cycle counter) enabled */
    __asm__ volatile("mcr p15, 0, %0, c9, c12, 1" ::"r"(0x8000001fu)); /* PMCNTENSET */
    uint32_t pmcr;
    __asm__ volatile("mrc p15, 0, %0, c9, c12, 0" : "=r"(pmcr));
    pmcr |= (1u << 0) | (1u << 1); /* E: enable, P: reset event counters (not the cycle counter) */
    __asm__ volatile("mcr p15, 0, %0, c9, c12, 0" ::"r"(pmcr));
    __asm__ volatile("isb" ::: "memory");
}

static void bolt_pmu_init(void) {
    if (g_pmu_set_cur == g_pmu_set_req) {
        return;
    }
    g_pmu_set_cur = g_pmu_set_req;
    for (uint32_t i = 0; i < BOLT_PMU_NCTR; i++) {
        bolt_pmu_events[i] = (g_pmu_set_cur == 2) ? g_pmu_custom[i] : bolt_pmu_sets[g_pmu_set_cur][i];
    }
    mp_sync_exec(MP_IPI_TARGET_ALL, 0, bolt_pmu_init_this_cpu, NULL);
}

static void bolt_pmu_read(struct bolt_pmu *s) {
    for (uint32_t i = 0; i < BOLT_PMU_NCTR; i++) {
        uint32_t v;
        bolt_pmu_select(i);
        __asm__ volatile("mrc p15, 0, %0, c9, c13, 2" : "=r"(v)); /* PMXEVCNTR */
        s->v[i] = v;
    }
}

static void bolt_pmu_report(const char *name, const struct bolt_pmu *a, const struct bolt_pmu *b) {
    if (g_pmu_set_cur == 2) {
        printf("bolt_bench: %s pmuX", name);
        for (uint32_t i = 0; i < BOLT_PMU_NCTR; i++) {
            printf(" 0x%02x=%u", (unsigned)g_pmu_custom[i], (unsigned)(b->v[i] - a->v[i]));
        }
        printf("\n");
        return;
    }
    if (g_pmu_set_cur == 1) {
        printf("bolt_bench: %s pmu2 l1i_acc=%u br_pred=%u inst_spec=%u ret_spec=%u l2d_acc=%u\n", name,
               (unsigned)(b->v[0] - a->v[0]), (unsigned)(b->v[1] - a->v[1]), (unsigned)(b->v[2] - a->v[2]),
               (unsigned)(b->v[3] - a->v[3]), (unsigned)(b->v[4] - a->v[4]));
        return;
    }
    printf("bolt_bench: %s pmu inst=%u l1i_refill=%u l1d_refill=%u br_mispred=%u taken=%u\n", name,
           (unsigned)(b->v[2] - a->v[2]), (unsigned)(b->v[0] - a->v[0]),
           (unsigned)(b->v[1] - a->v[1]), (unsigned)(b->v[3] - a->v[3]),
           (unsigned)(b->v[4] - a->v[4]));
}

__attribute__((noinline)) void bolt_bench_hot_loop(void) {
    lk_time_t t0 = arch_cycle_count();
    uint64_t sum = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS; i++) {
        sum += i;
    }
    bench_banner("hot_loop", arch_cycle_count() - t0);
    g_bolt_bench_sink = (uint32_t)sum;
}

__attribute__((noinline)) void bolt_bench_hot_cold(void) {
    lk_time_t t0 = arch_cycle_count();
    uint64_t cold = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS; i++) {
        if ((i & 0xFFFFF) == 0xFFFFF) {
            cold += i;
        }
    }
    bench_banner("hot_cold", arch_cycle_count() - t0);
    g_bolt_bench_sink = (uint32_t)cold;
}

__attribute__((noinline)) void bolt_bench_branch_chain(void) {
    lk_time_t t0 = arch_cycle_count();
    uint32_t acc = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS; i++) {
        uint32_t x = i ^ (i >> 3);
        if (x & 1) acc++;
        if (x & 2) acc++;
        if (x & 4) acc++;
        if (x & 8) acc++;
        if (x & 16) acc++;
        if (x & 32) acc++;
        if (x & 64) acc++;
        if (x & 128) acc++;
        if (x & 256) acc++;
        if (x & 512) acc++;
        if (x & 1024) acc++;
        if (x & 2048) acc++;
        if (x & 4096) acc++;
        if (x & 8192) acc++;
        if (x & 16384) acc++;
        if (x & 32768) acc++;
    }
    bench_banner("branch_chain", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

__attribute__((noinline)) uint32_t bolt_bench_far_target(uint32_t value) {
    /* Callee for P5 far-call experiments (optional BOLT_BENCH_FAR_PAD). */
    __asm__ volatile("" : "+r"(value));
    return value ^ 0xa53c79d1u;
}

__attribute__((noinline)) void bolt_bench_far_call(void) {
    g_bolt_bench_sink = bolt_bench_far_target(0x12345678u);
    printf("bolt_bench: far_call done\n");
}

__attribute__((noinline)) void bolt_bench_it_cond(void) {
#if defined(__thumb__)
    /* P7: explicit Thumb-2 IT/ITE — must survive identity rewrite intact. */
    lk_time_t t0 = arch_cycle_count();
    uint32_t y = 0, z = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS; i++) {
        uint32_t v = i & 3u;
        __asm__ volatile(
            "cmp %[v], #0\n\t"
            "ite eq\n\t"
            "moveq %[y], #1\n\t"
            "movne %[y], #2\n\t"
            "cmp %[v], #1\n\t"
            "itt ne\n\t"
            "addne %[z], %[z], #1\n\t"
            "addne %[z], %[z], %[v]\n\t"
            : [y] "+l"(y), [z] "+l"(z)
            : [v] "l"(v)
            : "cc");
    }
    bench_banner("it_cond", arch_cycle_count() - t0);
    g_bolt_bench_sink = (y << 24) ^ z;
#else
    /* IT encoding is Thumb-only; ARM-mode P4 builds skip this workload. */
    printf("bolt_bench: it_cond skipped (ARM mode)\n");
    g_bolt_bench_sink = 0x49544e41u; /* Explicit unavailable marker, not stale data. */
#endif
}

/* P8: explicit ARM↔Thumb callees. Clang emits BLX across modes. */
__attribute__((target("arm"), noinline, used))
static uint32_t bolt_bench_arm_callee(uint32_t x) {
    return x + 7u;
}

__attribute__((target("thumb"), noinline, used))
static uint32_t bolt_bench_thumb_callee(uint32_t x) {
    return x * 3u;
}

__attribute__((target("arm"), noinline))
void bolt_bench_interwork(void) {
    lk_time_t t0 = arch_cycle_count();
    uint32_t acc = 0;
    for (uint32_t i = 0; i < 10000u; i++) {
        /* ARM → Thumb */
        acc += bolt_bench_thumb_callee(i);
        /* Thumb → ARM (nested): thumb_callee is Thumb; call ARM from here too */
        acc += bolt_bench_arm_callee(i);
    }
    /* Force a Thumb site that calls ARM via a small Thumb wrapper. */
    acc += bolt_bench_thumb_callee(bolt_bench_arm_callee(acc));
    if (acc == 0)
        printf("bolt_bench: interwork unexpected zero\n");
    bench_banner("interwork", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

__attribute__((noinline)) static uint32_t bolt_bench_switch_pick(uint32_t x) {
    /* Dense 8-way switch with per-case operations deliberately unrelated by
     * any single arithmetic formula -- an earlier x+1..x+8 version let clang
     * fold the whole switch into "x + (x%8) + 1", producing no dispatch at
     * all. This shape reliably gets a Thumb-2 TBB/TBH table branch instead
     * of a compare chain or algebraic collapse. */
    switch (x % 8u) {
    case 0: return x ^ 0x1111u;
    case 1: return x * 3u + 1u;
    case 2: return ~x;
    case 3: return x << 2;
    case 4: return x >> 1;
    case 5: return x & 0xff00u;
    case 6: return x | 0x8000u;
    case 7: return x - 0x99u;
    default: return x;
    }
}

__attribute__((noinline)) void bolt_bench_switch(void) {
    lk_time_t t0 = arch_cycle_count();
    uint32_t acc = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS; i++) {
        acc += bolt_bench_switch_pick(i);
    }
    bench_banner("switch", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

__attribute__((noinline)) static uint32_t bolt_bench_spill_helper(uint32_t a, uint32_t b,
                                                                   uint32_t c, uint32_t d) {
    return a + b + c + d;
}

__attribute__((noinline)) void bolt_bench_spill_ret(void) {
    /* Enough live values across two calls to force the compiler to spill
     * callee-saved registers, giving a POP {..., pc} / LDM {..., pc}
     * epilogue instead of a bare BX lr -- the standard shape for almost any
     * function beyond a trivial leaf. */
    lk_time_t t0 = arch_cycle_count();
    uint32_t acc = 0;
    for (uint32_t i = 0; i < 100000u; i++) {
        uint32_t a = i, b = i + 1u, c = i + 2u, d = i + 3u;
        uint32_t e = i + 4u, f = i + 5u, g = i + 6u;
        acc += bolt_bench_spill_helper(a, b, c, d);
        acc += bolt_bench_spill_helper(e, f, g, i);
    }
    bench_banner("spill_ret", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

__attribute__((noinline)) void bolt_bench_litpool(void) {
    /* Explicit inline-asm literal pool: a PC-relative ldr of a .word placed
     * inline in .text, the constant-island pattern real ARM code (esp.
     * large/FP constants) uses routinely. Loaded once, used across the
     * loop, to keep code size sane while still exercising identity-rewrite
     * of a function whose .text contains embedded data.
     *
     * The loop vectorizer is disabled: this is meant to test literal-pool
     * handling specifically, not NEON codegen, and an earlier version of
     * this loop got auto-vectorized into VLD1/VDUP/VEOR/VADD Q-register
     * sequences, conflating two unrelated things this fix was checking. */
    lk_time_t t0 = arch_cycle_count();
    uint32_t v;
    __asm__ volatile(
        "ldr %0, 1f\n\t"
        "b 2f\n\t"
        ".align 2\n\t"
        "1: .word 0xdeadbeef\n\t"
        "2:\n\t"
        : "=r"(v));
    uint32_t acc = 0;
#pragma clang loop vectorize(disable) interleave(disable)
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS; i++) {
        acc += v ^ i;
    }
    if (v != 0xdeadbeefu)
        printf("bolt_bench: litpool unexpected value 0x%x\n", v);
    bench_banner("litpool", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

__attribute__((noinline)) void bolt_bench_memcpy(void) {
    /* A nonzero source and a different destination make a skipped/broken copy
     * observable. Read every destination byte after the timed copies. */
    for (uint32_t i = 0; i < sizeof(bench_src); i++) {
        bench_src[i] = (uint8_t)(i * 37u + 11u);
        bench_dst[i] = (uint8_t)~bench_src[i];
    }
    lk_time_t t0 = arch_cycle_count();
    for (uint32_t r = 0; r < BOLT_BENCH_MEMCPY_ROUNDS; r++) {
        memcpy(bench_dst, bench_src, sizeof(bench_src));
    }
    bench_banner("memcpy", arch_cycle_count() - t0);
    uint32_t hash = 2166136261u;
    uint32_t mismatch = 0;
    for (uint32_t i = 0; i < sizeof(bench_dst); i++) {
        mismatch |= bench_dst[i] ^ bench_src[i];
        hash = (hash ^ bench_dst[i]) * 16777619u;
    }
    if (mismatch)
        printf("bolt_bench: memcpy FAIL: destination mismatch\n");
    g_bolt_bench_sink = hash;
}

/* --- Richer ARM<->Thumb interworking: indirect (function-pointer) calls ---
 * `interwork` above only exercises direct BL/BLX call sites. A function
 * pointer whose target alternates between an ARM-mode and a Thumb-mode
 * callee (mode encoded in address bit 0 per AAPCS) crosses modes through
 * an indirect BLX-via-register instead -- a distinct code shape BOLT must
 * get right independently of the direct-call case. The 19:1 skew also
 * gives --indirect-call-promotion a real, heavily-biased target
 * distribution to actually promote into a guarded direct call. */
__attribute__((target("thumb"), noinline, used))
static uint32_t bolt_bench_ind_thumb_target(uint32_t x) {
    return x + 101u;
}

__attribute__((target("arm"), noinline, used))
static uint32_t bolt_bench_ind_arm_target(uint32_t x) {
    return x * 5u + 3u;
}

typedef uint32_t (*bolt_bench_fnptr_t)(uint32_t);

__attribute__((noinline)) void bolt_bench_indirect_call(void) {
    lk_time_t t0 = arch_cycle_count();
    uint32_t acc = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS_CALL; i++) {
        bolt_bench_fnptr_t fn =
            ((i % 20u) != 0u) ? bolt_bench_ind_thumb_target : bolt_bench_ind_arm_target;
        acc += fn(i);
    }
    bench_banner("indirect_call", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

/* --- Richer ARM<->Thumb interworking: tail calls across modes ---
 * A Thumb function whose final statement returns another function's
 * result directly is a tail-call candidate -- clang may emit a
 * mode-crossing branch (B/BX) instead of BL/BLX+return, a third distinct
 * interworking shape alongside the direct and indirect cases above. */
__attribute__((target("arm"), noinline, used))
static uint32_t bolt_bench_tail_arm_callee(uint32_t x) {
    return x ^ 0xC0FFEEu;
}

__attribute__((target("thumb"), noinline))
static uint32_t bolt_bench_tail_thumb_caller(uint32_t x) {
    return bolt_bench_tail_arm_callee(x);
}

__attribute__((noinline)) void bolt_bench_interwork_tail(void) {
    lk_time_t t0 = arch_cycle_count();
    uint32_t acc = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS_CALL; i++) {
        acc += bolt_bench_tail_thumb_caller(i);
    }
    bench_banner("interwork_tail", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

/* --- Register pressure, for -reg-reassign ---
 * Enough simultaneously-live values that the compiler must make real
 * register-allocation decisions (spills or callee-saved use) -- gives
 * -reg-reassign something to actually reassign. Thumb-1's narrow (2-byte)
 * encodings only reach r0-r7 while Thumb-2's wide (4-byte) encodings reach
 * r0-r15, so a reassignment that pushes a hot value into a high register
 * can change code size on this target in a way that has no x86/AArch64
 * analogue -- worth watching for specifically here, not just correctness. */
__attribute__((noinline)) static uint32_t bolt_bench_regpressure_calc(uint32_t seed) {
    uint32_t a = seed, b = seed * 3u + 1u, c = seed ^ 0xABCDu, d = seed << 2, e = seed >> 1;
    uint32_t f = a + b, g = b + c, h = c + d, i2 = d + e, j = e + a;
    uint32_t k = f ^ g, l = g ^ h, m = h ^ i2, n = i2 ^ j, o = j ^ f;
    uint32_t p = k + l + m, q = m + n + o, r = n + o + k, s = o + k + l;
    return a + b + c + d + e + f + g + h + i2 + j + k + l + m + n + o + p + q + r + s;
}

__attribute__((noinline)) void bolt_bench_regpressure(void) {
    lk_time_t t0 = arch_cycle_count();
    uint32_t acc = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS_CALL; i++) {
        acc += bolt_bench_regpressure_calc(i);
    }
    bench_banner("regpressure", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

/* --- Hot/cold skew with a substantial cold body, for -split-functions ---
 * `hot_cold` above already skews branch outcome, but its cold arm is one
 * instruction -- too small for -split-functions to have anything worth
 * physically relocating. This one's cold arm is a real (if small) function
 * with its own loop and a printf, taken roughly 1 in 256K times, giving
 * the pass a genuinely separable cold region. The synthesized jump to/from
 * the relocated cold fragment also exercises the same long-jump/veneer
 * machinery as P5, just triggered by splitting rather than branch range. */
__attribute__((noinline)) static void bolt_bench_cold_path(uint32_t i) {
    uint32_t x = i;
    for (int k = 0; k < 32; k++) {
        x = (x * 2654435761u) ^ (x >> 15);
    }
    printf("bolt_bench: cold_path hit at i=%u (x=%u)\n", i, x);
    g_bolt_bench_sink ^= x;
}

__attribute__((noinline)) void bolt_bench_hotcold_split(void) {
    lk_time_t t0 = arch_cycle_count();
    uint32_t acc = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS; i++) {
        if ((i & 0x3FFFFu) == 0x3FFFFu) {
            bolt_bench_cold_path(i);
        } else {
            acc += i * 2u + 1u;
        }
    }
    bench_banner("hotcold_split", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

/* --- Identical function bodies, for -icf ---
 * Two independently-named functions performing the literal same
 * computation, with no reference to their own identity, so clang has no
 * reason to generate different code for them -- a legitimate candidate
 * for BOLT's identical-code-folding to merge into one copy with two
 * callers redirected to it. (Caveat: if lld's own --icf is enabled in the
 * LK link, these may already be merged before BOLT ever sees the input
 * binary -- check with nm before trusting this as an unfolded-input
 * baseline.) */
__attribute__((noinline)) uint32_t bolt_bench_icf_a(uint32_t x) {
    return (x * 2654435761u) ^ (x >> 13) ^ 0x9E3779B9u;
}

__attribute__((noinline)) uint32_t bolt_bench_icf_b(uint32_t x) {
    return (x * 2654435761u) ^ (x >> 13) ^ 0x9E3779B9u;
}

__attribute__((noinline)) void bolt_bench_icf(void) {
    lk_time_t t0 = arch_cycle_count();
    uint32_t acc = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS_CALL; i++) {
        acc += bolt_bench_icf_a(i);
        acc += bolt_bench_icf_b(i ^ 1u);
    }
    bench_banner("icf", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

/* --- Rare register-heavy branch inside one function, for shrink-wrapping ---
 * The common path is register-light (no callee-saved use needed); a rare
 * path needs enough simultaneously-live values to force callee-saved
 * register use. An unconditional prologue would push/pop those registers
 * on every call regardless of which path is taken -- shrink-wrapping's
 * job is to move that save/restore onto only the path that needs it. */
__attribute__((noinline)) void bolt_bench_shrinkwrap(void) {
    lk_time_t t0 = arch_cycle_count();
    uint32_t acc = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS; i++) {
        if ((i & 0xFFFu) != 0xFFFu) {
            acc += i;
            continue;
        }
        uint32_t a = i, b = i + 1u, c = i + 2u, d = i + 3u;
        uint32_t e = i + 4u, f = i + 5u, g = i + 6u, h = i + 7u;
        uint32_t r = a ^ b;
        r += c; r ^= d; r += e; r ^= f; r += g; r ^= h;
        acc += r;
    }
    bench_banner("shrinkwrap", arch_cycle_count() - t0);
    g_bolt_bench_sink = acc;
}

/* Defined in composite.c -- see that file's header comment for why this
 * workload is split across two translation units. */
uint32_t composite_process(uint32_t x);
void composite_report_cold(uint32_t code);

__attribute__((noinline)) void bolt_bench_composite(void) {
    struct bolt_pmu p0, p1;
    bolt_pmu_init();
    /* Counters are per core: keep this thread on the core it starts on. */
    thread_t *self = get_current_thread();
    int old_pin = thread_pinned_cpu(self);
    uint start_cpu = arch_curr_cpu_num();
    thread_set_pinned_cpu(self, (int)start_cpu);
    lk_time_t t0 = arch_cycle_count();
    bolt_pmu_read(&p0);
    uint32_t acc = 0;
    for (uint32_t i = 0; i < BOLT_BENCH_ITERS; i++) {
        acc += composite_process(i);
        if ((i & 0x3FFFFu) == 0x3FFFFu) {
            composite_report_cold(acc);
        }
    }
    bolt_pmu_read(&p1);
    bench_banner("composite", arch_cycle_count() - t0);
    if (arch_curr_cpu_num() != start_cpu) {
        printf("bolt_bench: composite pmu INVALID (migrated cpu%u -> cpu%u)\n", start_cpu,
               (uint)arch_curr_cpu_num());
    } else {
        bolt_pmu_report("composite", &p0, &p1);
    }
    thread_set_pinned_cpu(self, old_pin);
    /* Result checksum, so the comparison tools can verify every image computes the same. */
    printf("bolt_bench: composite acc=0x%08x\n", (unsigned)acc);
    g_bolt_bench_sink = acc;
}

/* --- stair v2: one workload, three techniques, one clear step each -------------
 * bolt_bench_stair_kernel() has STAIR_SITES guarded call sites. The selector is a
 * runtime bitmap with half the guards permanently false. Each hot site calls
 * bolt_bench_stair_step() in composite.c (another TU). Same input, same profile,
 * so the stages are cumulative and each has its own expected counter signature:
 *
 *   PGO      the cold sites. Baseline skips each with a taken branch and leaves its
 *            body between hot code; PGO moves the bodies out of line.
 *            expect: `taken` drops (guards fall through).
 *   ThinLTO  the helper call crosses a TU, so only LTO inlines it.
 *            expect: `inst` drops (call/return/argument shuffling gone) and `taken`
 *            drops by two per call.
 *   BOLT     the helper has two arms of ~70 bytes each and a per-SITE bias (even
 *            sites take the THEN arm ~98%, odd ~2%). A compile-time profile is per
 *            function so it records ~50/50 and, after inlining, every site keeps
 *            both arms in line: hot and cold arms alternate through the code and the
 *            hot path spans ~2x the cache lines it needs -- more than the 48 KB L1I.
 *            BOLT profiles the final inlined binary, packs each site's hot arm and
 *            splits the cold ones away.
 *            expect: `l1i_refill` drops and IPC recovers, cycles follow.
 * Blocks are independent (no dependency chain) so the kernel is front-end bound;
 * the empty asm keeps them real branches rather than IT-predicated code. */
#ifndef STAIR_M
#define STAIR_M 10 /* 64 sites per unit; the sweep varies it */
#endif
#ifndef STAIR_X
#define STAIR_X 0 /* extra 16-site blocks (0..3) for finer steps */
#endif
#define STAIR_SITES (64u * STAIR_M + 16u * STAIR_X)
extern void bolt_bench_stair_init(uint32_t seed);
extern uint32_t bolt_bench_stair_step(uint32_t x, uint32_t site);

#define STAIR_SITE()                                                        \
    {                                                                       \
        const uint32_t k = __COUNTER__;                                     \
        if (sel[k >> 5] & (1u << (k & 31u))) {                              \
            acc ^= bolt_bench_stair_step(x + k * 0x9E37u, k);               \
            __asm__ volatile("" : "+r"(acc));                               \
        }                                                                   \
    }
#define STAIR_R2(m) m() m()
#define STAIR_R4(m) STAIR_R2(m) STAIR_R2(m)
#define STAIR_R16(m) STAIR_R4(m) STAIR_R4(m) STAIR_R4(m) STAIR_R4(m)
#define STAIR_R64(m) STAIR_R16(m) STAIR_R16(m) STAIR_R16(m) STAIR_R16(m)

__attribute__((noinline)) uint32_t bolt_bench_stair_kernel(uint32_t x, const volatile uint32_t *sel) {
    uint32_t acc = x;
#if STAIR_M >= 1
    STAIR_R64(STAIR_SITE)
#endif
#if STAIR_M >= 2
    STAIR_R64(STAIR_SITE)
#endif
#if STAIR_M >= 3
    STAIR_R64(STAIR_SITE)
#endif
#if STAIR_M >= 4
    STAIR_R64(STAIR_SITE)
#endif
#if STAIR_M >= 5
    STAIR_R64(STAIR_SITE)
#endif
#if STAIR_M >= 6
    STAIR_R64(STAIR_SITE)
#endif
#if STAIR_M >= 7
    STAIR_R64(STAIR_SITE)
#endif
#if STAIR_M >= 8
    STAIR_R64(STAIR_SITE)
#endif
#if STAIR_M >= 9
    STAIR_R64(STAIR_SITE)
#endif
#if STAIR_M >= 10
    STAIR_R64(STAIR_SITE)
#endif
#if STAIR_X >= 1
    STAIR_R16(STAIR_SITE)
#endif
#if STAIR_X >= 2
    STAIR_R16(STAIR_SITE)
#endif
#if STAIR_X >= 3
    STAIR_R16(STAIR_SITE)
#endif
    return acc;
}

#define BOLT_BENCH_STAIR_ITERS 1500u
#define BOLT_BENCH_STAIR_WARMUP 100u
/* hot guards: bits 0,1 of every nibble, so both site-bias classes (even/odd) run */
#define BOLT_BENCH_STAIR_SEL 0x33333333u
/* Variant 2 hot set: bits 2,3 of every nibble -- same number of hot sites, both site-bias
 * classes still present, but none of the sites the profile saw hot. */
#define BOLT_BENCH_STAIR_SEL_SHIFTED 0xCCCCCCCCu

static volatile uint32_t g_stair_sel[(STAIR_SITES + 31u) / 32u];

__attribute__((noinline)) void bolt_bench_stair(void) {
    struct bolt_pmu p0, p1;
    bolt_pmu_init();
    bolt_bench_stair_init(g_input_variant == 1 ? 0x5EEDF00Du : 12345u);
    thread_t *self = get_current_thread();
    int old_pin = thread_pinned_cpu(self);
    uint start_cpu = arch_curr_cpu_num();
    thread_set_pinned_cpu(self, (int)start_cpu);
    for (uint32_t i = 0; i < (STAIR_SITES + 31u) / 32u; i++) {
        g_stair_sel[i] = (g_input_variant == 2) ? BOLT_BENCH_STAIR_SEL_SHIFTED
                                                : BOLT_BENCH_STAIR_SEL; /* opaque: no folding */
    }
    uint32_t acc = 0;
    /* Warm-up trains the predictors and caches, so the window measures steady state.
     * Interrupts are off inside it: a timer tick would add its own instructions. */
    for (uint32_t i = 0; i < BOLT_BENCH_STAIR_WARMUP; i++) {
        acc = bolt_bench_stair_kernel(acc + i, g_stair_sel);
    }
    bench_ints_off();
    lk_time_t t0 = arch_cycle_count();
    bolt_pmu_read(&p0);
    for (uint32_t i = 0; i < BOLT_BENCH_STAIR_ITERS; i++) {
        acc = bolt_bench_stair_kernel(acc + i, g_stair_sel);
    }
    bolt_pmu_read(&p1);
    lk_time_t cyc = arch_cycle_count() - t0;
    bench_ints_on();
    bench_banner("stair", cyc);
    if (arch_curr_cpu_num() != start_cpu) {
        printf("bolt_bench: stair pmu INVALID (migrated cpu%u -> cpu%u)\n", start_cpu,
               (uint)arch_curr_cpu_num());
    } else {
        bolt_pmu_report("stair", &p0, &p1);
    }
    thread_set_pinned_cpu(self, old_pin);
    /* Result checksum: every variant, including BOLT's rewrite, must print the same. */
    printf("bolt_bench: stair acc=0x%08x\n", (unsigned)acc);
    g_bolt_bench_sink = acc;
}

/* --- pgo_lab: which compiler decisions does a profile actually change? ---------
 * Four independent kernels, each isolating one thing PGO can do that a static -O2
 * build cannot know. baseline vs +PGO on the same source shows which ones pay off on
 * a Cortex-A72 (branch layout alone does not: the stair workload showed predicted
 * taken branches are nearly free). The kernels are throughput-bound (independent
 * lanes) so instruction-count effects are visible, and every input is opaque to
 * the compiler (volatile / table loaded) so nothing folds.
 *   a  hot call-site inlining: pl_mix() is ~80 IR instructions, over -O2's inline
 *      threshold, called from 4 hot sites and 1 cold one. Only a profile says the
 *      sites are hot and raises the threshold.
 *   b  skewed switch: 92% of ops are case 0. A profile peels the hot case into a
 *      compare before the jump table.
 *   c  register pressure around a cold call: 12 live accumulators, and a rare call
 *      to a noinline function. A profile keeps the hot path in registers.
 *   d  loop trip count: an inner loop of 2..5 iterations (average 3.5) that a profile
 *      can unroll.
 */
#define PL_MIXR(c, s) v = ((v ^ (k + (c))) * 0x9E3779B1u) ^ (v >> (s));
static uint32_t pl_mix(uint32_t v, uint32_t k) {
    PL_MIXR(0x1001u, 3)
    PL_MIXR(0x2002u, 8)
    PL_MIXR(0x3003u, 13)
    PL_MIXR(0x4004u, 7)
    PL_MIXR(0x5005u, 12)
    PL_MIXR(0x6006u, 6)
    PL_MIXR(0x7007u, 11)
    PL_MIXR(0x8008u, 5)
    PL_MIXR(0x9009u, 10)
    PL_MIXR(0xa00au, 4)
    PL_MIXR(0xb00bu, 9)
    PL_MIXR(0xc00cu, 3)
    PL_MIXR(0xd00du, 8)
    PL_MIXR(0xe00eu, 13)
    PL_MIXR(0xf00fu, 7)
    PL_MIXR(0x0010u, 12)
    PL_MIXR(0x1011u, 6)
    PL_MIXR(0x2012u, 11)
    PL_MIXR(0x3013u, 5)
    PL_MIXR(0x4014u, 10)
    return v;
}

static uint8_t g_pl_ops[1024];
static volatile uint32_t g_pl_mask;

static void pl_init(void) {
    uint32_t s = (g_input_variant == 1) ? 0x5EEDF00Du : 12345u;
    /* Variant 2 moves the 92% hot case from 0 to 7: the profile's hot case becomes cold. */
    uint8_t hot = (g_input_variant == 2) ? 7u : 0u;
    for (uint32_t i = 0; i < 1024; i++) {
        s = s * 1664525u + 1013904223u;
        uint32_t r = s >> 24;
        uint8_t cold = (uint8_t)(1 + (r % 15u));
        if (hot != 0 && cold == hot) {
            cold = 0; /* keep the cold cases a permutation of the original ones */
        }
        g_pl_ops[i] = (r < 236u) ? hot : cold;
    }
    g_pl_mask = 0xFFFFu;
}

__attribute__((noinline)) static uint32_t pl_a(uint32_t seed, uint32_t n) {
    uint32_t mask = g_pl_mask;
    uint32_t a0 = seed, a1 = seed + 1, a2 = seed + 2, a3 = seed + 3;
    for (uint32_t i = 0; i < n; i++) {
        a0 = pl_mix(a0, i);
        a1 = pl_mix(a1, i ^ 0x55u);
        a2 = pl_mix(a2, i + 7u);
        a3 = pl_mix(a3, i * 3u);
        if ((a0 & mask) == 0) {
            a0 = pl_mix(a0, 0x1234u);
        }
    }
    return a0 ^ a1 ^ a2 ^ a3;
}

__attribute__((noinline)) static uint32_t pl_b(uint32_t seed, uint32_t n) {
    uint32_t acc = seed, b1 = seed + 1, b2 = seed + 2, b3 = seed + 3, b4 = seed + 4, b5 = seed + 5;
    for (uint32_t i = 0; i < n; i++) {
        switch (g_pl_ops[i & 1023u]) {
        case 0: acc = acc * 0x9E3779B1u + i; break;
        case 1: acc = (acc ^ 0x1111u) * 0x85ebca6bu; acc += acc >> 3; __asm__ volatile("" : "+r"(acc)); break;
        case 2: acc = (acc ^ 0x2222u) * 0xc2b2ae35u; acc += acc >> 4; __asm__ volatile("" : "+r"(acc)); break;
        case 3: acc = (acc ^ 0x3333u) * 0x27d4eb2fu; acc += acc >> 5; __asm__ volatile("" : "+r"(acc)); break;
        case 4: acc = (acc ^ 0x4444u) * 0x165667b1u; acc += acc >> 6; __asm__ volatile("" : "+r"(acc)); break;
        case 5: acc = (acc ^ 0x5555u) * 0xd3a2646cu; acc += acc >> 7; __asm__ volatile("" : "+r"(acc)); break;
        case 6: acc = (acc ^ 0x6666u) * 0xfd7046c5u; acc += acc >> 8; __asm__ volatile("" : "+r"(acc)); break;
        case 7: acc = (acc ^ 0x7777u) * 0xb55a4f09u; acc += acc >> 9; __asm__ volatile("" : "+r"(acc)); break;
        case 8: acc = (acc ^ 0x8888u) * 0x9e3779b1u; acc += acc >> 10; __asm__ volatile("" : "+r"(acc)); break;
        case 9: acc = (acc ^ 0x9999u) * 0x85ebca6bu; acc += acc >> 2; __asm__ volatile("" : "+r"(acc)); break;
        case 10: acc = (acc ^ 0xaaaau) * 0xc2b2ae35u; acc += acc >> 3; __asm__ volatile("" : "+r"(acc)); break;
        case 11: acc = (acc ^ 0xbbbbu) * 0x27d4eb2fu; acc += acc >> 4; __asm__ volatile("" : "+r"(acc)); break;
        case 12: acc = (acc ^ 0xccccu) * 0x165667b1u; acc += acc >> 5; __asm__ volatile("" : "+r"(acc)); break;
        case 13: acc = (acc ^ 0xddddu) * 0xd3a2646cu; acc += acc >> 6; __asm__ volatile("" : "+r"(acc)); break;
        case 14: acc = (acc ^ 0xeeeeu) * 0xfd7046c5u; acc += acc >> 7; __asm__ volatile("" : "+r"(acc)); break;
        case 15: acc = (acc ^ 0xffffu) * 0xb55a4f09u; acc += acc >> 8; __asm__ volatile("" : "+r"(acc)); break;
        }
        b1 += i ^ 0x11u; b2 ^= i + 3u; b3 += i * 5u; b4 ^= i >> 1; b5 += i ^ 0x77u;
        __asm__ volatile("" : "+r"(b1), "+r"(b2), "+r"(b3), "+r"(b4), "+r"(b5));
    }
    return acc ^ b1 ^ b2 ^ b3 ^ b4 ^ b5;
}

__attribute__((noinline)) static uint32_t pl_rare(uint32_t x) {
    for (uint32_t i = 0; i < 8; i++) {
        x = (x * 0x85EBCA6Bu) ^ (x >> 13) ^ i;
    }
    return x;
}

__attribute__((noinline)) static uint32_t pl_c(uint32_t seed, uint32_t n) {
    uint32_t mask = g_pl_mask;
    uint32_t r0 = seed, r1 = seed + 1, r2 = seed + 2, r3 = seed + 3, r4 = seed + 4, r5 = seed + 5;
    uint32_t r6 = seed + 6, r7 = seed + 7, r8 = seed + 8, r9 = seed + 9, r10 = seed + 10, r11 = seed + 11;
    for (uint32_t i = 0; i < n; i++) {
        r0 += i; r1 ^= i + 1u; r2 += r0 >> 3; r3 ^= r1 + 5u; r4 += i * 3u; r5 ^= r4 >> 2;
        r6 += r5 ^ i; r7 ^= r6 + 9u; r8 += r7 >> 1; r9 ^= r8 + i; r10 += r9 ^ 0x33u; r11 ^= r10 + 1u;
        if (((r0 ^ r11) & mask) == 0) {
            r0 ^= pl_rare(r1 + r2 + r3);
        }
    }
    return r0 ^ r1 ^ r2 ^ r3 ^ r4 ^ r5 ^ r6 ^ r7 ^ r8 ^ r9 ^ r10 ^ r11;
}

__attribute__((noinline)) static uint32_t pl_d(uint32_t seed, uint32_t n) {
    uint32_t acc = seed;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t m = 2u + (g_pl_ops[i & 1023u] & 3u);
        uint32_t t = acc + i;
        for (uint32_t j = 0; j < m; j++) {
            t = (t ^ j) * 0x9E3779B1u + (t >> 7);
        }
        acc += t;
    }
    return acc;
}

static void pl_run(const char *name, uint32_t (*fn)(uint32_t, uint32_t), uint32_t n) {
    struct bolt_pmu p0, p1;
    bolt_pmu_init();
    thread_t *self = get_current_thread();
    int old_pin = thread_pinned_cpu(self);
    uint start_cpu = arch_curr_cpu_num();
    thread_set_pinned_cpu(self, (int)start_cpu);
    uint32_t acc = fn(1u, n / 16u + 1u); /* warm-up: caches and predictors */
    bench_ints_off();
    lk_time_t t0 = arch_cycle_count();
    bolt_pmu_read(&p0);
    acc ^= fn(2u, n);
    bolt_pmu_read(&p1);
    lk_time_t cyc = arch_cycle_count() - t0;
    bench_ints_on();
    bench_banner(name, cyc);
    if (arch_curr_cpu_num() == start_cpu) {
        bolt_pmu_report(name, &p0, &p1);
    }
    thread_set_pinned_cpu(self, old_pin);
    printf("bolt_bench: %s acc=0x%08x\n", name, (unsigned)acc);
    g_bolt_bench_sink = acc;
}

__attribute__((noinline)) void bolt_bench_pgo_lab(void) {
    pl_init();
    pl_run("pl_a", pl_a, 60000u);
    pl_run("pl_b", pl_b, 2000000u);
    pl_run("pl_c", pl_c, 1500000u);
    pl_run("pl_d", pl_d, 1000000u);
}

/* --- multi: a hot path that spans several functions ------------------------------
 * Six ~5 KB straight-line functions called in turn through function pointers (so every
 * entry is reached the way a vector or callback table would reach it). Each is aligned
 * to 16 KB, which puts all six on the same Cortex-A72 L1I sets (48 KB, 3-way, 16 KB per
 * way): six lines compete for three ways, so every fetch misses. Packed contiguously
 * (what BOLT's --reorder-functions does to hot functions) they fit. bolt_bench_mf5 is
 * compiled in ARM mode, the others in Thumb, so both redirect encodings are exercised.
 * The one data-dependent branch per function is what gives BOLT an edge profile to
 * find them hot (a branch-free function has no edges to count). The empty asm between
 * groups stops the compiler folding the adds into one. */
#define MF_G()                                                              \
    {                                                                       \
        a += 0x100u + (__COUNTER__ & 0x7FFu);                               \
        b ^= a + (__COUNTER__ & 0x7FFu);                                    \
        c += b >> ((__COUNTER__ & 3u) + 1u);                                \
        d ^= c + (__COUNTER__ & 0x7FFu);                                    \
        __asm__ volatile("" : "+r"(a), "+r"(b), "+r"(c), "+r"(d));          \
    }
#define MF_R2(m) m() m()
#define MF_R4(m) MF_R2(m) MF_R2(m)
#define MF_R16(m) MF_R4(m) MF_R4(m) MF_R4(m) MF_R4(m)
#define MF_R64(m) MF_R16(m) MF_R16(m) MF_R16(m) MF_R16(m)
#define MF_R256(m) MF_R64(m) MF_R64(m) MF_R64(m) MF_R64(m)
#define MF_BODY                                                             \
    {                                                                       \
        uint32_t a = x, b = x + 1u, c = x + 2u, d = x + 3u;                 \
        if (__builtin_expect(x == 0xFFFFFFF1u, 0)) {                        \
            a++; __asm__ volatile("" : "+r"(a));                                                            \
        }                                                                   \
        MF_R256(MF_G) MF_R64(MF_G)                                          \
        return a ^ b ^ c ^ d;                                               \
    }
#define MF_FN(N, MODE) __attribute__((noinline, aligned(16384), target(MODE))) uint32_t bolt_bench_mf##N(uint32_t x) MF_BODY
MF_FN(0, "thumb")
MF_FN(1, "thumb")
MF_FN(2, "thumb")
MF_FN(3, "thumb")
MF_FN(4, "thumb")
MF_FN(5, "arm")

static uint32_t (*volatile const g_mf[6])(uint32_t) = {
    bolt_bench_mf0, bolt_bench_mf1, bolt_bench_mf2, bolt_bench_mf3, bolt_bench_mf4, bolt_bench_mf5,
};

#define BOLT_BENCH_MULTI_ITERS 4000u

__attribute__((noinline)) void bolt_bench_multi(void) {
    struct bolt_pmu p0, p1;
    bolt_pmu_init();
    thread_t *self = get_current_thread();
    int old_pin = thread_pinned_cpu(self);
    uint start_cpu = arch_curr_cpu_num();
    thread_set_pinned_cpu(self, (int)start_cpu);
    uint32_t x = 1u;
    for (uint32_t i = 0; i < 200u; i++) { /* warm-up */
        for (uint32_t f = 0; f < 6; f++) {
            x = g_mf[f](x);
        }
    }
    bench_ints_off();
    lk_time_t t0 = arch_cycle_count();
    bolt_pmu_read(&p0);
    for (uint32_t i = 0; i < BOLT_BENCH_MULTI_ITERS; i++) {
        for (uint32_t f = 0; f < 6; f++) {
            x = g_mf[f](x);
        }
    }
    bolt_pmu_read(&p1);
    lk_time_t cyc = arch_cycle_count() - t0;
    bench_ints_on();
    bench_banner("multi", cyc);
    if (arch_curr_cpu_num() != start_cpu) {
        printf("bolt_bench: multi pmu INVALID (migrated)\n");
    } else {
        bolt_pmu_report("multi", &p0, &p1);
    }
    thread_set_pinned_cpu(self, old_pin);
    printf("bolt_bench: multi acc=0x%08x\n", (unsigned)x);
    g_bolt_bench_sink = x;
}

/* --- pmu_probe: which PMU events does this core really count? -------------------
 * `bolt_bench pmu_probe <ev> [<ev> ...]` (hex, up to 5) runs one fixed workload -- calls and
 * returns, taken and not-taken branches, loads and stores over a buffer larger than the L1D,
 * unaligned accesses -- and prints what each event counted. An event that reads 0 here while
 * the workload obviously does that thing is not implemented (or not enabled) on this core. */
static uint8_t g_pp_buf[65536 + 64];

__attribute__((noinline)) static uint32_t pp_leaf(uint32_t x) {
    return x * 3u + 1u;
}

__attribute__((noinline)) static uint32_t pp_kernel(uint32_t n) {
    uint32_t x = 1u, s = 0u;
    volatile uint8_t *buf = g_pp_buf;
    for (uint32_t i = 0; i < n; i++) {
        x = pp_leaf(x);
        if (x & 4u) {
            s += 3u;
            __asm__ volatile("" : "+r"(s));
        } else {
            s ^= 5u;
            __asm__ volatile("" : "+r"(s));
        }
        s += buf[(i * 67u) & 0xFFFFu];
        buf[(i * 131u) & 0xFFFFu] = (uint8_t)s;
        s += *(volatile uint32_t *)(buf + 1u + ((i * 8u) & 0x3FF0u)); /* unaligned load */
    }
    return s ^ x;
}

static void bolt_bench_pmu_probe(void) {
    struct bolt_pmu p0, p1;
    bolt_pmu_init();
    thread_t *self = get_current_thread();
    int old_pin = thread_pinned_cpu(self);
    uint start_cpu = arch_curr_cpu_num();
    thread_set_pinned_cpu(self, (int)start_cpu);
    uint32_t acc = pp_kernel(2000u); /* warm-up */
    bench_ints_off();
    bolt_pmu_read(&p0);
    acc ^= pp_kernel(100000u);
    bolt_pmu_read(&p1);
    bench_ints_on();
    bolt_pmu_report("pmu_probe", &p0, &p1);
    thread_set_pinned_cpu(self, old_pin);
    printf("bolt_bench: pmu_probe iters=100000 acc=0x%08x\n", (unsigned)acc);
    g_bolt_bench_sink = acc;
}

static void run_one(const char *name) {
    if (!strcmp(name, "hot_loop")) {
        bolt_bench_hot_loop();
    } else if (!strcmp(name, "hot_cold")) {
        bolt_bench_hot_cold();
    } else if (!strcmp(name, "branch_chain")) {
        bolt_bench_branch_chain();
    } else if (!strcmp(name, "memcpy")) {
        bolt_bench_memcpy();
    } else if (!strcmp(name, "far_call")) {
        bolt_bench_far_call();
    } else if (!strcmp(name, "it_cond")) {
        bolt_bench_it_cond();
    } else if (!strcmp(name, "interwork")) {
        bolt_bench_interwork();
    } else if (!strcmp(name, "switch")) {
        bolt_bench_switch();
    } else if (!strcmp(name, "spill_ret")) {
        bolt_bench_spill_ret();
    } else if (!strcmp(name, "litpool")) {
        bolt_bench_litpool();
    } else if (!strcmp(name, "indirect_call")) {
        bolt_bench_indirect_call();
    } else if (!strcmp(name, "interwork_tail")) {
        bolt_bench_interwork_tail();
    } else if (!strcmp(name, "regpressure")) {
        bolt_bench_regpressure();
    } else if (!strcmp(name, "hotcold_split")) {
        bolt_bench_hotcold_split();
    } else if (!strcmp(name, "icf")) {
        bolt_bench_icf();
    } else if (!strcmp(name, "shrinkwrap")) {
        bolt_bench_shrinkwrap();
    } else if (!strcmp(name, "composite")) {
        bolt_bench_composite();
    } else if (!strcmp(name, "stair")) {
        bolt_bench_stair();
    } else if (!strcmp(name, "pgo_lab")) {
        bolt_bench_pgo_lab();
    } else if (!strcmp(name, "multi")) {
        bolt_bench_multi();
    } else if (!strcmp(name, "all")) {
        bolt_bench_hot_loop();
        print_sink("hot_loop");
        bolt_bench_hot_cold();
        print_sink("hot_cold");
        bolt_bench_branch_chain();
        print_sink("branch_chain");
        bolt_bench_memcpy();
        print_sink("memcpy");
        bolt_bench_far_call();
        print_sink("far_call");
        bolt_bench_it_cond();
        print_sink("it_cond");
        bolt_bench_interwork();
        print_sink("interwork");
        bolt_bench_switch();
        print_sink("switch");
        bolt_bench_spill_ret();
        print_sink("spill_ret");
        bolt_bench_litpool();
        print_sink("litpool");
        bolt_bench_indirect_call();
        print_sink("indirect_call");
        bolt_bench_interwork_tail();
        print_sink("interwork_tail");
        bolt_bench_regpressure();
        print_sink("regpressure");
        bolt_bench_hotcold_split();
        print_sink("hotcold_split");
        bolt_bench_icf();
        print_sink("icf");
        bolt_bench_shrinkwrap();
        print_sink("shrinkwrap");
        bolt_bench_composite();
        print_sink("composite");
        bolt_bench_stair();
        print_sink("stair");
    } else {
        printf("unknown workload %s\n", name);
    }
}

/* T2 (SMP): run rewritten code on every core.
 *
 * Phase 1 runs the full `all` suite on each core in turn (a thread pinned to
 * that core; the others idle), checking the thread really runs there. Phase 2
 * runs the workloads whose only shared state is the (per-core) sink on all
 * cores at once, `reps` times in a per-core rotated order, so the same and
 * different rewritten functions execute concurrently. memcpy (shared
 * buffers), composite and stair (shared PMU/selector state) stay out of
 * phase 2. Every printed sink is checked on the host against the independent
 * oracle (scripts/bolt_bench_smp_check.py). */
typedef void (*bench_fn)(void);
static const struct { const char *name; bench_fn fn; } g_smp_set[] = {
    {"hot_loop", bolt_bench_hot_loop}, {"hot_cold", bolt_bench_hot_cold},
    {"branch_chain", bolt_bench_branch_chain}, {"far_call", bolt_bench_far_call},
    {"it_cond", bolt_bench_it_cond}, {"interwork", bolt_bench_interwork},
    {"switch", bolt_bench_switch}, {"spill_ret", bolt_bench_spill_ret},
    {"litpool", bolt_bench_litpool}, {"indirect_call", bolt_bench_indirect_call},
    {"interwork_tail", bolt_bench_interwork_tail}, {"regpressure", bolt_bench_regpressure},
    {"hotcold_split", bolt_bench_hotcold_split}, {"icf", bolt_bench_icf},
    {"shrinkwrap", bolt_bench_shrinkwrap},
};
#define SMP_SET_N (sizeof(g_smp_set) / sizeof(g_smp_set[0]))
#define SMP_MAX_REPS 8u
static uint32_t g_smp_result[SMP_MAX_CPUS][SMP_MAX_REPS][SMP_SET_N];
static volatile uint32_t g_smp_ran_on[SMP_MAX_CPUS][2];
static volatile int g_smp_ready;
static volatile int g_smp_go;
static uint32_t g_smp_reps;
static uint32_t g_smp_ncpu;

static int smp_seq_thread(void *arg) {
    uint32_t cpu = (uint32_t)(uintptr_t)arg;
    printf("bolt_bench: smp seq cpu=%u on=%u begin\n", (unsigned)cpu, (unsigned)arch_curr_cpu_num());
    run_one("all");
    printf("bolt_bench: smp seq cpu=%u on=%u end\n", (unsigned)cpu, (unsigned)arch_curr_cpu_num());
    return 0;
}

static int smp_conc_thread(void *arg) {
    uint32_t cpu = (uint32_t)(uintptr_t)arg;
    g_smp_ran_on[cpu][0] = arch_curr_cpu_num();
    atomic_add((volatile int *)&g_smp_ready, 1);
    while (!g_smp_go)
        thread_yield(); /* core 0 shares with the console thread */
    for (uint32_t r = 0; r < g_smp_reps; r++) {
        for (uint32_t k = 0; k < SMP_SET_N; k++) {
            uint32_t w = (k + cpu * 4u + r) % SMP_SET_N;
            g_smp_set[w].fn();
            g_smp_result[cpu][r][w] = g_bolt_bench_sink;
        }
    }
    g_smp_ran_on[cpu][1] = arch_curr_cpu_num();
    return 0;
}

static void bolt_bench_smp(uint32_t reps) {
    thread_t *t[SMP_MAX_CPUS];
    uint32_t n = 0;
    for (uint32_t c = 0; c < SMP_MAX_CPUS; c++)
        if (mp_is_cpu_active(c))
            n = c + 1;
    g_smp_ncpu = n;
    g_smp_reps = reps < 1 ? 1 : (reps > SMP_MAX_REPS ? SMP_MAX_REPS : reps);
    printf("bolt_bench: smp cpus=%u reps=%u set=%u\n", (unsigned)n, (unsigned)g_smp_reps, (unsigned)SMP_SET_N);

    for (uint32_t c = 0; c < n; c++) {
        t[c] = thread_create("bb_smp_seq", smp_seq_thread, (void *)(uintptr_t)c, DEFAULT_PRIORITY, 8192);
        thread_set_pinned_cpu(t[c], (int)c);
        thread_resume(t[c]);
        thread_join(t[c], NULL, INFINITE_TIME);
    }

    g_smp_ready = 0;
    g_smp_go = 0;
    g_bench_quiet = 1;
    for (uint32_t c = 0; c < n; c++) {
        t[c] = thread_create("bb_smp_conc", smp_conc_thread, (void *)(uintptr_t)c, DEFAULT_PRIORITY, 8192);
        thread_set_pinned_cpu(t[c], (int)c);
        thread_resume(t[c]);
    }
    /* The console thread shares core 0 with its worker: wait by sleeping so
     * that worker can reach the barrier, then release all cores together. */
    while (g_smp_ready < (int)n)
        thread_sleep(1);
    g_smp_go = 1;
    for (uint32_t c = 0; c < n; c++)
        thread_join(t[c], NULL, INFINITE_TIME);
    g_bench_quiet = 0;

    for (uint32_t c = 0; c < n; c++) {
        printf("bolt_bench: smp conc cpu=%u on=%u,%u\n", (unsigned)c,
               (unsigned)g_smp_ran_on[c][0], (unsigned)g_smp_ran_on[c][1]);
        for (uint32_t r = 0; r < g_smp_reps; r++)
            for (uint32_t w = 0; w < SMP_SET_N; w++)
                printf("bolt_bench: smp conc cpu=%u rep=%u %s sink=0x%08x\n", (unsigned)c, (unsigned)r,
                       g_smp_set[w].name, (unsigned)g_smp_result[c][r][w]);
    }
    printf("bolt_bench: smp done\n");
}

static int bolt_bench_cmd(int argc, const console_cmd_args *argv) {
    if (argc >= 2 && !strcmp(argv[1].str, "smp")) {
        bolt_bench_smp(argc > 2 ? (uint32_t)argv[2].u : 4u);
        return 0;
    }
    if (argc < 2) {
        printf("usage: bolt_bench <hot_loop|hot_cold|branch_chain|memcpy|far_call|it_cond|interwork|switch|spill_ret|litpool|indirect_call|interwork_tail|regpressure|hotcold_split|icf|shrinkwrap|composite|stair|pgo_lab|multi|all>\n");
        return -1;
    }
    if (!strcmp(argv[1].str, "pmu_probe")) {
        for (uint32_t i = 0; i < BOLT_PMU_NCTR; i++) {
            g_pmu_custom[i] = ((int)i + 2 < argc) ? (uint32_t)strtoul(argv[i + 2].str, NULL, 16) : 0x08u;
        }
        g_pmu_set_req = 2;
        g_pmu_set_cur = -1; /* re-arm the counters with the events just given */
        bolt_bench_pmu_probe();
        return 0;
    }
    g_pmu_set_req = (argc > 2 && argv[2].i == 1) ? 1 : 0;
    g_input_variant = (argc > 3) ? (uint32_t)argv[3].u : 0u;
    run_one(argv[1].str);
    return 0;
}

/* Real hardware has no QMP memsave/pmemsave -- this replaces it for reading
 * BOLT's .bolt.instr.counters section back out over UART. Dumps in fixed
 * chunks, each with its own seq number and FNV-1a checksum (same algorithm
 * family as lk-perf's profiler_sample_checksum, applied to a raw byte range
 * instead of typed fields), so the host script can detect and re-request
 * just the corrupted chunks -- lk-perf found real, silent UART corruption
 * at both 3M and 6M baud (a USB packet-boundary artifact), and a dump
 * that just trusts whatever arrived would reproduce that same bug here. */
#define BOLT_DUMP_CHUNK 64u

static uint32_t bolt_dump_checksum(const uint8_t *buf, size_t len) {
    uint32_t c = 0x811c9dc5u;
    for (size_t i = 0; i < len; i++) {
        c ^= buf[i];
        c *= 16777619u;
    }
    return c;
}

#if WITH_BOLT_PGO
/* clang's -fprofile-instr-generate counter data, with no filesystem and no
 * runtime-init hook (ATFE's compiler-rt has a real COMPILER_RT_PROFILE_BAREMETAL
 * build mode for exactly this -- see scripts/build-pgo-rt-baremetal.sh).
 * __llvm_profile_write_buffer() serializes a complete, valid raw instrprof
 * file into this buffer; the existing generic bolt_dump command above reads
 * it out over UART like any other memory range, no new transport needed. */
#define BOLT_PGO_BUFFER_SIZE (64u * 1024u)
static uint8_t g_bolt_pgo_buffer[BOLT_PGO_BUFFER_SIZE];

extern uint64_t __llvm_profile_get_size_for_buffer(void);
extern int __llvm_profile_write_buffer(char *Buffer);

static int bolt_pgo_dump_cmd(int argc, const console_cmd_args *argv) {
    uint64_t needed = __llvm_profile_get_size_for_buffer();
    if (needed > sizeof(g_bolt_pgo_buffer)) {
        printf("bolt_pgo_dump: profile needs %llu bytes, buffer is only %u\n",
               (unsigned long long)needed, (unsigned)sizeof(g_bolt_pgo_buffer));
        return -1;
    }
    int rc = __llvm_profile_write_buffer((char *)g_bolt_pgo_buffer);
    if (rc != 0) {
        printf("bolt_pgo_dump: __llvm_profile_write_buffer failed (%d)\n", rc);
        return -1;
    }
    printf("bolt_pgo_dump: addr=%08lx size=%08lx (now: bolt_dump %08lx %08lx)\n",
           (unsigned long)(uintptr_t)g_bolt_pgo_buffer, (unsigned long)needed,
           (unsigned long)(uintptr_t)g_bolt_pgo_buffer, (unsigned long)needed);
    return 0;
}
#endif

static int bolt_dump_cmd(int argc, const console_cmd_args *argv) {
    if (argc < 3) {
        printf("usage: bolt_dump <addr_hex> <size_hex>\n");
        return -1;
    }
    uintptr_t addr = (uintptr_t)strtoul(argv[1].str, NULL, 16);
    size_t size = (size_t)strtoul(argv[2].str, NULL, 16);
    const uint8_t *base = (const uint8_t *)addr;

    printf("BOLT_DUMP_BEGIN addr=%08lx size=%08lx\n",
           (unsigned long)addr, (unsigned long)size);

    uint32_t seq = 0;
    size_t off = 0;
    while (off < size) {
        size_t chunk = size - off;
        if (chunk > BOLT_DUMP_CHUNK) {
            chunk = BOLT_DUMP_CHUNK;
        }
        uint32_t crc = bolt_dump_checksum(base + off, chunk);
        printf("BOLT_DUMP seq=%08lx off=%08lx len=%04lx crc=%08lx data=",
               (unsigned long)seq, (unsigned long)off, (unsigned long)chunk,
               (unsigned long)crc);
        for (size_t i = 0; i < chunk; i++) {
            printf("%02x", base[off + i]);
        }
        printf("\n");
        off += chunk;
        seq++;
    }
    printf("BOLT_DUMP_END seq=%08lx total=%08lx\n",
           (unsigned long)seq, (unsigned long)size);
    return 0;
}

static void bolt_bench_app_entry(const struct app_descriptor *app, void *args) {
    char name[32];
    if (cmdline_get_string("lk.bolt_bench", name, sizeof(name), NULL) != NO_ERROR) {
        return;
    }
    printf("bolt_bench: running %s from cmdline\n", name);
    run_one(name);
}

/* Hang guard for unattended test runs: `wdog <seconds>` arms the BCM PM watchdog and keeps
 * petting it from an LK timer until <seconds> have passed; `wdog 0` disarms it. A test image
 * that hangs (or loops forever) then resets the SoC back into the SD-card chainloader on its
 * own -- ~15 s after the deadline, or as soon as the timer stops running (interrupts off). */
#if __has_include(<platform/bcm28xx.h>)
#include <kernel/timer.h>
#include <platform.h>
#include <platform/bcm28xx.h>
#include <lk/reg.h>

#define BB_PM_RSTC (PM_BASE + 0x1c)
#define BB_PM_WDOG (PM_BASE + 0x24)
#define BB_PM_PASSWORD 0x5a000000u
#define BB_PM_RSTC_WRCFG_MASK 0x00000030u
#define BB_PM_RSTC_WRCFG_FULL_RESET 0x00000020u
#define BB_PM_RSTC_RESET 0x00000102u
#define BB_WDOG_TICKS (15u << 16) /* 65536 ticks/s; the field is 20 bits (< 16 s) */

static timer_t g_wdog_timer;
static lk_time_t g_wdog_deadline;
static bool g_wdog_armed;

static void wdog_pet(void) {
    *REG32(BB_PM_WDOG) = BB_PM_PASSWORD | BB_WDOG_TICKS;
    uint32_t rstc = *REG32(BB_PM_RSTC) & ~(BB_PM_RSTC_WRCFG_MASK | 0xff000000u);
    *REG32(BB_PM_RSTC) = BB_PM_PASSWORD | rstc | BB_PM_RSTC_WRCFG_FULL_RESET;
}

static enum handler_return wdog_tick(timer_t *t, lk_time_t now, void *arg) {
    if (g_wdog_armed && (int32_t)(g_wdog_deadline - now) > 0)
        wdog_pet();
    return INT_NO_RESCHEDULE;
}

static int wdog_cmd(int argc, const console_cmd_args *argv) {
    uint32_t secs = (argc > 1) ? (uint32_t)argv[1].u : 0u;
    static bool timer_ready;
    if (!timer_ready) { /* timer_cancel() asserts on a never-initialized timer */
        timer_initialize(&g_wdog_timer);
        timer_ready = true;
    }
    timer_cancel(&g_wdog_timer);
    if (!secs) {
        g_wdog_armed = false;
        *REG32(BB_PM_RSTC) = BB_PM_PASSWORD | BB_PM_RSTC_RESET;
        printf("wdog: off\n");
        return 0;
    }
    g_wdog_deadline = current_time() + secs * 1000u;
    g_wdog_armed = true;
    wdog_pet();
    timer_set_periodic(&g_wdog_timer, 1000, wdog_tick, NULL);
    printf("wdog: armed for %u s\n", (unsigned)secs);
    if (argc > 2 && !strcmp(argv[2].str, "hang")) { /* self-test: spin with IRQs on */
        printf("wdog: hanging on purpose\n");
        for (;;)
            ;
    }
    return 0;
}
#define BB_HAVE_WDOG 1

/* PC sampler for sample-based BOLT profiles (no instrumented image): `bolt_sample start
 * <cycles>` arms PMU event counter 5 on every core to count CPU cycles and interrupt on
 * overflow; each overflow records the interrupted PC (bit 0 = Thumb) in bolt_sample_buf.
 * `bolt_sample stop` disarms and prints the count; the host reads the buffer back with
 * bolt_dump and turns it into perf2bolt's pre-aggregated format
 * (scripts/pi4/samples_to_fdata.py). Design after lk-perf's PMU mode (same SPIs 48..51,
 * level-triggered, always acknowledged), but counter 5 is reached through PMEVCNTR5 /
 * PMEVTYPER5 directly (ARMv8 AArch32), never PMSELR, so an overflow in the middle of a
 * workload's own PMSELR-based counter read cannot corrupt it; counters 0..4 and the cycle
 * counter stay the workloads'. */
#include <kernel/mp.h>
#include <arch/atomic.h>
#include <dev/interrupt/arm_gic.h>
#include <platform/interrupts.h>

#define BB_SAMPLE_MAX (1u << 17)
#define BB_SAMPLE_CTR 5u
#define BB_SAMPLE_SPI 48u /* GIC SPI 16 + 32: PMU of cpu0; cpu n is 48 + n */
#define BB_SAMPLE_MIN_PERIOD 10000u

uint32_t bolt_sample_buf[BB_SAMPLE_MAX];
static volatile uint32_t g_sample_n;
static volatile uint32_t g_sample_on;
static uint32_t g_sample_reload;
static uint32_t g_sample_cpu;
static volatile uint32_t g_sample_irqs[4]; /* PMU overflow interrupts seen, per core */

/* not in a public header; defined by dev/interrupt/arm_gic */
status_t gic_configure_interrupt(unsigned int vector, enum interrupt_trigger_mode tm,
                                 enum interrupt_polarity pol);

static inline void sample_ctr_write(uint32_t v) {
    __asm__ volatile("mcr p15, 0, %0, c14, c8, 5" ::"r"(v)); /* PMEVCNTR5 */
}

void bolt_sample_on_irq(struct arm_iframe *frame, unsigned int vector) {
    if (vector < BB_SAMPLE_SPI || vector >= BB_SAMPLE_SPI + 4)
        return;
    /* level-triggered: always acknowledge, even when disarmed, or it storms */
    __asm__ volatile("mcr p15, 0, %0, c9, c12, 3" ::"r"(1u << BB_SAMPLE_CTR)); /* PMOVSR */
    g_sample_irqs[arch_curr_cpu_num() & 3]++;
    if (!g_sample_on)
        return;
    sample_ctr_write(g_sample_reload);
    uint32_t i = atomic_add((volatile int *)&g_sample_n, 1);
    if (i < BB_SAMPLE_MAX)
        bolt_sample_buf[i] = (frame->pc & ~1u) | ((frame->spsr >> 5) & 1u);
}

static void sample_arm_this_cpu(void *unused) {
    __asm__ volatile("mcr p15, 0, %0, c14, c12, 5" ::"r"(0x11u)); /* PMEVTYPER5 = CPU_CYCLES */
    sample_ctr_write(g_sample_reload);
    __asm__ volatile("mcr p15, 0, %0, c9, c12, 1" ::"r"(1u << BB_SAMPLE_CTR)); /* PMCNTENSET */
    __asm__ volatile("mcr p15, 0, %0, c9, c14, 1" ::"r"(1u << BB_SAMPLE_CTR)); /* PMINTENSET */
    uint32_t pmcr;
    __asm__ volatile("mrc p15, 0, %0, c9, c12, 0" : "=r"(pmcr));
    __asm__ volatile("mcr p15, 0, %0, c9, c12, 0" ::"r"(pmcr | 1u)); /* E */
    __asm__ volatile("isb" ::: "memory");
}

static void sample_disarm_this_cpu(void *unused) {
    __asm__ volatile("mcr p15, 0, %0, c9, c14, 2" ::"r"(1u << BB_SAMPLE_CTR)); /* PMINTENCLR */
    __asm__ volatile("mcr p15, 0, %0, c9, c12, 2" ::"r"(1u << BB_SAMPLE_CTR)); /* PMCNTENCLR */
    __asm__ volatile("mcr p15, 0, %0, c9, c12, 3" ::"r"(1u << BB_SAMPLE_CTR)); /* PMOVSR */
    __asm__ volatile("isb" ::: "memory");
}

static void bolt_pmu_init(void);

static int sample_cmd(int argc, const console_cmd_args *argv) {
    if (argc > 2 && !strcmp(argv[1].str, "start")) {
        uint32_t period = (uint32_t)argv[2].u;
        if (period < BB_SAMPLE_MIN_PERIOD) {
            printf("bolt_sample: period must be >= %u cycles\n", BB_SAMPLE_MIN_PERIOD);
            return -1;
        }
        bolt_pmu_init(); /* program the workloads' counters now: it resets event counters */
        static bool routed;
        if (!routed) {
            /* one SPI per core (gic init routes every SPI to cpu0) */
            volatile uint32_t *itargetsr =
                (volatile uint32_t *)(BCM_GIC_BASE_VIRT + 0x1000 + 0x800 + BB_SAMPLE_SPI);
            *itargetsr = 0x08040201;
            for (unsigned i = 0; i < 4; i++) {
                gic_configure_interrupt(BB_SAMPLE_SPI + i, IRQ_TRIGGER_MODE_LEVEL,
                                        IRQ_POLARITY_ACTIVE_HIGH);
                unmask_interrupt(BB_SAMPLE_SPI + i);
            }
            routed = true;
        }
        g_sample_reload = 0u - period;
        g_sample_n = 0;
        g_sample_on = 1;
        g_bolt_sampling = 1;
        /* Keep the shell (and the workloads it runs) on the core it is on for the whole
         * session, like the workloads themselves do: one core, one PMU. */
        g_sample_cpu = arch_curr_cpu_num();
        thread_set_pinned_cpu(get_current_thread(), (int)g_sample_cpu);
        for (unsigned i = 0; i < 4; i++)
            g_sample_irqs[i] = 0;
        mp_sync_exec(MP_IPI_TARGET_ALL, 0, sample_arm_this_cpu, NULL);
        printf("bolt_sample: on, every %u cycles\n", (unsigned)period);
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1].str, "stop")) {
        g_sample_on = 0;
        g_bolt_sampling = 0;
        mp_sync_exec(MP_IPI_TARGET_ALL, 0, sample_disarm_this_cpu, NULL);
        thread_set_pinned_cpu(get_current_thread(), -1);
        uint32_t n = g_sample_n < BB_SAMPLE_MAX ? g_sample_n : BB_SAMPLE_MAX;
        printf("bolt_sample: %u samples (%u taken) buf=0x%08lx bytes=0x%x\n", (unsigned)n,
               (unsigned)g_sample_n, (unsigned long)(uintptr_t)bolt_sample_buf,
               (unsigned)(n * 4u));
        printf("bolt_sample: cpu %u; PMU interrupts per core: %u %u %u %u\n",
               (unsigned)g_sample_cpu, (unsigned)g_sample_irqs[0], (unsigned)g_sample_irqs[1],
               (unsigned)g_sample_irqs[2], (unsigned)g_sample_irqs[3]);
        return 0;
    }
    printf("usage: bolt_sample start <cycles> | stop\n");
    return -1;
}
#endif

#if WITH_LIB_CONSOLE
STATIC_COMMAND_START
STATIC_COMMAND("bolt_bench", "BOLT synthetic bare-metal workloads", &bolt_bench_cmd)
STATIC_COMMAND("bolt_dump", "dump raw memory over UART for BOLT profiling (addr_hex size_hex)", &bolt_dump_cmd)
#if BB_HAVE_WDOG
STATIC_COMMAND("wdog", "hang guard: reset the Pi unless disarmed within <seconds> (0 = off)", &wdog_cmd)
STATIC_COMMAND("bolt_sample", "PC sampling for BOLT profiles: start <cycles> | stop", &sample_cmd)
#endif
#if WITH_BOLT_PGO
STATIC_COMMAND("bolt_pgo_dump", "serialize PGO counters into a buffer, print addr/size for bolt_dump", &bolt_pgo_dump_cmd)
#endif
STATIC_COMMAND_END(bolt_bench);
#endif

APP_START(bolt_bench)
    .entry = bolt_bench_app_entry,
APP_END
