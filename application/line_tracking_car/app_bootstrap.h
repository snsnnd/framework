/**
 * @file    app_bootstrap.h
 * @brief   循迹小车应用 glue code：对外提供极简 app_init/app_loop_1ms
 */

#ifndef APP_BOOTSTRAP_H
#define APP_BOOTSTRAP_H

#include "efw/efw.h"

efw_status_t app_init(void);
efw_status_t app_loop_1ms(void);

#endif
