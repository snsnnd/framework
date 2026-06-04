/**
 * @file    app_manifest.h
 * @brief   Generated feature switches and registry capacities.
 */

#ifndef APP_MANIFEST_H
#define APP_MANIFEST_H

#include "app_board_config.h"

#define APP_USE_HAL                 $APP_USE_HAL
#define APP_USE_SENSOR              $APP_USE_SENSOR
#define APP_USE_LINE_TRACKING       $APP_USE_LINE_TRACKING
#define APP_USE_ACTUATOR            $APP_USE_ACTUATOR
#define APP_USE_MOTOR               $APP_USE_MOTOR
#define APP_USE_ALGORITHM           $APP_USE_ALGORITHM
#define APP_USE_PID                 $APP_USE_PID
#define APP_USE_PROCESSOR           $APP_USE_PROCESSOR
#define APP_USE_MODULE              $APP_USE_MODULE
#define APP_USE_EVENT               $APP_USE_EVENT
#define APP_USE_STATE_MACHINE       $APP_USE_STATE_MACHINE

#define APP_PROJECT_TICK_MS          $APP_PROJECT_TICK_MS

#define APP_HAL_COUNT               $APP_HAL_COUNT
#define APP_SENSOR_COUNT            $APP_SENSOR_COUNT
#define APP_ACTUATOR_COUNT          $APP_ACTUATOR_COUNT
#define APP_ALGO_COUNT              $APP_ALGO_COUNT
#define APP_PROCESSOR_COUNT         $APP_PROCESSOR_COUNT
#define APP_DATAFLOW_PIPELINE_COUNT $APP_DATAFLOW_PIPELINE_COUNT
#define APP_DATAFLOW_BUFFER_SIZE    $APP_DATAFLOW_BUFFER_SIZE
#define APP_MODULE_COUNT            $APP_MODULE_COUNT
#define APP_TOPIC_COUNT             $APP_TOPIC_COUNT
#define APP_CONTRACT_COUNT          $APP_CONTRACT_COUNT
#define APP_STATE_COUNT             $APP_STATE_COUNT

$TOPIC_MACROS
#endif
