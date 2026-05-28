/**
 * @file    ultrasonic.c
 * @brief   超声波传感器读取 —— 对通用 efw_sensor_read() 的类型安全包装
 *
 * 本文件由 EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_ULTRASONIC 双开关控制。
 * efw_ultrasonic_read() 提供编译期类型检查。
 *
 * 注意：超声波传感器测量需要数百微秒到数十毫秒（声速约 340m/s），
 * 阻塞式测量不适合高速控制循环。推荐在 read 回调中使用非阻塞方式
 * （如中断驱动测量，read 仅读取已完成的距离值）。
 */

#include "efw/core/config.h"
#include "efw/device/sensor.h"
#include "efw/device/sensor/ultrasonic.h"

#if EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_ULTRASONIC  /**< 双开关 */

/**
 * @brief 读取超声波距离传感器数据
 *
 * 对 efw_sensor_read() 的类型安全包装。
 * 用户在注册的超声波传感器的 read 回调中负责触发测量并填充 distance_m。
 *
 * @param name 已注册的超声波传感器名称 (如 "ultrasonic_front")
 * @param out  输出数据指针 (efw_ultrasonic_data_t*)，不能为空
 * @return EFW_OK 成功, EFW_ERR_INVALID out 为空, 其他错误来自底层 read
 */
efw_status_t efw_ultrasonic_read(const char *name, efw_ultrasonic_data_t *out) {
    if (!out) return EFW_ERR_INVALID;           /* out 为空 → 无法写入 */
    return efw_sensor_read(name, out);          /* 委托给通用传感器读取 */
}

#endif /* EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_ULTRASONIC */
