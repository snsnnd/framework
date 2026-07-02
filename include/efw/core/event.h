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

typedef void (*efw_topic_cb_t)(uint16_t topic_id, const void *data, uint16_t size, void *user);

efw_status_t efw_topic_clear(void);
efw_status_t efw_topic_subscribe(uint16_t topic_id, efw_topic_cb_t cb, void *user);
efw_status_t efw_topic_unsubscribe(uint16_t topic_id, efw_topic_cb_t cb);
efw_status_t efw_topic_publish(uint16_t topic_id, const void *data, uint16_t size);

typedef struct {
    uint16_t topic_id;
    uint16_t size;
    const char *event_name;
    uint8_t data[EFW_EVENT_ITEM_MAX_SIZE];
} efw_event_item_t;

efw_status_t efw_event_queue_init(void);
efw_status_t efw_event_queue_post(uint16_t topic_id, const void *data, uint16_t size);
efw_status_t efw_event_queue_post_named(uint16_t topic_id, const char *event_name, const void *data, uint16_t size);
efw_status_t efw_event_queue_process(void);
uint8_t efw_event_queue_count(void);

typedef void (*efw_event_dispatch_fn)(const char *event_name, uint16_t topic_id, const void *data, uint16_t size);
efw_status_t efw_event_queue_process_ex(efw_event_dispatch_fn dispatch);

#endif
