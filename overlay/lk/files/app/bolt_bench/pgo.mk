# Module-scoped profiles: frontend (legacy), IR-PGO, and post-inline CSPGO.
BOLT_PGO_KIND ?= frontend
ifneq ($(filter $(BOLT_PGO_KIND),frontend ir),$(BOLT_PGO_KIND))
$(error BOLT_PGO_KIND must be frontend or ir)
endif

ifeq ($(WITH_BOLT_CSPGO),true)
ifneq ($(BOLT_PGO_KIND),ir)
$(error CSPGO requires BOLT_PGO_KIND=ir)
endif
ifneq ($(WITH_BOLT_THINLTO),true)
$(error CSPGO requires WITH_BOLT_THINLTO=true)
endif
ifeq ($(WITH_BOLT_PGO_USE),)
$(error CSPGO collection requires an ordinary IR profile)
endif
ifeq ($(WITH_BOLT_PGO),true)
$(error ordinary and CS collection cannot be combined)
endif
MODULE_COMPILEFLAGS += -fprofile-use=$(WITH_BOLT_PGO_USE) -fcs-profile-generate -mfpu=none -mllvm -disable-vp
# LK invokes ld.lld directly: clang cannot forward these options for us.
GLOBAL_LDFLAGS += --lto-cs-profile-generate --lto-cs-profile-file=default.profraw --mllvm=-disable-vp
MODULE_DEFINES += WITH_BOLT_PGO=1
else
ifeq ($(WITH_BOLT_PGO),true)
ifneq ($(WITH_BOLT_PGO_USE),)
$(error ordinary collection and profile use cannot be combined)
endif
ifeq ($(BOLT_PGO_KIND),ir)
# Bare-metal compiler-rt excludes InstrProfilingValue.c. Disable indirect-call
# and memop value profiling, including instrumentation performed by ThinLTO.
MODULE_COMPILEFLAGS += -fprofile-generate -mllvm -disable-vp -mfpu=none
ifeq ($(WITH_BOLT_THINLTO),true)
GLOBAL_LDFLAGS += --mllvm=-disable-vp
endif
else
MODULE_COMPILEFLAGS += -fprofile-instr-generate -mfpu=none
endif
MODULE_DEFINES += WITH_BOLT_PGO=1
endif

ifneq ($(WITH_BOLT_PGO_USE),)
ifeq ($(BOLT_PGO_KIND),ir)
MODULE_COMPILEFLAGS += -fprofile-use=$(WITH_BOLT_PGO_USE)
ifeq ($(WITH_BOLT_THINLTO),true)
# Reads both ordinary and CS records from a merged IR profile. Ordinary-only
# profiles also work; they simply contain no CS records.
GLOBAL_LDFLAGS += --lto-cs-profile-file=$(WITH_BOLT_PGO_USE)
endif
else
MODULE_COMPILEFLAGS += -fprofile-instr-use=$(WITH_BOLT_PGO_USE)
endif
endif
endif

# Preserve diagnostics: an unexpected profile mismatch is not suppressed.
ifneq ($(WITH_BOLT_PGO_USE),)
MODULE_COMPILEFLAGS += -Wno-profile-instr-unprofiled
endif

ifneq ($(filter true,$(WITH_BOLT_PGO) $(WITH_BOLT_CSPGO)),)
ifeq ($(BOLT_PGO_KIND),ir)
# Post-inline counters scale with STAIR_M. Bounds are checked before dumping.
BOLT_PGO_BUFFER_SIZE ?= 1048576
else
BOLT_PGO_BUFFER_SIZE ?= 65536
endif
MODULE_DEFINES += BOLT_PGO_BUFFER_SIZE=$(BOLT_PGO_BUFFER_SIZE)
endif
