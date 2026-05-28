/**
 * @file    moving_average.h
 * @brief   滑动均值滤波器 (Moving Average / Running Average)
 *
 * =========================================================================
 * 算法原理
 * =========================================================================
 *
 * 【核心思想】
 *   维护一个固定长度为 N 的环形缓冲区 (circular buffer)，每次新采样值到来时，
 *   用新值替换最旧的样本，重新计算总和与均值，实现 O(1) 的实时平滑。
 *
 * 【数学定义】
 *   avg(t) = (x_t + x_{t-1} + ... + x_{t-N+1}) / N
 *   即：最近 N 个采样值的算术平均
 *
 * 【增量更新公式 (O(1) 关键)】
 *   窗口未满 (count < N)：sum += new_sample
 *   窗口已满 (count = N)：sum += new_sample - oldest_sample
 *   均值：avg = sum / count
 *
 *   对比朴素遍历法 (每次重新 sum over N)：O(N) → O(1)，实际提速 N 倍
 *
 * 【为什么用滑动均值？】
 *   ① 简单：只需一个 float 数组 + 几个状态变量
 *   ② 高效：O(1) 复杂度，不受窗口大小影响
 *   ③ 可预测：输出 = 过去 N 个样本的平均，没有递归反馈，天生稳定 (BIBO)
 *   ④ 线性相位：延迟恒定为 (N-1)/2 个采样周期，容易补偿
 *
 * 【窗口大小 N 的选择】
 *   N 是唯一的调参维度——这是最重要的设计决策：
 *
 *   N=4~8   轻度平滑 | 滞后 ~2~4 采样周期
 *            适合 IMU 角速度、电机电流等高频信号 (需快速响应)
 *   N=10~20 中度平滑 | 滞后 ~5~10 采样周期
 *            适合 ADC 采样、电池电压、超声波距离等中频信号
 *   N=32~64 重度平滑 | 滞后 ~16~32 采样周期
 *            适合温度、湿度等缓变信号
 *
 *   经验法则：先确定"系统能容忍的最大延迟"，再选 N。
 *     N_max = 2 × 可容忍延迟 / 采样周期
 *     例如 100ms 延迟可接受，采样周期 10ms → N_max = 20
 *
 * 【vs 指数移动平均 (EMA / 一阶低通)】
 *   滑动均值：过去 N 个点权重相同 (矩形窗)，截止后完全遗忘
 *     → 适合需要"等权平均"的场景，阶跃响应线性
 *   EMA：越近的样本权重越大 (指数衰减)，永不彻底遗忘
 *     → 适合需要"连续衰减"的场景，计算量更小 (无需 buffer)
 *
 * 【两阶段行为】
 *   阶段① 填窗期 (count < capacity)：
 *     新样本追加到 buffer 尾部，count 递增。
 *     返回值 = 当前已有所有样本的均值（不是 N 的均值，因为样本还不够）。
 *     初始化后的前 N 次调用都处于此阶段。
 *
 *   阶段② 稳定期 (count = capacity)：
 *     新样本替换最旧的样本，增量更新 sum。
 *     返回值 = 最近 N 个样本的精确均值。
 *
 * 【使用示例】
 *   float buf[20];  // 静态分配 20 个 float 的环形缓冲区
 *   efw_moving_avg_t avg = { .buffer=buf, .capacity=20 };
 *
 *   float sample = read_adc();
 *   float filtered;
 *   efw_moving_avg_run(&avg, &sample, &filtered);
 * =========================================================================
 */

#ifndef EFW_ALGORITHM_MOVING_AVERAGE_H
#define EFW_ALGORITHM_MOVING_AVERAGE_H

#include "efw/core/common.h"

/**
 * @brief 滑动均值滤波器状态结构体
 *
 * 使用前必须由用户分配 buffer 并设置 capacity。
 * buffer 大小 = capacity × sizeof(float)，推荐静态分配（如 float buf[32]）。
 *
 * @field buffer   环形缓冲区指针：用户预先分配的 float 数组
 *                 大小必须 ≥ capacity，框架不会检查数组是否足够大
 * @field capacity 窗口大小 N：最大保留的样本数，必须 > 0 (注册时校验)
 *                 N 为 2 的幂可以利用位运算取模优化，但任意值均可正常工作
 * @field count    当前有效样本数 (内部状态，≤ capacity)
 *                 填窗期：count < capacity，每次 +1
 *                 稳定期：count = capacity，保持不变
 * @field index    下一个写入位置 (内部状态)
 *                 循环移动：0 → 1 → ... → capacity-1 → 0 → ...
 *                 总是指向 buffer 中最旧的样本 (即将被覆盖的位置)
 * @field sum      当前窗口内所有样本的总和 (内部状态，O(1) 增量更新的关键)
 *                 填窗期：sum = Σ(所有已有样本)
 *                 稳定期：sum = Σ(最近 N 个样本)
 *                 更新方式：sum = sum - 被替换的旧值 + 新值
 */
typedef struct {
    float *buffer;      /**< 环形缓冲区指针 (用户静态分配, 大小 ≥ capacity) */
    uint16_t capacity;  /**< 窗口大小 N (必须 > 0) */
    uint16_t count;     /**< 当前有效样本数 (内部状态, ≤ capacity) */
    uint16_t index;     /**< 下一个写入位置 (内部状态, 循环 0→capacity-1→0) */
    float sum;          /**< 当前窗口内样本总和 (内部状态, 增量更新用) */
} efw_moving_avg_t;

/**
 * @brief 重置滤波器状态 —— 清空所有历史数据
 *
 * 调用后滤波器回到初始状态（count=0, index=0, sum=0），
 * 下次 run 从填窗阶段重新开始。
 *
 * 调用时机：
 *   ① 切换信号源 (如 ADC1 → ADC2)，避免旧数据污染新信号
 *   ② 传感器重新标定后
 *   ③ 系统复位 / 从休眠唤醒后
 */
void efw_moving_avg_reset(efw_moving_avg_t *avg);

/**
 * @brief 执行一次滑动均值计算 (O(1) 增量算法)
 *
 * 此函数签名匹配 efw_algo_ops_t.run，可直接注册到算法管理器。
 *
 * 内部逻辑：
 *   ① 参数校验 (avg/buffer/in/out 非空, capacity>0)
 *   ② 若 count < capacity → 追加新样本 (填窗阶段)
 *   ③ 若 count = capacity → 替换最旧样本 (稳定阶段)
 *   ④ index 循环递增
 *   ⑤ result = sum / count
 *
 * @param ctx 指向 efw_moving_avg_t 的指针
 * @param in  指向 float 的指针 (新采样值，如 ADC 原始读数 3.27f)
 * @param out 指向 float 的指针 (滤波后的均值写回此处)
 * @return EFW_OK 成功, EFW_ERR_INVALID 参数非法
 */
efw_status_t efw_moving_avg_run(void *ctx, const void *in, void *out);

#endif
