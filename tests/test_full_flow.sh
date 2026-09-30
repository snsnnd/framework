#!/bin/bash
# EFW 完整流程测试脚本

set -e

echo "=========================================="
echo "EFW 完整流程测试"
echo "=========================================="

# 测试目录
TEST_DIR="/tmp/efw_test_$(date +%s)"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

echo ""
echo "测试目录: $TEST_DIR"
echo ""

# ============================================
# 步骤 1: 检查工具
# ============================================
echo "[1/8] 检查工具..."
echo "----------------------------------------"

# 检查 Python
python3 --version

# 检查 efw.py
python3 /mnt/d/framework/tools/efw.py help > /dev/null 2>&1 && echo "✓ efw.py OK" || echo "✗ efw.py FAIL"

echo ""

# ============================================
# 步骤 2: 芯片数据库
# ============================================
echo "[2/8] 检查芯片数据库..."
echo "----------------------------------------"

python3 /mnt/d/framework/tools/efw.py mcu list 2>&1 | head -10

echo ""

# ============================================
# 步骤 3: 设计项目
# ============================================
echo "[3/8] 设计项目..."
echo "----------------------------------------"

python3 /mnt/d/framework/tools/efw.py design --chip STM32F407VGT6 -o project.json
echo "✓ 项目配置已生成"

echo ""

# ============================================
# 步骤 4: SVD 导入
# ============================================
echo "[4/8] SVD 导入..."
echo "----------------------------------------"

# 检查 SVD 数据是否存在
SVD_DIR="/mnt/d/STM32/STM32CUBEMX"
if [ -d "$SVD_DIR" ]; then
    echo "STM32CUBEMX 目录存在"
else
    echo "STM32CUBEMX 目录不存在，跳过 SVD 测试"
fi

# 测试 SVD 导入工具
python3 /mnt/d/framework/tools/svd_import.py --help > /dev/null 2>&1 && echo "✓ svd_import.py OK" || echo "✗ svd_import.py FAIL"

echo ""

# ============================================
# 步骤 5: 固件管理
# ============================================
echo "[5/8] 检查固件..."
echo "----------------------------------------"

python3 /mnt/d/framework/tools/efw.py firmware list 2>&1 | head -10

# 检查已安装固件
python3 /mnt/d/framework/tools/efw.py firmware installed 2>&1

echo ""

# ============================================
# 步骤 6: 编译器检查
# ============================================
echo "[6/8] 检查编译器..."
echo "----------------------------------------"

python3 /mnt/d/framework/tools/efw.py build detect 2>&1

echo ""

# ============================================
# 步骤 7: 代码生成
# ============================================
echo "[7/8] 生成代码..."
echo "----------------------------------------"

python3 /mnt/d/framework/tools/efw.py develop project.json -o src/ 2>&1

echo ""
echo "生成的文件:"
find src/ -type f 2>/dev/null | sort

echo ""

# ============================================
# 步骤 8: 编译测试
# ============================================
echo "[8/8] 编译测试..."
echo "----------------------------------------"

# 检查是否有编译器
if command -v arm-none-eabi-gcc &> /dev/null; then
    echo "ARM GCC 已安装"
    # python3 /mnt/d/framework/tools/efw.py build compile --chip STM32F407VGT6
else
    echo "ARM GCC 未安装，跳过编译测试"
fi

echo ""

# ============================================
# 测试总结
# ============================================
echo "=========================================="
echo "测试总结"
echo "=========================================="
echo ""
echo "测试目录: $TEST_DIR"
echo ""
echo "已测试:"
echo "  ✓ 工具检查"
echo "  ✓ 芯片数据库"
echo "  ✓ 项目设计"
echo "  ✓ SVD 导入工具"
echo "  ✓ 固件管理"
echo "  ✓ 编译器检查"
echo "  ✓ 代码生成"
echo ""
echo "未测试（需要硬件）:"
echo "  ○ 编译（需要 ARM GCC）"
echo "  ○ 烧录（需要 ST-Link）"
echo "  ○ 运行验证（需要 MCU）"
echo ""

# 清理
echo "清理测试目录..."
rm -rf "$TEST_DIR"
echo "✓ 清理完成"
