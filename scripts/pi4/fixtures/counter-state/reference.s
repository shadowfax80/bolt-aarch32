// Independent assembly oracle for the complete generated leaf bodies.
// Counter addresses are supplied as absolute symbols by llvm-mc --defsym.
.syntax unified
.arch armv7-a
.section .text.arm,"ax",%progbits
.arm
 sub sp,sp,#16
 str r0,[sp]
 str r1,[sp,#4]
 str r2,[sp,#8]
 str r3,[sp,#12]
 movw r0,#:lower16:counter_arm_address
 movt r0,#:upper16:counter_arm_address
 mrs r2,cpsr
 cpsid i
 ldr r1,[r0]
 ldr r3,[r0,#4]
 adds r1,r1,#1
arm_carry:
 adc r3,r3,#0
 str r1,[r0]
 str r3,[r0,#4]
arm_restore_cpsr:
 msr cpsr_fc,r2
arm_restore_r0:
 ldr r0,[sp]
 ldr r1,[sp,#4]
 ldr r2,[sp,#8]
 ldr r3,[sp,#12]
 add sp,sp,#16
 bx lr
.section .text.thumb,"ax",%progbits
.thumb
 sub sp,sp,#16
 str.w r0,[sp]
 str.w r1,[sp,#4]
 str.w r2,[sp,#8]
 str.w r3,[sp,#12]
 movw r0,#:lower16:counter_thumb_address
 movt r0,#:upper16:counter_thumb_address
 mrs r2,cpsr
 cpsid i
 ldr.w r1,[r0]
 ldr.w r3,[r0,#4]
 adds.w r1,r1,#1
 adc r3,r3,#0
 str.w r1,[r0]
 str.w r3,[r0,#4]
 msr cpsr_fc,r2
 ldr.w r0,[sp]
 ldr.w r1,[sp,#4]
 ldr.w r2,[sp,#8]
 ldr.w r3,[sp,#12]
 add sp,sp,#16
 nop
 bx lr
