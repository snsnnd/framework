#ifndef EFW_EVENT_H
#define EFW_EVENT_H

#include "efw/core/common.h"

#ifndef EFW_MAX_TOPIC_SUBS
#define EFW_MAX_TOPIC_SUBS 8
#endif

#ifndef EFW_EVENT_QUEUE_CAPACITY
#define EFW_EVENT_QUEUE_CAPACITY 8
#endif

#ifndef EFW_EVENT_ITEM_MAX_SIZE
#define EFW_EVENT_ITEM_MAX_SIZE 32
#endif

#ifndef EFW_EVENT_NAME_MAX_LEN
#define EFW_EVENT_NAME_MAX_LEN 32
#endif

/**
 * @brief 同步话题订阅回调。
 *
 * publish 会在当前调用上下文直接执行所有匹配回调，不会创建线程，也不会
 * 复制回调之外的数据。若需要中断与主循环解耦，应使用下方事件队列。
 */
typedef void (*efw_topic_cb_t)(uint16_t topic_id, const void *data, uint16_t size, void *user);

/** @brief 删除所有话题订阅关系。 */
efw_status_t efw_topic_clear(void);

/** @brief 添加一个 topic_id、回调和用户上下文组成的订阅槽位。 */
efw_status_t efw_topic_subscribe(uint16_t topic_id, efw_topic_cb_t cb, void *user);

/** @brief 删除一个匹配 topic_id 和回调地址的订阅槽位。 */
efw_status_t efw_topic_unsubscribe(uint16_t topic_id, efw_topic_cb_t cb);

/**
 * @brief 同步发布话题。
 *
 * data 由调用方拥有，回调返回后框架不再使用它；size 可以为 0，此时 data
 * 可以为 NULL。回调返回值不会汇总，因此 publish 本身通常返回 EFW_OK。
 */
efw_status_t efw_topic_publish(uint16_t topic_id, const void *data, uint16_t size);

/**
 * @brief 事件队列中的一个固定大小消息。
 *
 * 入队时会复制 event_name 和 data，所以入队后调用方可以立即复用原缓冲区。
 * event_name 为空表示只有 topic_id 的普通事件；data 最大为
 * EFW_EVENT_ITEM_MAX_SIZE 字节。
 */
typedef struct {
    uint16_t topic_id;
    uint16_t size;
    char event_name[EFW_EVENT_NAME_MAX_LEN];
    uint8_t data[EFW_EVENT_ITEM_MAX_SIZE];
} efw_event_item_t;

/** @brief 清空事件队列的读写游标和消息数量。 */
efw_status_t efw_event_queue_init(void);

/** @brief 入队一个不带名称的事件消息。 */
efw_status_t efw_event_queue_post(uint16_t topic_id, const void *data, uint16_t size);

/** @brief 入队一个带名称的事件消息；名称会被复制到固定数组。 */
efw_status_t efw_event_queue_post_named(uint16_t topic_id, const char *event_name, const void *data, uint16_t size);

/**
 * @brief 处理当前队列快照中的消息。
 *
 * 函数开始时记录待处理数量，因此回调期间新入队的消息留到下一次处理，
 * 避免回调不断产生消息导致本次调用无法返回。
 */
efw_status_t efw_event_queue_process(void);

/** @brief 返回当前排队消息数量。 */
uint8_t efw_event_queue_count(void);

/** @brief 事件队列扩展分发回调，可同时观察名称、topic、数据和长度。 */
typedef void (*efw_event_dispatch_fn)(const char *event_name, uint16_t topic_id, const void *data, uint16_t size);

/** @brief 使用自定义分发回调处理当前队列快照。 */
efw_status_t efw_event_queue_process_ex(efw_event_dispatch_fn dispatch);

#endif
