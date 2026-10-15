/**
 * @file    custom.c
 * @brief   自定义传感器 —— 对通用 efw_sensor_read() 的类型安全/参数校验包装
 *
 * 本文件由 EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_CUSTOM 双开关控制。
 *
 * 提供两个版本的读取函数：
 *   efw_custom_sensor_read()       — 泛型版，仅校验 out 非空
 *   efw_custom_sensor_read_data()  — 增强版，额外校验 data 指针和 size
 */

#include "efw/core/config.h"
#include "efw/device/sensor.h"
#include "efw/device/sensor/custom.h"

#if EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_CUSTOM  /**< 双开关 */

/**
 * @brief 读取自定义传感器 (泛型版本)
 *
 * 对 efw_sensor_read() 的简单封装，提供编译期类型安全的调用。
 * out 是 void*，调用方负责确保大小和类型与实际传感器匹配。
 *
 * @param name 已注册的自定义传感器名称
 * @param out  输出缓冲区 (任意指针，不能为空)
 * @return EFW_OK 成功, EFW_ERR_INVALID out 为空
 */
efw_status_t efw_custom_sensor_read(const char *name, void *out, uint16_t out_size) {
    if (!out) return EFW_ERR_INVALID;
    return efw_sensor_read(name, out, out_size);
}

/**
 * @brief 读取自定义传感器 (带 size 校验版本)
 *
 * 在委托给 efw_sensor_read() 之前，额外做两层校验：
 *   ① out 不能为空
 *   ② out->data 不能为空 (数据缓冲区必须已分配)
 *   ③ out->size 必须 > 0 (缓冲区大小必须有效)
 *
 * @param name 已注册的自定义传感器名称
 * @param out  输出数据描述符指针 (含 type_id + data + size)
 * @return EFW_OK 成功, EFW_ERR_INVALID 参数非法
 */
efw_status_t efw_custom_sensor_read_data(const char *name, efw_custom_sensor_data_t *out) {
    if (!out || !out->data || out->size == 0) return EFW_ERR_INVALID;
    return efw_sensor_read(name, out, (uint16_t)sizeof(*out));
}

#endif /* EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_CUSTOM */
