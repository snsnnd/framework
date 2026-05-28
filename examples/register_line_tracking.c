#include "efw/efw.h"

static efw_status_t lt_init(void *ctx) { (void)ctx; return EFW_OK; }
static efw_status_t lt_read(void *ctx, void *out) { (void)ctx; (void)out; return EFW_OK; }

static efw_sensor_ops_t line4 = {
    .name = "line_tracking_4ch",
    .type = EFW_SENSOR_LINE_TRACKING,
    .channel_count = 4,
    .hal_name = 0,
    .comm_name = 0,
    .ctx = 0,
    .init = lt_init,
    .read = lt_read,
};

static efw_sensor_ops_t line8 = {
    .name = "line_tracking_8ch",
    .type = EFW_SENSOR_LINE_TRACKING,
    .channel_count = 8,
    .hal_name = 0,
    .comm_name = 0,
    .ctx = 0,
    .init = lt_init,
    .read = lt_read,
};

void register_sensors_example(void) {
    efw_sensor_registry_init();
    efw_sensor_register(&line4);
    efw_sensor_register(&line8);
}
