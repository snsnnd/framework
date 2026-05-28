#ifndef EFW_H
#define EFW_H

#include "efw/core/common.h"
#include "efw/core/config.h"
#include "efw/hal/hal.h"
#include "efw/comm/comm.h"
#include "efw/module/module.h"
#include "efw/device/sensor.h"
#include "efw/algorithm/registry.h"
#include "efw/algorithm/algorithms.h"
#include "efw/state/state_machine.h"

efw_status_t efw_init(void);

#endif
