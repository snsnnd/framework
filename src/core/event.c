#include "efw/core/config.h"
#include "efw/core/event.h"
#include <string.h>

#if EFW_ENABLE_EVENT

typedef struct {
    uint16_t topic_id;
    efw_topic_cb_t cb;
    void *user;
} efw_sub_t;

static efw_sub_t g_subs[EFW_MAX_TOPIC_SUBS];
static size_t g_sub_n;

static efw_event_item_t g_event_queue[EFW_EVENT_QUEUE_CAPACITY];
static uint8_t g_eq_head;
static uint8_t g_eq_tail;
static uint8_t g_eq_count;

efw_status_t efw_topic_clear(void) {
    g_sub_n = 0;
    return EFW_OK;
}

efw_status_t efw_topic_subscribe(uint16_t topic_id, efw_topic_cb_t cb, void *user) {
    if (!cb) return EFW_ERR_INVALID;
    if (g_sub_n >= EFW_MAX_TOPIC_SUBS) return EFW_ERR_FULL;
    g_subs[g_sub_n++] = (efw_sub_t){ topic_id, cb, user };
    return EFW_OK;
}

efw_status_t efw_topic_unsubscribe(uint16_t topic_id, efw_topic_cb_t cb) {
    if (!cb) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_sub_n; ++i) {
        if (g_subs[i].topic_id == topic_id && g_subs[i].cb == cb) {
            g_subs[i] = g_subs[--g_sub_n];
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_topic_publish(uint16_t topic_id, const void *data, uint16_t size) {
    for (size_t i = 0; i < g_sub_n; ++i) {
        if (g_subs[i].topic_id == topic_id) {
            g_subs[i].cb(topic_id, data, size, g_subs[i].user);
        }
    }
    return EFW_OK;
}

efw_status_t efw_event_queue_init(void) {
    g_eq_head = 0;
    g_eq_tail = 0;
    g_eq_count = 0;
    return EFW_OK;
}

static efw_status_t queue_post(uint16_t topic_id, const char *event_name, const void *data, uint16_t size) {
    if (g_eq_count >= EFW_EVENT_QUEUE_CAPACITY) return EFW_ERR_FULL;
    if (size > 0 && !data) return EFW_ERR_INVALID;
    if (size > EFW_EVENT_ITEM_MAX_SIZE) return EFW_ERR_RANGE;
    efw_event_item_t *item = &g_event_queue[g_eq_tail];
    item->topic_id = topic_id;
    item->event_name = event_name;
    item->size = size;
    if (data && size > 0) {
        memcpy(item->data, data, size);
    }
    g_eq_tail = (uint8_t)((g_eq_tail + 1u) % EFW_EVENT_QUEUE_CAPACITY);
    g_eq_count++;
    return EFW_OK;
}

efw_status_t efw_event_queue_post(uint16_t topic_id, const void *data, uint16_t size) {
    return queue_post(topic_id, 0, data, size);
}

efw_status_t efw_event_queue_post_named(uint16_t topic_id, const char *event_name, const void *data, uint16_t size) {
    return queue_post(topic_id, event_name, data, size);
}

efw_status_t efw_event_queue_process(void) {
    uint8_t to_process = g_eq_count;
    while (to_process > 0 && g_eq_count > 0) {
        efw_event_item_t *item = &g_event_queue[g_eq_head];
        g_eq_head = (uint8_t)((g_eq_head + 1u) % EFW_EVENT_QUEUE_CAPACITY);
        g_eq_count--;
        to_process--;
        if (item->topic_id != 0) {
            efw_status_t s = efw_topic_publish(item->topic_id,
                                               item->size > 0 ? item->data : 0,
                                               item->size);
            if (s != EFW_OK) return s;
        }
    }
    return EFW_OK;
}

efw_status_t efw_event_queue_process_ex(efw_event_dispatch_fn dispatch) {
    if (!dispatch) return EFW_ERR_INVALID;
    uint8_t to_process = g_eq_count;
    while (to_process > 0 && g_eq_count > 0) {
        efw_event_item_t *item = &g_event_queue[g_eq_head];
        g_eq_head = (uint8_t)((g_eq_head + 1u) % EFW_EVENT_QUEUE_CAPACITY);
        g_eq_count--;
        to_process--;
        dispatch(item->event_name, item->topic_id,
                 item->size > 0 ? item->data : 0, item->size);
    }
    return EFW_OK;
}

uint8_t efw_event_queue_count(void) {
    return g_eq_count;
}

#endif
