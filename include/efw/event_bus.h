#ifndef EFW_EVENT_BUS_H
#define EFW_EVENT_BUS_H

#include "efw_common.h"
#include <stdint.h>

typedef struct {
    uint16_t topic_id;
    const void *payload;
    uint16_t payload_size;
} efw_message_t;

typedef efw_status_t (*efw_event_cb_t)(const efw_message_t *msg, void *user);

efw_status_t efw_event_bus_init(void);
efw_status_t efw_subscribe(uint16_t topic_id, efw_event_cb_t cb, void *user);
efw_status_t efw_publish(const efw_message_t *msg);

#endif
