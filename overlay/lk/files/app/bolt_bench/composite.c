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
