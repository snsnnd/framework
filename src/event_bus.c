#include "efw/event_bus.h"

#define EFW_MAX_SUBS 32

typedef struct {
    uint16_t topic_id;
    efw_event_cb_t cb;
    void *user;
} subscriber_t;

static subscriber_t g_subs[EFW_MAX_SUBS];
static uint16_t g_sub_n;

efw_status_t efw_event_bus_init(void) { g_sub_n = 0; return EFW_OK; }

efw_status_t efw_subscribe(uint16_t topic_id, efw_event_cb_t cb, void *user) {
    if (!cb) return EFW_ERR_INVALID;
    if (g_sub_n >= EFW_MAX_SUBS) return EFW_ERR_FULL;
    g_subs[g_sub_n++] = (subscriber_t){ .topic_id = topic_id, .cb = cb, .user = user };
    return EFW_OK;
}

efw_status_t efw_publish(const efw_message_t *msg) {
    if (!msg) return EFW_ERR_INVALID;
    for (uint16_t i = 0; i < g_sub_n; ++i) {
        if (g_subs[i].topic_id == msg->topic_id) {
            efw_status_t s = g_subs[i].cb(msg, g_subs[i].user);
            if (s != EFW_OK) return s;
        }
    }
    return EFW_OK;
}
