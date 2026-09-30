/* Second translation unit for bolt_bench's "composite" workload.
 *
 * Every other bench is single-file, so ThinLTO has nothing cross-module to
 * actually optimize -- everything a single clang -O2 invocation can see is
 * already visible without LTO. This workload's hot path
 * (composite_process, called every iteration) and cold path
 * (composite_report_cold, called rarely) live here; bolt_bench.c's
 * bolt_bench_composite() drives the loop and calls into both, so those
 * calls cross a real translation-unit boundary that only LTO -- not a
 * single compile -- can see through.
 */
#include <stdint.h>
#include <stdio.h>

/* The hot path is deliberately NOT noinline: unlike the other benches (which
 * need distinct symbols so BOLT can instrument them), this workload exists to
 * measure whether the compiler can inline composite_process into the driver
 * loop in bolt_bench.c -- possible only across the TU boundary with LTO. */
static uint32_t composite_transform(uint32_t x) {
    return (x * 2654435761u) ^ (x >> 15);
}

uint32_t composite_process(uint32_t x) {
    return composite_transform(x) + (x << 1);
}

/* Cold path stays out of line so PGO/BOLT have a real cold function to place. */
__attribute__((noinline)) void composite_report_cold(uint32_t code) {
    printf("bolt_bench: composite cold report acc=0x%x\n", code);
}

/* --- stair helper (see bolt_bench.c) ---------------------------------------
 * Lives in this TU so the kernel's call crosses a boundary only LTO can inline
 * through. The branch has a per-SITE bias: even sites take THEN ~98% of the time,
 * odd sites ~2%. Each site has its own pseudo-random stream, so outcomes are
 * data-dependent yet strongly biased and well predicted -- what layout removes is
 * fetch footprint and taken branches, not mispredictions. Both arms are ~70 bytes
 * of independent arithmetic; the empty asm keeps each a real block, not a select. */
#ifndef STAIR_M
#define STAIR_M 10
#endif
#ifndef STAIR_X
#define STAIR_X 0
#endif
#define STAIR_SITES (64u * STAIR_M + 16u * STAIR_X)
static uint32_t stair_state[STAIR_SITES];

void bolt_bench_stair_init(void) {
    for (uint32_t i = 0; i < STAIR_SITES; i++) {
        stair_state[i] = i * 2654435761u + 12345u;
    }
}

uint32_t bolt_bench_stair_step(uint32_t x, uint32_t site) {
    uint32_t s = stair_state[site] * 1664525u + 1013904223u;
    stair_state[site] = s;
    uint32_t r = s >> 24; /* uniform byte */
    uint32_t bias = (site & 1u) ? 5u : 250u;
    uint32_t t = x;
    if (r < bias) {
        __asm__ volatile("");
        t *= 0x9E3779B1u;
        t ^= t >> 15;
        t += s >> 8;
        t *= 0x85EBCA6Bu;
        t ^= t >> 13;
        t = (t << 5) | (t >> 27);
        t ^= s;
        t *= 0xC2B2AE35u;
        t ^= t >> 16;
        t += 0x1234567u;
        t = (t ^ (t >> 7)) * 0x27D4EB2Fu;
        t ^= s >> 3;
        t *= 0x165667B1u;
        t ^= t >> 11;
        return t + 1u;
    }
    __asm__ volatile("");
    t ^= 0xA5A5A5A5u;
    t += s << 3;
    t *= 0xD3A2646Cu;
    t ^= t >> 12;
    t = (t << 9) | (t >> 23);
    t += s;
    t *= 0xFD7046C5u;
    t ^= t >> 14;
    t -= 0x7654321u;
    t = (t ^ (t >> 5)) * 0xB55A4F09u;
    t ^= s >> 6;
    t *= 0x6C078965u;
    t ^= t >> 9;
    return t + 2u;
}
