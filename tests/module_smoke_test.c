#include "efw/efw.h"

#include <stdio.h>

static int g_fail;

#define CHECK_OK(expr) do { efw_status_t s__ = (expr); if (s__ != EFW_OK) { printf("FAIL %s -> %d\n", #expr, (int)s__); g_fail++; } } while (0)
#define CHECK_TRUE(expr) do { if (!(expr)) { printf("FAIL %s\n", #expr); g_fail++; } } while (0)

int main(void)
{
    CHECK_OK(efw_init());

#if EFW_ENABLE_HAL
    CHECK_OK(efw_hal_registry_init());
    CHECK_TRUE(efw_hal_count() == 0u);
#endif

#if EFW_ENABLE_SENSOR
    CHECK_OK(efw_sensor_registry_init());
    CHECK_TRUE(efw_sensor_count() == 0u);
#endif

#if EFW_ENABLE_ACTUATOR
    CHECK_OK(efw_actuator_registry_init());
    CHECK_TRUE(efw_actuator_count() == 0u);
#endif

#if EFW_ENABLE_ALGORITHM
    CHECK_OK(efw_algo_registry_init());
    CHECK_TRUE(efw_algo_count() == 0u);
#endif

#if EFW_ENABLE_STATE_MACHINE
    CHECK_OK(efw_sm_registry_init());
    CHECK_TRUE(efw_sm_count() == 0u);
#endif

#if EFW_ENABLE_MODULE
    CHECK_OK(efw_module_registry_init());
    CHECK_TRUE(efw_module_count() == 0u);
#endif

#if EFW_ENABLE_EVENT
    efw_topic_clear();
    CHECK_OK(efw_event_queue_init());
#endif

#if EFW_ENABLE_DEBUG
    CHECK_OK(efw_debug_init());
    CHECK_TRUE(efw_debug_point_count() == 0u);
#endif

    if (g_fail == 0) {
        printf("module smoke checks passed\n");
    }
    return g_fail ? 1 : 0;
}
