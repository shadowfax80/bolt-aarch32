// Review fixture: flags are live after CBZ on both successors.
// THUMB_ENTRY additionally reproduces odd e_entry translation failure.
.syntax unified
.cpu cortex-a9
.text
.ifdef THUMB_ENTRY
.thumb
.else
.arm
.endif
.global _start
.type _start,%function
.ifdef THUMB_ENTRY
.thumb_func
.endif
_start:
.ifdef THUMB_ENTRY
  bl probe
.else
  blx probe
.endif
  bx lr
.size _start, .-_start
.thumb
.global probe
.type probe,%function
.thumb_func
probe:
  cmp r1, #0
  cbz r0, .Ltarget
  bne .Lwrong
  mov.w r0, #7
  bx lr
.Ltarget:
  bne .Lwrong
  mov.w r0, #9
  bx lr
.Lwrong:
  mov.w r0, #3
  bx lr
.size probe, .-probe
