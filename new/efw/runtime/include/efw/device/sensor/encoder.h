/**
 * @file    encoder.h
 * @brief   编码器传感器的标准化数据结构
 *
 * =========================================================================
 * 编码器是什么？
 * =========================================================================
 *
 *   编码器是测量旋转运动的传感器，通常安装在电机轴上或车轮上。
 *   它输出脉冲信号，控制器通过计数脉冲来推算角度、位置和速度。
 *
 *   两种主要类型：
 *     ① 增量式编码器 (Incremental)：输出 A/B 两相脉冲，
 *        通过相位差判断方向，通过脉冲数计算角度增量。
 *        需要"零位校准"才能获得绝对位置。
 *        优点：便宜，分辨率高。缺点：断电后位置丢失。
 *
 *     ② 绝对式编码器 (Absolute)：每个位置有唯一的编码（如格雷码），
 *        上电即可读取绝对角度，不需要零位校准。
 *        优点：断电位置不丢失。缺点：较贵，分辨率可能较低。
 *
 *   典型应用：
 *     - 电机转速测量（speed 字段）
 *     - 车轮里程计（position 字段累积）
 *     - 机器人关节角度控制
 *
 * =========================================================================
 * 各字段物理含义
 * =========================================================================
 *
 *   count    — 脉冲计数值 (int32_t)
 *              增量式编码器：当前累计的脉冲数（正转+1，反转-1）
 *              绝对式编码器：当前绝对位置编码值
 *              ★ 这是最原始的读数，所有其他值都从此推导
 *
 *   position — 位置 (float)
 *              从 count 换算的物理位置。单位由实现定义：
 *              角度：度(°) 或弧度(rad)
 *              距离：米(m) 或毫米(mm)
 *              换算公式：position = count × (每脉冲对应的物理量)
 *              例如编码器 1000 线/圈，轮径 50mm →
 *              每脉冲距离 = π×50mm / 1000
 *
 *   speed    — 速度 (float)
 *              从 position 的时间差分计算：
 *              speed = (position_now - position_prev) / dt
 *              单位由实现定义：m/s, mm/s, RPM(转/分), °/s
 *              通常由上层算法（如编码器速度观测器）填充
 */

#ifndef EFW_SENSOR_ENCODER_H
#define EFW_SENSOR_ENCODER_H

#include "efw/core/common.h"

/**
 * @brief 编码器传感器数据结构
 *
 * @field count    原始脉冲计数值 (int32_t)
 *                 正转 → 递增，反转 → 递减
 *                 这是编码器最底层、最直接的读数
 * @field position 换算后的物理位置 (float)
 *                 由 count 乘以换算系数得到
 *                 单位示例：度(°)、弧度(rad)、米(m)、毫米(mm)
 * @field speed    当前速度 (float)
 *                 由 position 的时间差分计算
 *                 单位示例：m/s, RPM(转/分), °/s
 */
typedef struct {
    int32_t count;      /**< 原始脉冲计数 */
    float position;     /**< 物理位置 (count × 换算系数) */
    float speed;        /**< 当前速度 (position 时间差分) */
} efw_encoder_data_t;

/**
 * @brief 读取编码器传感器数据
 *
 * 内部委托给通用 efw_sensor_read()。
 * 用户需要在注册的编码器传感器的 read 回调中填充 count/position/speed。
 *
 * @param name 传感器注册名称 (如 "enc_left", "enc_right")
 * @param out  输出数据指针 (efw_encoder_data_t*，不能为空)
 * @return EFW_OK 成功, EFW_ERR_INVALID 参数错误
 */
efw_status_t efw_encoder_read(const char *name, efw_encoder_data_t *out);

#endif
