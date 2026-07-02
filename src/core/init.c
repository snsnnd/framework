#include "efw/efw.h"

efw_status_t efw_init(void) {
    efw_status_t s;
    EFW_UNUSED(s);

#if EFW_ENABLE_HAL
    s = efw_hal_registry_init();
    if (s != EFW_OK) return s;
#endif

#if EFW_ENABLE_COMM
    s = efw_comm_registry_init();
    if (s != EFW_OK) return s;
#endif

#if EFW_ENABLE_MODULE
    s = efw_module_registry_init();
    if (s != EFW_OK) return s;
#endif

#if EFW_ENABLE_SENSOR
    s = efw_sensor_registry_init();
    if (s != EFW_OK) return s;
#endif

#if EFW_ENABLE_ACTUATOR
    s = efw_actuator_registry_init();
    if (s != EFW_OK) return s;
#endif

#if EFW_ENABLE_ALGORITHM
    s = efw_algo_registry_init();
    if (s != EFW_OK) return s;
#endif

#if EFW_ENABLE_STATE_MACHINE
    s = efw_sm_registry_init();
    if (s != EFW_OK) return s;
#endif

#if EFW_ENABLE_EVENT
    s = efw_topic_clear();
    if (s != EFW_OK) return s;
    s = efw_event_queue_init();
    if (s != EFW_OK) return s;
#endif

#if EFW_ENABLE_SCHEDULER
    s = efw_scheduler_init();
    if (s != EFW_OK) return s;
#endif

    return EFW_OK;
}
