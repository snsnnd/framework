/**
 * @file    common.h
 * @brief   EFW 框架公共类型定义
 *
 * 本文件定义了整个框架共用的基础类型：
 *   - efw_status_t : 统一状态码枚举，所有 API 均返回此类型，调用方检查返回值判断成功/失败
 *   - EFW_UNUSED   : 用于标记未使用的函数参数，消除编译器警告 (等效于 (void)x)
 *
 * 依赖：仅 stdint.h 和 stddef.h，不依赖任何 OS 或动态内存，适合裸机环境
 */

#ifndef EFW_COMMON_H
#define EFW_COMMON_H

#include <stdint.h>
#include <stddef.h>

/**
 * @brief 框架统一状态码
 *
 * 每个 API 调用都返回 efw_status_t，调用方必须检查返回值是否为 EFW_OK。
 * 正值保留未用，负值表示各类错误。
 *
 * 使用示例：
 *   efw_status_t s = efw_sensor_read("imu0", &data);
 *   if (s != EFW_OK) { 错误处理 }
 */
typedef enum {
    EFW_OK                =  0, /**< 操作成功，无错误 */
    EFW_ERR_INVALID       = -1, /**< 参数无效：传入 NULL 指针、name 为空、dt<=0 等 */
    EFW_ERR_FULL          = -2, /**< 注册表已满：已注册数量达到编译期上限 (如 EFW_MAX_SENSORS) */
    EFW_ERR_NOT_FOUND     = -3, /**< 按名称查找失败：未注册过该名称的组件 */
    EFW_ERR_ALREADY_EXISTS = -4, /**< 名称冲突：尝试注册一个已被使用的名称 */
    EFW_ERR_NOT_READY     = -5, /**< 设备未就绪：组件未初始化或未打开，不能执行操作 */
    EFW_ERR_IO            = -6  /**< IO 错误：底层硬件读写失败 */
} efw_status_t;

/**
 * @brief 消除 "unused variable/parameter" 编译警告
 *
 * 在回调函数中某些参数可能未被使用（如预留的 ctx 或通用接口参数），
 * 用此宏告知编译器 "我知道这个变量没用，不是 bug"。
 *
 * 用法：EFW_UNUSED(unused_param);
 */
#ifndef EFW_UNUSED
#define EFW_UNUSED(x) ((void)(x))
#endif

#endif
