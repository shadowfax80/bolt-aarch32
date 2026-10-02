#include <stdint.h>

extern void counter_arm(void), counter_thumb(void);
extern void probe_state(void (*function)(void), uint32_t flags, uint32_t irq_mask);
extern volatile uint32_t *counter_slots[2];
extern volatile uint32_t expected_delta;
volatile uint32_t observed[19];

#define REG(address) (*(volatile uint32_t *)(address))
#define UART 0xfe201000u
#define PM 0xfe100000u

static void puts_uart(const char *s) {
    while (*s) {
        while (REG(UART + 0x18) & (1u << 5)) {}
        REG(UART) = (uint32_t)*s++;
    }
}

static void hex(uint32_t x) {
    const char *digits = "0123456789abcdef";
    char buffer[9];
    for (unsigned i = 0; i < 8; ++i) buffer[i] = digits[(x >> (28 - 4*i)) & 15];
    buffer[8] = 0;
    puts_uart(buffer);
}

static void watchdog(unsigned seconds) {
    REG(PM + 0x24) = 0x5a000000u | (seconds << 16);
    uint32_t rstc = REG(PM + 0x1c) & ~(0x30u | 0xff000000u);
    REG(PM + 0x1c) = 0x5a000000u | rstc | 0x20;
}

static void finish(void) {
    __asm__ volatile("cpsid if" ::: "memory");
    while (REG(UART + 0x18) & (1u << 3)) {}
    watchdog(1); // Return to the resident loader without changing the SD card.
    for (;;) __asm__ volatile("wfe");
}

static void fail(unsigned case_id, unsigned field, uint32_t expected, uint32_t actual) {
    puts_uart("BOLT_COUNTER_STATE FAIL case="); hex(case_id);
    puts_uart(" field="); hex(field);
    puts_uart(" expected="); hex(expected);
    puts_uart(" actual="); hex(actual); puts_uart("\r\n");
    finish();
}

void state_main(void) {
    // The chainloader leaves PL011 at 115200, caches/MMU off, other cores parked.
    // There are no enabled interrupt sources in this fixture; no ISR is exercised.
    watchdog(10);
    uint32_t cpsr;
    __asm__ volatile("mrs %0,cpsr" : "=r"(cpsr));
    puts_uart("BOLT_COUNTER_STATE BEGIN mode="); hex(cpsr & 31);
    puts_uart(" delta="); hex(expected_delta); puts_uart("\r\n");
    if ((cpsr & 31) != 0x1a && (cpsr & 31) != 0x13) fail(0,100,0x1a,cpsr & 31);
    const uint32_t low[4] = {0,0xffffffffu,0xfffffffeu,0xffffffffu};
    const uint32_t high[4] = {0,7,0,0xffffffffu};
    for (unsigned mode = 0; mode < 2; ++mode) {
        for (unsigned pattern = 0; pattern < 32; ++pattern) {
            for (unsigned irq = 0; irq < 2; ++irq) {
                for (unsigned seed = 0; seed < 4; ++seed) {
                    unsigned id = (mode << 8) | (pattern << 3) | (irq << 2) | seed;
                    volatile uint32_t *counter = counter_slots[mode];
                    counter[0] = low[seed]; counter[1] = high[seed];
                    uint32_t flags = ((pattern & 15u) << 28) | ((pattern >> 4) << 27)
                                   | (((~pattern) & 15u) << 16);
                    probe_state(mode ? counter_thumb : counter_arm, flags, irq);
                    for (unsigned r = 0; r < 13; ++r) {
                        uint32_t value = ((0xa000u + r) << 16) | (0x1000u + r);
                        if (observed[r] != value) fail(id,r,value,observed[r]);
                    }
                    if (observed[13] != observed[18]) fail(id,13,observed[18],observed[13]);
                    if (observed[14] != observed[16]) fail(id,14,observed[16],observed[14]);
                    if (observed[16] & 7) fail(id,16,0,observed[16] & 7);
                    // Back in ARM state: compare the entire CPSR, including IRQ/FIQ/control.
                    if (observed[15] != observed[17]) fail(id,15,observed[17],observed[15]);
                    // Also prove the harness really established the requested flag/IRQ state.
                    if ((observed[17] & 0xf80f0080u) != (flags | (irq << 7)))
                        fail(id,17,flags | (irq << 7),observed[17] & 0xf80f0080u);
                    uint32_t want_low = low[seed] + expected_delta;
                    uint32_t want_high = high[seed] + (want_low < low[seed]);
                    if (counter[0] != want_low) fail(id,20,want_low,counter[0]);
                    if (counter[1] != want_high) fail(id,21,want_high,counter[1]);
                }
            }
        }
        puts_uart(mode ? "BOLT_COUNTER_STATE Thumb cases=256\r\n"
                       : "BOLT_COUNTER_STATE ARM cases=256\r\n");
        watchdog(10);
    }
    puts_uart("BOLT_COUNTER_STATE PASS cases=512\r\n");
    finish();
}
