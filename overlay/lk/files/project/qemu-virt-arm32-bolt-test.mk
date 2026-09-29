# QEMU-bootable twin of rpi4-bolt-test, for debugging crashes with a single
# readable console and a debugger. Not used for measurements (QEMU's cycle and
# PMU numbers are not real). Deliberately excludes project/virtual/test.mk:
# it pulls in lib/symtab (whose generated data failed to link here) and libm.
MODULES += 	app/shell 	app/bolt_bench

include project/target/qemu-virt-arm32.mk
