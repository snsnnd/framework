/**
 * @file    encoder.c
 * @brief   编码器传感器读取 —— 对通用 efw_sensor_read() 的类型安全包装
 *
 * 本文件由 EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_ENCODER 双开关控制。
 * efw_encoder_read() 提供编译期类型检查，避免误传错误的结构体类型。
 */

#include "efw/core/config.h"
#include "efw/device/sensor.h"
#include "efw/device/sensor/encoder.h"

#if EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_ENCODER  /**< 双开关 */

/**
 * @brief 读取编码器传感器数据
 *
 * 对 efw_sensor_read() 的类型安全包装。
 * 用户在注册的编码器传感器的 read 回调中负责填充 count/position/speed。
 *
 * @param name 已注册的编码器传感器名称 (如 "enc_left", "enc_right")
 * @param out  输出数据指针 (efw_encoder_data_t*)，不能为空
 * @return EFW_OK 成功, EFW_ERR_INVALID out 为空, 其他错误来自底层 read
 */
efw_status_t efw_encoder_read(const char *name, efw_encoder_data_t *out) {
    if (!out) return EFW_ERR_INVALID;           /* out 为空 → 无法写入 */
    return efw_sensor_read(name, out);          /* 委托给通用传感器读取 */
}

#endif /* EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_ENCODER */
