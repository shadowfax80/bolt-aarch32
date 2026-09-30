#!/usr/bin/env python3
"""Derive the fast-upload chainloader main.c from lk-perf's pi4-serialboot main.c
(upstream commit b40f57e). Re-runnable: it always starts from main.c.orig."""
import os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
orig = os.path.join(HERE, "main.c.orig")
dst = os.path.join(HERE, "main.c")
if not os.path.exists(orig):
    shutil.copy(dst, orig)
t = open(orig, encoding="utf-8").read()
NL = chr(92) + "n"


def sub(old, new):
    global t
    old = old.replace("@NL@", NL)
    new = new.replace("@NL@", NL)
    assert t.count(old) == 1, (t.count(old), old[:70])
    t = t.replace(old, new)


# ---- header comment: document the new mode --------------------------------------------
sub(''' *   Pi   -> "CRC OK, jumping to 0x00008000@NL@" and jumps,
 *           or "ER ..." and goes back to waiting
''', ''' *   Pi   -> "CRC OK, jumping to 0x00008000@NL@" and jumps,
 *           or "ER ..." and goes back to waiting
 *
 * FAST MODE (this variant): the header magic "LKB3" instead of "LKBT" asks for the
 * payload at 3,000,000 baud. Everything else -- the prompt, the header, "OK", every
 * result line -- stays at 115200, so a failed fast transfer is always diagnosable and
 * the old "LKBT" path is untouched:
 *   host -> "LKB3" <size> <crc32>          (115200)
 *   Pi   -> "OK@NL@", then switches to 3 Mbaud, waits FAST_SETTLE_MS, drains the RX FIFO
 *   host -> switches to 3 Mbaud, waits > FAST_SETTLE_MS, sends <size> bytes
 *   Pi   -> stores the bytes with no per-byte work (the loader runs with its caches
 *           off: a bitwise CRC per byte cannot keep up with a byte every 3.3 us),
 *           notes UART overrun/framing/parity/break flags, waits FAST_TAIL_MS, switches
 *           back to 115200, then CRCs the received bytes from memory with a lookup table.
 *   host -> switches back to 115200 within FAST_TAIL_MS after its last byte
 *   Pi   -> "CRC OK, jumping ..." or "ER overrun/timeout/crc ..." (115200)
''')

# ---- platform switch (QEMU raspi2b protocol test) --------------------------------------
sub("#define PERIPHERAL_BASE 0xFE000000u\n",
    "#ifdef PLATFORM_QEMU_RPI2\n"
    "#define PERIPHERAL_BASE 0x3F000000u   /* QEMU raspi2b: protocol test only */\n"
    "#else\n"
    "#define PERIPHERAL_BASE 0xFE000000u\n"
    "#endif\n")
sub("#define UART_CLOCK_HZ 48000000u\n",
    "#define UART_CLOCK_HZ 48000000u\n"
    "\n"
    "// PL011 divisors: IBRD = clock / (16 * baud), FBRD = round(frac * 64).\n"
    "// 48 MHz / (16 * 115200) = 26.0417 -> 26, 3.  48 MHz / (16 * 3000000) = 1.0 -> 1, 0\n"
    "// (exact: the same divisor LK already uses successfully at 3 Mbaud with this adapter).\n"
    "#define BAUD_SLOW_IBRD 26u\n"
    "#define BAUD_SLOW_FBRD 3u\n"
    "#define BAUD_FAST_IBRD 1u\n"
    "#define BAUD_FAST_FBRD 0u\n"
    "#define FAST_SETTLE_MS 250u   /* after \"OK\": Pi at 3M, ignores the host's baud-change noise */\n"
    "#define FAST_TAIL_MS   300u   /* after the last byte: both sides return to 115200 */\n"
    "#define DR_ERR_MASK    0xF00u /* framing, parity, break, overrun bits of a PL011 DR read */\n")

# ---- uart_init: baud from the constants; mailbox/GPIO only on the real Pi -------------------
sub('''    gpio_uart0_pins();
    mbox_set_uart_clock();

    // 48000000 / (16 * 115200) = 26.0417 -> IBRD=26, FBRD=round(0.0417*64)=3
    UART0_IBRD = 26;
    UART0_FBRD = 3;
''', '''#ifndef PLATFORM_QEMU_RPI2
    gpio_uart0_pins();
    mbox_set_uart_clock();
#endif

    UART0_IBRD = BAUD_SLOW_IBRD;
    UART0_FBRD = BAUD_SLOW_FBRD;
''')

# ---- new helpers after uart_flush / timer ------------------------------------------------
sub('''static uint32_t crc32_update(uint32_t crc, uint8_t byte) {
    crc ^= byte;
    for (int i = 0; i < 8; i++) {
        crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1u));
    }
    return crc;
}
''', '''static uint32_t crc32_update(uint32_t crc, uint8_t byte) {
    crc ^= byte;
    for (int i = 0; i < 8; i++) {
        crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1u));
    }
    return crc;
}

// Table-driven CRC-32 (IEEE), for the readback pass: with the caches off the bitwise loop
// costs several microseconds per byte. Built once at run time into .bss.
static uint32_t crc_table[256];

static void crc32_init_table(void) {
    for (uint32_t n = 0; n < 256; n++) {
        uint32_t c = n;
        for (int k = 0; k < 8; k++) {
            c = (c >> 1) ^ (0xEDB88320u & -(c & 1u));
        }
        crc_table[n] = c;
    }
}

static uint32_t crc32_buf(const volatile uint8_t *p, uint32_t n) {
    uint32_t crc = 0xFFFFFFFFu;
    for (uint32_t i = 0; i < n; i++) {
        crc = crc_table[(crc ^ p[i]) & 0xFFu] ^ (crc >> 8);
    }
    return ~crc;
}

static void delay_ms(uint32_t ms, uint64_t one_sec) {
    uint64_t start = timer_now();
    uint64_t ticks = (one_sec / 1000u) * ms;
    while (timer_now() - start < ticks) {}
}

static void uart_drain_rx(void) {
    while (!(UART0_FR & FR_RXFE)) {
        (void)UART0_DR;
    }
}

// Change the baud rate. Waits for TX to drain, then disables the UART, writes the divisor
// (LCRH must be written after IBRD/FBRD to latch it) and re-enables it.
static void uart_set_baud(uint32_t ibrd, uint32_t fbrd) {
    uart_flush();
    UART0_CR = 0;
    UART0_IBRD = ibrd;
    UART0_FBRD = fbrd;
    UART0_LCRH = (1 << 4) | (3 << 5);
    UART0_CR = (1 << 0) | (1 << 8) | (1 << 9);
}

// Fast receive: store bytes as they arrive and do nothing else per byte. `errs` collects the
// error bits of every DR read, so a dropped byte (FIFO overrun) is reported as such instead of
// only as a CRC mismatch. The timer is read only while the FIFO is empty, and the idle timer
// restarts on every byte. Returns the number of bytes stored.
static uint32_t rx_fast(volatile uint8_t *dst, uint32_t size, uint64_t idle_limit,
                        uint32_t *errs) {
    uint32_t got = 0, e = 0;
    uint64_t idle_since = 0;
    while (got < size) {
        if (!(UART0_FR & FR_RXFE)) {
            uint32_t v = UART0_DR;
            e |= v;
            dst[got++] = (uint8_t)v;
            idle_since = 0;
        } else {
            uint64_t now = timer_now();
            if (idle_since == 0) {
                idle_since = now;
            } else if (now - idle_since > idle_limit) {
                break;
            }
        }
    }
    *errs = e & DR_ERR_MASK;
    return got;
}
''')

# crc32_update above uses nothing from timer; but delay_ms/rx_fast need timer_now, which is defined
# earlier (before uart_getc_timeout), so the insertion point is fine.

# ---- header: accept LKBT and LKB3 -------------------------------------------------------
sub('''static int wait_for_header(uint64_t one_sec, uint32_t *size, uint32_t *crc) {
    static const char magic[4] = { 'L', 'K', 'B', 'T' };
    int matched = 0;
    uint64_t last_prompt = timer_now() - one_sec;

    while (matched < 4) {
        if (!(UART0_FR & FR_RXFE)) {
            char c = (char)(UART0_DR & 0xFF);
            if (c == magic[matched]) {
                matched++;
            } else {
                matched = (c == magic[0]) ? 1 : 0;
            }
''', '''static int wait_for_header(uint64_t one_sec, uint32_t *size, uint32_t *crc, int *fast) {
    static const char magic[4] = { 'L', 'K', 'B', 'T' };
    int matched = 0;
    uint64_t last_prompt = timer_now() - one_sec;

    *fast = 0;
    while (matched < 4) {
        if (!(UART0_FR & FR_RXFE)) {
            char c = (char)(UART0_DR & 0xFF);
            if (matched == 3 && c == '3') {
                *fast = 1;              /* "LKB3": payload at 3 Mbaud */
                matched = 4;
            } else if (c == magic[matched]) {
                matched++;
            } else {
                matched = (c == magic[0]) ? 1 : 0;
            }
''')

# ---- main loop -------------------------------------------------------------------------
sub("void boot_main(uint32_t r0, uint32_t r1, uint32_t r2) {\n    uart_init();\n",
    "void boot_main(uint32_t r0, uint32_t r1, uint32_t r2) {\n    uart_init();\n    crc32_init_table();\n")
sub('''        uint32_t size, want_crc;
        if (wait_for_header(one_sec, &size, &want_crc) < 0) {''',
    '''        uint32_t size, want_crc;
        int fast;
        if (wait_for_header(one_sec, &size, &want_crc, &fast) < 0) {''')

sub('''        uart_puts("OK@NL@");

        volatile uint8_t *dst = (volatile uint8_t *)PAYLOAD_ADDR;
        uint32_t crc = 0xFFFFFFFFu;
        uint32_t got = 0;
        while (got < size) {''', '''        uart_puts("OK@NL@");

        volatile uint8_t *dst = (volatile uint8_t *)PAYLOAD_ADDR;
        if (fast) {
            uint32_t errs = 0;
            uart_set_baud(BAUD_FAST_IBRD, BAUD_FAST_FBRD);
            delay_ms(FAST_SETTLE_MS, one_sec);
            uart_drain_rx();            /* discard whatever the host's baud change produced */
            uint32_t n = rx_fast(dst, size, 2 * one_sec, &errs);
            delay_ms(FAST_TAIL_MS, one_sec);
            uart_set_baud(BAUD_SLOW_IBRD, BAUD_SLOW_FBRD);
            uart_drain_rx();
            if (errs) {
                uart_puts("ER overrun/framing flags ");
                uart_puthex(errs);
                uart_puts(" after ");
                uart_puthex(n);
                uart_puts(" bytes@NL@");
                continue;
            }
            if (n < size) {
                uart_puts("ER timeout after ");
                uart_puthex(n);
                uart_puts(" bytes@NL@");
                continue;
            }
            uint32_t mcrc = crc32_buf(dst, size);
            if (mcrc != want_crc) {
                uart_puts("ER crc got ");
                uart_puthex(mcrc);
                uart_puts(" want ");
                uart_puthex(want_crc);
                uart_puts("@NL@");
                continue;
            }
            uart_puts("CRC OK, jumping to ");
            uart_puthex(PAYLOAD_ADDR);
            uart_puts("@NL@");
            uart_flush();
            jump_to_payload(r0, r1, r2, PAYLOAD_ADDR);
        }

        uint32_t crc = 0xFFFFFFFFu;
        uint32_t got = 0;
        while (got < size) {''')

open(dst, "w", encoding="utf-8", newline="\n").write(t)
print("patched main.c:", t.count("\n"), "lines")
