/**
 * @file    app_bootstrap.h
 * @brief   Smart Environment Controller 示例启动入口
 */

#ifndef SMART_ENVIRONMENT_APP_BOOTSTRAP_H
#define SMART_ENVIRONMENT_APP_BOOTSTRAP_H

#include "app_types.h"

efw_status_t app_init(void);
efw_status_t app_loop_1ms(void);
const app_env_sample_t *app_current_sample(void);

#endif
