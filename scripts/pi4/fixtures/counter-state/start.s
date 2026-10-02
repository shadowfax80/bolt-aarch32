.syntax unified
.arch armv7-a
.arm
.section .text.start,"ax",%progbits
.global _start
.type _start,%function
_start:
 cpsid if
 ldr sp,=0x00800000
 bl state_main
1: wfe
 b 1b
.size _start,.-_start
.ltorg

.text
.global counter_arm
.type counter_arm,%function
counter_arm:
 bx lr
.size counter_arm,.-counter_arm
.thumb
.balign 4
.global counter_thumb
.type counter_thumb,%function
.thumb_func
counter_thumb:
 nop // Four bytes allow the original entry to hold an explicit B.W redirect.
 bx lr
.size counter_thumb,.-counter_thumb

.arm
.balign 4
// r0 = function, r1 = NZCV/Q/GE bits, r2 = requested IRQ mask.
// All r0-r12 have distinct sentinels while the generated counter executes.
.global probe_state
.type probe_state,%function
probe_state:
 push {r4-r11,lr}
 sub sp,sp,#12
 mrs r3,cpsr
 str r3,[sp]
 str r0,[sp,#8]
 // Establish IRQ state before setting flags (the comparison changes NZCV).
 cmp r2,#0
 beq 1f
 cpsid i
 b 2f
1: cpsie i
2: msr cpsr_fs,r1
 mrs r2,cpsr
 str r2,[sp,#4]
 ldr r3,=observed
 str sp,[r3,#64]
 str r2,[r3,#68]
 ldr r2,=probe_return
 str r2,[r3,#72]
 ldr lr,[sp,#8]
 .macro seed reg,number
 movw \reg,#(0x1000+\number)
 movt \reg,#(0xa000+\number)
 .endm
 seed r0,0
 seed r1,1
 seed r2,2
 seed r3,3
 seed r4,4
 seed r5,5
 seed r6,6
 seed r7,7
 seed r8,8
 seed r9,9
 seed r10,10
 seed r11,11
 seed r12,12
 blx lr
probe_return:
 // These first three instructions preserve flags and capture every GPR/LR/SP.
 stmdb sp!,{r0-r12,lr}
 mrs r0,cpsr
 add r1,sp,#56
 ldr r2,=observed
 str r1,[r2,#56]
 str r0,[r2,#60]
 mov r0,sp
 mov r1,#14
3: ldr r3,[r0],#4
 str r3,[r2],#4
 subs r1,r1,#1
 bne 3b
 add sp,sp,#56
 ldr r0,[sp]
 msr cpsr_fc,r0
 add sp,sp,#12
 pop {r4-r11,pc}
.size probe_state,.-probe_state
.ltorg

.data
.balign 8
.global counter_slots
.type counter_slots,%object
counter_slots:
 .word dummy_counters,dummy_counters+8
.size counter_slots,.-counter_slots
.global expected_delta
.type expected_delta,%object
expected_delta:
 .word 0
.size expected_delta,.-expected_delta
dummy_counters:
 .quad 0,0
