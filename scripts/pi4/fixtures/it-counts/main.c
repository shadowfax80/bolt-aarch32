#include <stdint.h>

#define REG(address) (*(volatile uint32_t *)(address))
#define UART 0xfe201000u
#define PM 0xfe100000u
#ifndef NUM_CASES
#define NUM_CASES 100
#define PASS_CASES "300"
#endif
struct Case { uint32_t (*function)(uint32_t); uint32_t argument, result; };
extern struct Case cases[NUM_CASES];
extern volatile uint32_t *counter_base;
extern volatile uint32_t counter_count, instrumented;
extern uint32_t expected_counts[NUM_CASES][128];

static void puts_uart(const char *s) {
    while (*s) {
        while (REG(UART+0x18) & (1u<<5)) {}
        REG(UART) = (uint32_t)*s++;
    }
}

static void hex(uint32_t value) {
    const char *digits = "0123456789abcdef";
    char buffer[9];
    for (unsigned i=0; i<8; ++i) buffer[i]=digits[(value>>(28-4*i))&15];
    buffer[8]=0; puts_uart(buffer);
}

static void watchdog(unsigned seconds) {
    REG(PM+0x24)=0x5a000000u|(seconds<<16);
    uint32_t rstc=REG(PM+0x1c)&~(0x30u|0xff000000u);
    REG(PM+0x1c)=0x5a000000u|rstc|0x20;
}

static void finish(void) {
    __asm__ volatile("cpsid if" ::: "memory");
    while (REG(UART+0x18)&(1u<<3)) {}
    watchdog(1);
    for (;;) __asm__ volatile("wfe");
}

static void fail(unsigned id, unsigned seed, unsigned field, uint32_t expected, uint32_t actual) {
    puts_uart("BOLT_IT_COUNTS FAIL case="); hex(id);
    puts_uart(" seed="); hex(seed); puts_uart(" field="); hex(field);
    puts_uart(" expected="); hex(expected); puts_uart(" actual="); hex(actual);
    puts_uart("\r\n"); finish();
}

void state_main(void) {
    __asm__ volatile("cpsid if" ::: "memory");
    watchdog(10);
    puts_uart("BOLT_IT_COUNTS BEGIN instrumented="); hex(instrumented);
    puts_uart(" counters="); hex(counter_count); puts_uart("\r\n");
    if (!counter_count || counter_count>128) fail(0,0,999,128,counter_count);
    const uint32_t seed_low[3]={0,0xfffffff0u,0xffffffffu};
    const uint32_t seed_high[3]={0,7,0xffffffffu};
    for (unsigned id=0; id<NUM_CASES; ++id) {
        for (unsigned seed=0; seed<3; ++seed) {
            for (unsigned index=0; index<counter_count; ++index) {
                counter_base[2*index]=seed_low[seed];
                counter_base[2*index+1]=seed_high[seed];
            }
            uint32_t result=cases[id].function(cases[id].argument);
            if (result!=cases[id].result) fail(id,seed,1000,cases[id].result,result);
            for (unsigned index=0; index<counter_count; ++index) {
                uint32_t delta=instrumented ? expected_counts[id][index] : 0;
                uint32_t low=seed_low[seed]+delta;
                uint32_t high=seed_high[seed]+(low<seed_low[seed]);
                if (counter_base[2*index]!=low) fail(id,seed,2*index,low,counter_base[2*index]);
                if (counter_base[2*index+1]!=high) fail(id,seed,2*index+1,high,counter_base[2*index+1]);
            }
        }
        watchdog(10);
    }
    puts_uart("BOLT_IT_COUNTS PASS cases=" PASS_CASES "\r\n");
    finish();
}
