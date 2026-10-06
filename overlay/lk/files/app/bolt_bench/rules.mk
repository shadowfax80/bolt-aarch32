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

# Frontend/IR/CS profiling stays scoped to this module.
include $(LOCAL_DIR)/pgo.mk

# Step 7 (ThinLTO): compile just this module (bolt_bench.c + composite.c) as
# ThinLTO bitcode, not all of LK -- keeps PGO-vs-ThinLTO a one-variable
# difference and needs overlay patch 0005 (per-module MODULE_LTO in module.mk).
ifeq ($(WITH_BOLT_THINLTO),true)
MODULE_LTO := thin
# ThinLTO internalizes bolt_bench_composite (only run_one, in the same module,
# references it) into a LOCAL symbol, which BOLT then names
# "bolt_bench_composite/1" -- matching none of the exact-name --funcs-file
# entries or hook lookups the BOLT scripts use. --undefined makes lld treat it
# as externally referenced, so it stays a GLOBAL entry point as in every other
# variant.
GLOBAL_LDFLAGS += --undefined=bolt_bench_composite
GLOBAL_LDFLAGS += --undefined=bolt_bench_stair_kernel
endif

# Sites in the stair kernel = 64 * STAIR_M (see bolt_bench.c); the footprint sweep varies it.
# Must come before the module.mk include, which consumes MODULE_DEFINES.
STAIR_M ?= 10
MODULE_DEFINES += STAIR_M=$(STAIR_M)
STAIR_X ?= 0
MODULE_DEFINES += STAIR_X=$(STAIR_X)

include make/module.mk
