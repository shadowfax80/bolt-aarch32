# QEMU-bootable twin of rpi4-bolt-test, for debugging crashes with a single
# readable console and a debugger. Not used for measurements (QEMU's cycle and
# PMU numbers are not real). Deliberately excludes project/virtual/test.mk:
# it pulls in lib/symtab (whose generated data failed to link here) and libm.
MODULES += 	app/shell 	app/bolt_bench

include project/target/qemu-virt-arm32.mk

# No FPU/NEON: the target has none (see overlay patch 0008).
ARM_WITHOUT_VFP_NEON := true
GLOBAL_COMPILEFLAGS += -mfpu=none
# Float modules (lib/gfx): arch/arm/toolchain.mk appends -mfpu=neon later;
# an override assignment wins over those appends.
override ARCH_arm_COMPILEFLAGS_FLOAT := -mfpu=none
# lib/gfx (virtio GPU) needs soft-float helpers that are not linked; drop it
# (overlay/lk/patches/0010).
BOLT_NO_VIRTIO_GPU := true
