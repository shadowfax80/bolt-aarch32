LOCAL_DIR := $(GET_LOCAL_DIR)

TARGET := rpi4

# project/virtual/test.mk (and its app/tests) deliberately excluded: it
# pulls in lib/libm, which compiles several routines with hardware VFP
# instructions regardless of the kernel-level ARM_WITH_VFP setting. The
# real hardware PoC target (Cortex-A55) has no FPU/NEON at all -- ported
# from lk-perf, which hit this same trap first (see its project/rpi4-test.mk).
MODULES += \
	app/shell \
	app/bolt_bench
