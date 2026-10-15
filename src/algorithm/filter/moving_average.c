/**
 * @file    moving_average.c
 * @brief   滑动均值滤波器完整实现 (O(1) 环形缓冲区增量算法)
 *
 * 本文件由 EFW_ENABLE_ALGO_MOVING_AVG 宏控制编译。
 *
 * =========================================================================
 * 算法核心：O(1) 增量均值 vs O(N) 朴素遍历
 * =========================================================================
 *
 * 【朴素方法 —— 每次重新遍历求和：O(N)】
 *   result = 0;
 *   for (i = 0; i < count; i++) result += buffer[i];
 *   result /= count;
 *   问题：窗口越大越慢，N=64 时每次 64 次浮点加法。
 *
 * 【本实现 —— 增量维护 sum：O(1)】
 *   维护一个 sum 变量 = 当前窗口内所有样本的总和。
 *   新样本到来时：
 *     sum = sum - 被替换的旧值 + 新值  （2 次浮点加减）
 *   代价：多存 1 个 float（4 字节 RAM）
 *   收益：无论 N=4 还是 N=256，每次计算量完全相同
 *
 * =========================================================================
 * 环形缓冲区 index 的 invariants（关键逻辑）
 * =========================================================================
 *
 *   index 始终指向"即将被覆盖的最旧样本"位置。
 *   每次 run 后 index 递增 1，到达 capacity 时回绕到 0。
 *
 *   例：capacity=4，依次插入 3.0, 2.5, 3.2, 2.8, 3.1
 *     Run1: buf[0]=3.0, count=1, sum=3.0, idx→1, res=3.0
 *     Run2: buf[1]=2.5, count=2, sum=5.5, idx→2, res=2.75
 *     Run3: buf[2]=3.2, count=3, sum=8.7, idx→3, res=2.9
 *     Run4: buf[3]=2.8, count=4, sum=11.5, idx→0, res=2.875  ← 窗口满
 *     Run5: sum=11.5-3.0+3.1=11.6, buf[0]=3.1, idx→1, res=2.9  ← 替换旧值
 *
 * =========================================================================
 * 窗口大小 N 的选择指南
 * =========================================================================
 *
 *   N=4~8   轻度平滑 | 滞后约 2~4 个采样周期
 *            IMU 角速度、电机电流等高频信号
 *   N=10~20 中度平滑 | 滞后约 5~10 个采样周期
 *            ADC 采样、电池电压、超声波距离
 *   N=32~64 重度平滑 | 滞后约 16~32 个采样周期
 *            温度、湿度等缓变信号
 *
 *   经验公式：N = 2 × 可容忍延迟 / 采样周期
 *   例：可容忍 100ms 延迟，采样周期 10ms → N ≤ 20
 *
 * =========================================================================
 * 精度说明（浮点累积误差）
 * =========================================================================
 *
 *   sum 通过增量更新维护（而非每次遍历重算），长时间运行后浮点舍入误差
 *   会逐渐累积。对典型嵌入式场景 (N≤64, float)，误差 < 1e-5，可忽略。
 *   若 N>1000 或需要极高精度，可定期调用 efw_moving_avg_reset() 重置。
 */

#include "efw/core/config.h"
#include "efw/algorithm/filter/moving_average.h"

#if EFW_ENABLE_ALGO_MOVING_AVG  /**< 编译开关：0 时整个文件被跳过 */

/**
 * @brief 重置滤波器 —— 清空所有历史数据
 *
 * count=0, index=0, sum=0 → 回到初始状态，下次 run 从填窗阶段开始。
 * 调用于：切换信号源、传感器重标定、系统复位/唤醒。
 */
void efw_moving_avg_reset(efw_moving_avg_t *avg) {
    if (!avg) return;       /* 空指针保护 */
    avg->count = 0;         /* 样本数归零 → 重新进入填窗阶段 */
    avg->index = 0;         /* 写入指针回到起点 */
    avg->sum = 0.0f;        /* 总和归零 */
}

/**
 * @brief 执行一次滑动均值计算 (O(1) 增量算法，可注册为 algo_ops.run)
 *
 * 两阶段逻辑：
 *   【填窗期】count < capacity：直接追加新样本，count++，sum += sample
 *   【稳定期】count = capacity：sum -= buf[index] (减旧) + buf[index]=sample (写新) + sum += sample (加新)
 *   index 循环递增，到达 capacity 回绕到 0。
 *
 * @param ctx 指向 efw_moving_avg_t (buffer/capacity/count/index/sum)
 * @param in  指向 float (新采样值)
 * @param out 指向 float (滤波后的均值写回)
 * @return EFW_OK 成功, EFW_ERR_INVALID 参数非法
 */
efw_status_t efw_moving_avg_run(void *ctx, const void *in, uint16_t in_size, void *out, uint16_t out_size) {
    efw_moving_avg_t *avg = (efw_moving_avg_t *)ctx;
    const float *sample = (const float *)in;
    float *result = (float *)out;
    if (!avg || !sample || !result) return EFW_ERR_INVALID;
    if (in_size < sizeof(float) || out_size < sizeof(float)) return EFW_ERR_RANGE;

    /* 参数校验：所有指针非空 + buffer 已分配 + capacity>0 */
    if (!avg || !avg->buffer || avg->capacity == 0 || !sample || !result)
        return EFW_ERR_INVALID;

    /* ===== 两阶段增量更新 ===== */
    if (avg->count < avg->capacity) {
        /* 阶段①：填窗期——直接追加 */
        avg->buffer[avg->index] = *sample;  /* 新样本存入当前槽位 */
        avg->sum += *sample;                /* 总和累加 (无旧值需减) */
        avg->count++;                       /* 有效样本数 +1 */
    } else {
        /* 阶段②：稳定期——增量替换 */
        avg->sum -= avg->buffer[avg->index]; /* 减旧：丢弃即将被覆盖的值 */
        avg->buffer[avg->index] = *sample;   /* 写新：覆盖最旧位置 */
        avg->sum += *sample;                 /* 加新：新值加入总和 */
        /* count 保持 = capacity */
    }

    /* ===== index 循环递增 (环形回绕) ===== */
    avg->index++;
    if (avg->index >= avg->capacity) avg->index = 0;  /* 到达末尾 → 回起点 */

    /* ===== 均值计算 ===== */
    *result = avg->sum / (float)avg->count;
    /* 填窗期：sum / count (count < capacity)
     * 稳定期：sum / capacity */

    return EFW_OK;
}

#endif /* EFW_ENABLE_ALGO_MOVING_AVG */
