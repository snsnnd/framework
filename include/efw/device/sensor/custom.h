/**
 * @file    custom.h
 * @brief   自定义传感器 —— 通用传感器数据容器
 *
 * 本文件提供了一种"万能"传感器类型，用于封装框架内置 5 种传感器类型
 * 无法覆盖的特殊传感器（如颜色传感器、气压计、电流传感器、GPS 模块等）。
 *
 * =========================================================================
 * 为什么需要自定义传感器？
 * =========================================================================
 *
 *   框架内置了 4 种具体传感器 (循迹/IMU/编码器/超声波) + CUSTOM 占位。
 *   每种具体的传感器有固定的数据结构 (efw_line_tracking_data_t 等)。
 *
 *   但嵌入式项目中总会遇到框架未覆盖的传感器类型，例如：
 *     - 颜色传感器 (TCS34725) → RGB 三通道值
 *     - 气压计 (BMP280) → 气压 + 温度
 *     - GPS 模块 → 经纬度 + 高度 + 速度
 *     - 电流传感器 (INA219) → 电压 + 电流 + 功率
 *
 *   EFW_SENSOR_CUSTOM 类型 + efw_custom_sensor_data_t 结构体
 *   提供了一个通用的容器来承载这些自定义数据。
 *
 * =========================================================================
 * 数据结构
 * =========================================================================
 *
 *   efw_custom_sensor_data_t:
 *     type_id — 用户自定义的类型标识 (用于区分同一 CUSTOM 类型下的不同传感器)
 *     data    — 指向实际数据的指针 (void*)
 *     size    — data 指向的数据大小 (字节数)
 *
 *   这本质上是一个"带类型标记的缓冲区描述符"。
 *   上层代码根据 type_id 知道如何解释 data 指向的内存。
 *
 *   使用建议：
 *     为每种自定义传感器定义一个唯一的 type_id 枚举值：
 *       enum { CUSTOM_TYPE_COLOR=1, CUSTOM_TYPE_PRESSURE=2, CUSTOM_TYPE_GPS=3 };
 *     在传感器注册时，在 ctx 中存储 type_id。
 *     在 read 回调中，根据 ctx 中的 type_id 填充对应的数据结构。
 */

#ifndef EFW_SENSOR_CUSTOM_H
#define EFW_SENSOR_CUSTOM_H

#include "efw/core/common.h"

/**
 * @brief 自定义传感器数据结构 —— 通用缓冲区描述符
 *
 * @field type_id 用户自定义类型标识 (uint32_t)
 *                用于区分不同种类的自定义传感器数据
 *                例如 1=颜色传感器RGB, 2=气压计, 3=GPS 等
 * @field data    数据指针 (void*)，指向实际传感器数据结构
 *                调用方负责分配和释放内存
 * @field size    data 指向的缓冲区大小 (字节)
 *                用于校验和防止越界
 */
typedef struct {
    uint32_t type_id;       /**< 用户自定义类型标识 */
    void *data;             /**< 实际数据指针 */
    uint16_t size;          /**< 数据大小 (字节) */
} efw_custom_sensor_data_t;

/**
 * @brief 读取自定义传感器数据 (泛型版本)
 *
 * 对 efw_sensor_read() 的直接包装，out 是 void* 类型。
 * 调用方需要确保 out 的大小和类型与传感器 read 回调匹配。
 *
 * @param name 传感器注册名称
 * @param out  输出缓冲区 (任意类型指针)
 * @return EFW_OK 成功, EFW_ERR_INVALID out 为空
 */
efw_status_t efw_custom_sensor_read(const char *name, void *out);

/**
 * @brief 读取自定义传感器数据 (带大小校验的版本)
 *
 * 对 efw_custom_sensor_read() 的包装，额外做 out->data 非空
 * 和 out->size>0 的校验，提供更安全的调用。
 *
 * @param name 传感器注册名称
 * @param out  输出数据描述符 (含 type_id + data + size)
 * @return EFW_OK 成功, EFW_ERR_INVALID 参数非法
 */
efw_status_t efw_custom_sensor_read_data(const char *name, efw_custom_sensor_data_t *out);

#endif
