/**
 * @file    imu.c
 * @brief   IMU 传感器读取 —— 对通用 efw_sensor_read() 的类型安全包装
 *
 * 本文件由 EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_IMU 双开关控制。
 * efw_imu_read() 仅做类型检查和参数校验，实际读取委托给传感器注册表中的 read 回调。
 */

#include "efw/core/config.h"
#include "efw/device/sensor.h"
#include "efw/device/sensor/imu.h"

#if EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_IMU  /**< 双开关 */

/**
 * @brief 读取 IMU 传感器数据
 *
 * 这是对 efw_sensor_read() 的类型安全包装——编译期确保 out 是 efw_imu_data_t*。
 * 与直接调用 efw_sensor_read("imu_head", (void*)&data) 功能等价。
 *
 * @param name 已注册的 IMU 传感器名称 (如 "imu_head", "imu_body")
 * @param out  输出数据指针 (efw_imu_data_t*)，不能为空
 * @return EFW_OK 成功, EFW_ERR_INVALID out 为空, 其他错误来自底层 read
 */
efw_status_t efw_imu_read(const char *name, efw_imu_data_t *out) {
    if (!out) return EFW_ERR_INVALID;           /* out 为空 → 无法写入 */
    return efw_sensor_read(name, out, (uint16_t)sizeof(*out));  /* 委托给通用传感器读取 */
}

#endif /* EFW_ENABLE_SENSOR && EFW_ENABLE_SENSOR_IMU */
