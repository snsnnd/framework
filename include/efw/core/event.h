/**
 * @file    event.h
 * @brief   事件总线 —— 发布-订阅模式的轻量级消息系统
 *
 * 提供基于 topic_id 的发布-订阅机制，允许模块间解耦通信。
 *
 * =========================================================================
 * 设计原理
 * =========================================================================
 *
 *   事件总线是一个"黑板"模式的消息传递系统：
 *     - 发布者 (publisher)  不需要知道谁在接收——只往 topic_id 推送数据
 *     - 订阅者 (subscriber) 不需要知道谁在发送——只注册 topic_id 的回调
 *
 *   优势：
 *     ① 解耦：传感器模块不知道谁在用数据，只管发布
 *     ② 可扩展：新增消费者只需 subscribe，不需改发布方
 *     ③ 一对多：一个 topic 的所有订阅者都会被通知
 *
 * =========================================================================
 * 使用示例
 * =========================================================================
 *
 *   #define TOPIC_IMU_DATA 1      // 用枚举管理 topic ID
 *
 *   void on_imu(uint16_t id, const void *data, uint16_t size, void *user) {
 *       efw_imu_data_t *imu = (efw_imu_data_t*)data;
 *   }
 *   efw_topic_subscribe(TOPIC_IMU_DATA, on_imu, NULL);
 *   efw_topic_publish(TOPIC_IMU_DATA, &imu, sizeof(imu));
 *
 * =========================================================================
 * 容量 + 性能
 * =========================================================================
 *
 *   EFW_MAX_TOPIC_SUBS (默认 8) 控制最大订阅者数。
 *   publish 遍历全部订阅者 O(n)，n≤8 时开销可忽略。
 *   回调在 publish 调用上下文中同步执行——耗时操作会阻塞发布者。
 */

#ifndef EFW_EVENT_H
#define EFW_EVENT_H

#include "efw/core/common.h"

/**
 * @brief 话题回调函数类型
 * @param topic_id 触发回调的话题 ID
 * @param data     发布者传入的数据指针 (类型由 topic 约定)
 * @param size     数据大小 (字节)
 * @param user     订阅时传入的用户自定义指针 (可为 NULL)
 */
typedef void (*efw_topic_cb_t)(uint16_t topic_id, const void *data, uint16_t size, void *user);

/** @brief 清空所有订阅关系 */
efw_status_t efw_topic_clear(void);

/**
 * @brief 订阅话题
 * @param topic_id 话题 ID (用户自定义枚举)
 * @param cb       回调函数指针 (不可为空)
 * @param user     用户自定义指针，发布时传回给回调 (可为 NULL)
 * @return EFW_OK / EFW_ERR_INVALID (cb为空) / EFW_ERR_FULL (订阅者已满)
 */
efw_status_t efw_topic_subscribe(uint16_t topic_id, efw_topic_cb_t cb, void *user);

/**
 * @brief 发布话题 —— 同步调用所有匹配 topic_id 的订阅者回调
 * @param topic_id 话题 ID
 * @param data     数据指针 (可为 NULL 表示无数据事件)
 * @param size     数据大小 (字节，无数据时传 0)
 * @return 始终返回 EFW_OK (单个回调失败不影响其他订阅者)
 */
efw_status_t efw_topic_publish(uint16_t topic_id, const void *data, uint16_t size);

#endif
