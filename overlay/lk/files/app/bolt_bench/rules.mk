LOCAL_DIR := $(GET_LOCAL_DIR)

MODULE := $(LOCAL_DIR)

MODULE_DEPS += \
	lib/console \

MODULE_SRCS += \
	$(LOCAL_DIR)/bolt_bench.c \
	$(LOCAL_DIR)/composite.c \

# P4 identity rewrite is ARM-mode. Default LK ARM32 user code is Thumb.
# Rebuild with: make qemu-virt-arm32-test BOLT_BENCH_ISA=arm
ifeq ($(BOLT_BENCH_ISA),arm)
MODULE_COMPILEFLAGS += -marm
endif

# Step 6 (PGO): instrument just this module with clang's counter-based PGO,
# not all of LK. Needs libpgo_rt_baremetal.a on the final link line for
# __llvm_profile_get_size_for_buffer()/__llvm_profile_write_buffer() --
# passed via EXTRA_OBJS by scripts/build-lk-aarch32.sh, not from here,
# since rules.mk has no path back to the toolchain's BASE-specific build
# output directory.
ifeq ($(WITH_BOLT_PGO),true)
MODULE_COMPILEFLAGS += -fprofile-instr-generate
MODULE_DEFINES += WITH_BOLT_PGO=1
endif

include make/module.mk
