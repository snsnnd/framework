#include "efw/efw.h"

/**
 * @brief 初始化框架的所有已启用子系统。
 *
 * 这里不负责注册具体对象，因为对象属于 BSP 或应用；它只负责把各注册表
 * 恢复到空闲初始态。每个子系统失败立即返回，因此调用方可以在启动阶段
 * 阻止应用继续运行。
 */
efw_status_t efw_init(void) {
    efw_status_t s;
    EFW_UNUSED(s);    // 消除警告，防止没有一个模块启动
    efw_diag_clear(); // 清理/初始化诊断模块的信息

    /* 先初始化底层表，保证后续 COMM/SENSOR/ACTUATOR 的名称绑定有目标。 */

#if EFW_ENABLE_HAL                // 判断是否启动HAL
    s = efw_hal_registry_init();  // 初始化HAL
    if (s != EFW_OK) return s;    // 初始化失败返回错误码
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
