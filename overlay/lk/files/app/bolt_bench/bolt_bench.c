#include <app.h>
#include <arch/ops.h>
#include <lib/cmdline.h>
#include <lib/console.h>
#include <lk/console_cmd.h>
#include <lk/debug.h>
#include <stdio.h>
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
 * here that reliably keeps a pure-arithmetic loop's body in the binary. */
static volatile uint32_t g_bolt_bench_sink;

static void bench_banner(const char *name, lk_time_t cycles) {
    printf("bolt_bench: %s done (%llu cycles)\n", name, (unsigned long long)cycles);
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

__attribute__((noinline)) void bolt_bench_far_target(void) {
    /* Callee for P5 far-call experiments (optional BOLT_BENCH_FAR_PAD). */
}

__attribute__((noinline)) void bolt_bench_far_call(void) {
    bolt_bench_far_target();
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
    (void)y;
    (void)z;
#else
    /* IT encoding is Thumb-only; ARM-mode P4 builds skip this workload. */
    printf("bolt_bench: it_cond skipped (ARM mode)\n");
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
    lk_time_t t0 = arch_cycle_count();
    for (uint32_t r = 0; r < BOLT_BENCH_MEMCPY_ROUNDS; r++) {
        memcpy(bench_dst, bench_src, sizeof(bench_src));
    }
    bench_banner("memcpy", arch_cycle_count() - t0);
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
    } else if (!strcmp(name, "all")) {
        bolt_bench_hot_loop();
        bolt_bench_hot_cold();
        bolt_bench_branch_chain();
        bolt_bench_memcpy();
        bolt_bench_far_call();
        bolt_bench_it_cond();
        bolt_bench_interwork();
        bolt_bench_switch();
        bolt_bench_spill_ret();
        bolt_bench_litpool();
        bolt_bench_indirect_call();
        bolt_bench_interwork_tail();
        bolt_bench_regpressure();
        bolt_bench_hotcold_split();
        bolt_bench_icf();
        bolt_bench_shrinkwrap();
    } else {
        printf("unknown workload %s\n", name);
    }
}

static int bolt_bench_cmd(int argc, const console_cmd_args *argv) {
    if (argc < 2) {
        printf("usage: bolt_bench <hot_loop|hot_cold|branch_chain|memcpy|far_call|it_cond|interwork|switch|spill_ret|litpool|indirect_call|interwork_tail|regpressure|hotcold_split|icf|shrinkwrap|all>\n");
        return -1;
    }
    run_one(argv[1].str);
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

#if WITH_LIB_CONSOLE
STATIC_COMMAND_START
STATIC_COMMAND("bolt_bench", "BOLT synthetic bare-metal workloads", &bolt_bench_cmd)
STATIC_COMMAND_END(bolt_bench);
#endif

APP_START(bolt_bench)
    .entry = bolt_bench_app_entry,
APP_END
