#!/bin/bash
# EFW hwtest build for STM32G431RBT6 (run inside WSL Ubuntu-22.04)
set -e
ROOT=/mnt/d/framework
OUT=$ROOT/hwtest_g431/build
mkdir -p "$OUT"

CC=arm-none-eabi-gcc
CPU="-mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16"
CFLAGS="$CPU -std=c99 -include stdbool.h -O2 -g -Wall -Wextra -ffunction-sections -fdata-sections"
INC="-I$ROOT/include -I$ROOT/src -I$ROOT/hwtest_g431"

echo "== compile =="
$CC $CFLAGS $INC -c $ROOT/src/efw_all.c            -o $OUT/efw_all.o
$CC $CFLAGS $INC -c $ROOT/hwtest_g431/startup.c    -o $OUT/startup.o
$CC $CFLAGS $INC -c $ROOT/hwtest_g431/bsp.c        -o $OUT/bsp.o
$CC $CFLAGS $INC -c $ROOT/hwtest_g431/lcd.c        -o $OUT/lcd.o
$CC $CFLAGS $INC -c $ROOT/hwtest_g431/stress.c     -o $OUT/stress.o
$CC $CFLAGS $INC -c $ROOT/hwtest_g431/dashboard.c  -o $OUT/dashboard.o
$CC $CFLAGS $INC -c $ROOT/hwtest_g431/game.c       -o $OUT/game.o
$CC $CFLAGS $INC -c $ROOT/hwtest_g431/boundary.c   -o $OUT/boundary.o
$CC $CFLAGS $INC -c $ROOT/hwtest_g431/tests.c      -o $OUT/tests.o

echo "== link =="
$CC $CPU -nostartfiles \
    -T $ROOT/hwtest_g431/linker.ld \
    -Wl,--gc-sections -Wl,-Map=$OUT/hwtest.map -Wl,--print-memory-usage \
    --specs=nano.specs --specs=nosys.specs \
    -o $OUT/hwtest.elf \
    $OUT/efw_all.o $OUT/startup.o $OUT/bsp.o $OUT/lcd.o $OUT/stress.o $OUT/dashboard.o $OUT/game.o $OUT/boundary.o $OUT/tests.o -lm

echo "== size =="
arm-none-eabi-size $OUT/hwtest.elf
echo "OK: $OUT/hwtest.elf"
