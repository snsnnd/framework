#!/bin/bash
# Host-native build of the EFW hwtest suite (behavioral comparison vs MCU).
# Runs the SAME tests.c/stress.c/dashboard.c logic on the host CPU.
set -e
ROOT=/mnt/d/framework
OUT=$ROOT/hwtest_g431/build
mkdir -p "$OUT"

CFLAGS="-std=c99 -include stdbool.h -O2 -Wall -DHOST_BUILD"
INC="-I$ROOT/include -I$ROOT/src -I$ROOT/hwtest_g431"

gcc $CFLAGS $INC -c $ROOT/src/efw_all.c           -o $OUT/host_efw_all.o
gcc $CFLAGS $INC -c $ROOT/hwtest_g431/tests.c     -o $OUT/host_tests.o
gcc $CFLAGS $INC -c $ROOT/hwtest_g431/stress.c    -o $OUT/host_stress.o
gcc $CFLAGS $INC -c $ROOT/hwtest_g431/dashboard.c -o $OUT/host_dashboard.o
gcc $CFLAGS $INC -c $ROOT/hwtest_g431/game.c      -o $OUT/host_game.o
gcc $CFLAGS $INC -c $ROOT/hwtest_g431/boundary.c  -o $OUT/host_boundary.o
gcc $CFLAGS $INC -c $ROOT/hwtest_g431/host_bsp.c  -o $OUT/host_bsp.o

gcc -o $OUT/hwtest_host \
    $OUT/host_efw_all.o $OUT/host_tests.o $OUT/host_stress.o \
    $OUT/host_dashboard.o $OUT/host_game.o $OUT/host_boundary.o $OUT/host_bsp.o -lm
echo "OK: $OUT/hwtest_host"
