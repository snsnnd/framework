/**
 * @file    event.c
 * @brief   事件总线实现 —— 发布-订阅轻量级消息系统
 *
 * 由 EFW_ENABLE_EVENT 宏控制编译。
 *
 * =========================================================================
 * 实现细节
 * =========================================================================
 *
 *   订阅者存储结构：
 *     g_subs[] — 静态数组，每个元素记录 { topic_id, callback, user }
 *     g_sub_n  — 当前订阅者数量
 *
 *   不支持取消订阅 (unsubscribe) —— 嵌入式场景中订阅关系通常在初始化时
 *   一次性建立，不需要运行时动态取消。
 *
 *   publish 遍历全部 g_sub_n 个条目，对每个匹配 topic_id 的订阅者
 *   同步调用回调。调用顺序 = 订阅顺序。
 *
 *   复杂度：publish O(n)，n=总订阅数。对于 ≤8 的典型值开销可忽略。
 */

#include "efw/core/config.h"
#include "efw/core/event.h"

#if EFW_ENABLE_EVENT  /**< 编译开关 */

/**
 * @brief 单个订阅条目
 * @field topic_id 订阅的话题 ID
 * @field cb       回调函数指针
 * @field user     用户自定义指针
 */
typedef struct {
    uint16_t topic_id;      /**< 话题 ID */
    efw_topic_cb_t cb;      /**< 回调函数 */
    void *user;             /**< 用户指针 */
} efw_sub_t;

/** @brief 订阅者数组 (固定容量 EFW_MAX_TOPIC_SUBS) */
static efw_sub_t g_subs[EFW_MAX_TOPIC_SUBS];
/** @brief 当前订阅者数量 */
static size_t g_sub_n;

/**
 * @brief 清空所有订阅 —— g_sub_n = 0
 */
efw_status_t efw_topic_clear(void) {
    g_sub_n = 0;        /* 计数归零 = 全部清除 */
    return EFW_OK;
}

/**
 * @brief 订阅话题
 *
 * 校验：cb 非空 + 容量未满。
 * 存入 g_subs[g_sub_n++] 尾部追加。
 * 不支持去重——同一回调可以多次订阅同一 topic。
 */
efw_status_t efw_topic_subscribe(uint16_t topic_id, efw_topic_cb_t cb, void *user) {
    if (!cb) return EFW_ERR_INVALID;                    /* 回调不能为空 */
    if (g_sub_n >= EFW_MAX_TOPIC_SUBS) return EFW_ERR_FULL;   /* 容量已满 */
    g_subs[g_sub_n++] = (efw_sub_t){ topic_id, cb, user };    /* 尾部追加 */
    return EFW_OK;
}

/**
 * @brief 发布话题
 *
 * 遍历全部订阅者，对匹配 topic_id 的每个订阅者调用回调。
 * 回调在 publish 的调用上下文中同步执行——不需要队列或事件循环。
 *
 * 注意：不检查单个回调的返回值——一个回调失败不影响其他订阅者。
 */
efw_status_t efw_topic_publish(uint16_t topic_id, const void *data, uint16_t size) {
    for (size_t i = 0; i < g_sub_n; ++i) {
        if (g_subs[i].topic_id == topic_id) {   /* topic 匹配 → 通知 */
            g_subs[i].cb(topic_id, data, size, g_subs[i].user);
        }
    }
    return EFW_OK;
}

#endif /* EFW_ENABLE_EVENT */
