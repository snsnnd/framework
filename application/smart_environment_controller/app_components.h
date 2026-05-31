/**
 * @file    app_components.h
 * @brief   Smart Environment Controller 示例组件注册与状态查询
 */

#ifndef SMART_ENVIRONMENT_APP_COMPONENTS_H
#define SMART_ENVIRONMENT_APP_COMPONENTS_H

#include "app_types.h"

efw_status_t app_components_register(void);
const app_env_sample_t *app_components_current_sample(void);

#endif
