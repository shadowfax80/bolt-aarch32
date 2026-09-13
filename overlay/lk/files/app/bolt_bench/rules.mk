LOCAL_DIR := $(GET_LOCAL_DIR)

MODULE := $(LOCAL_DIR)

MODULE_DEPS += \
	lib/console \

MODULE_SRCS += \
	$(LOCAL_DIR)/bolt_bench.c \

# P4 identity rewrite is ARM-mode. Default LK ARM32 user code is Thumb.
# Rebuild with: make qemu-virt-arm32-test BOLT_BENCH_ISA=arm
ifeq ($(BOLT_BENCH_ISA),arm)
MODULE_COMPILEFLAGS += -marm
endif

include make/module.mk
