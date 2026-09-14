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

static uint8_t bench_src[4096] __attribute__((aligned(64)));
static uint8_t bench_dst[4096] __attribute__((aligned(64)));

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
    (void)sum;
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
    (void)cold;
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
    (void)acc;
}

__attribute__((noinline)) void bolt_bench_far_target(void) {
    /* Callee for P5 far-call experiments (optional BOLT_BENCH_FAR_PAD). */
}

__attribute__((noinline)) void bolt_bench_far_call(void) {
    bolt_bench_far_target();
    printf("bolt_bench: far_call done\n");
}

__attribute__((noinline)) void bolt_bench_memcpy(void) {
    lk_time_t t0 = arch_cycle_count();
    for (uint32_t r = 0; r < BOLT_BENCH_MEMCPY_ROUNDS; r++) {
        memcpy(bench_dst, bench_src, sizeof(bench_src));
    }
    bench_banner("memcpy", arch_cycle_count() - t0);
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
    } else if (!strcmp(name, "all")) {
        bolt_bench_hot_loop();
        bolt_bench_hot_cold();
        bolt_bench_branch_chain();
        bolt_bench_memcpy();
        bolt_bench_far_call();
    } else {
        printf("unknown workload %s\n", name);
    }
}

static int bolt_bench_cmd(int argc, const console_cmd_args *argv) {
    if (argc < 2) {
        printf("usage: bolt_bench <hot_loop|hot_cold|branch_chain|memcpy|far_call|all>\n");
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
