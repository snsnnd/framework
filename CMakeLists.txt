cmake_minimum_required(VERSION 3.15)

project(efw C)

option(EFW_BUILD_APPLICATIONS "Build EFW application examples" OFF)
option(EFW_BUILD_TESTS "Build host-side EFW contract checks" ON)
option(EFW_ENABLE_HAL "Enable HAL registry" ON)
option(EFW_ENABLE_COMM "Enable COMM registry" ON)
option(EFW_ENABLE_MODULE "Enable module registry" ON)
option(EFW_ENABLE_SENSOR "Enable sensor registry" ON)
option(EFW_ENABLE_SENSOR_LINE_TRACKING "Enable line tracking sensor middleware" ON)
option(EFW_ENABLE_SENSOR_IMU "Enable IMU sensor middleware" ON)
option(EFW_ENABLE_SENSOR_ENCODER "Enable encoder sensor middleware" ON)
option(EFW_ENABLE_SENSOR_ULTRASONIC "Enable ultrasonic sensor middleware" ON)
option(EFW_ENABLE_SENSOR_CUSTOM "Enable custom sensor middleware" ON)
option(EFW_ENABLE_ACTUATOR "Enable actuator registry" ON)
option(EFW_ENABLE_ACTUATOR_MOTOR "Enable motor actuator helpers" ON)
option(EFW_ENABLE_ALGORITHM "Enable algorithm registry" ON)
option(EFW_ENABLE_ALGO_PID "Enable built-in PID algorithm" ON)
option(EFW_ENABLE_ALGO_MOVING_AVG "Enable built-in moving average algorithm" ON)
option(EFW_ENABLE_ALGO_LOW_PASS "Enable low-pass filter algorithm" ON)
option(EFW_ENABLE_ALGO_RAMP "Enable ramp limiter algorithm" ON)
option(EFW_ENABLE_ALGO_ENCODER_SPEED "Enable encoder speed estimator" ON)
option(EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY "Enable complementary attitude estimator" ON)
option(EFW_ENABLE_STATE_MACHINE "Enable state machine registry" ON)
option(EFW_ENABLE_EVENT "Enable lightweight topic event" ON)
option(EFW_ENABLE_SCHEDULER "Enable multi-period task scheduler" ON)
option(EFW_ENABLE_DEBUG "Enable online debug module" ON)

set(EFW_SOURCES src/core/init.c src/core/diagnostic.c src/app/runtime.c)

if(EFW_ENABLE_EVENT)
    list(APPEND EFW_SOURCES src/core/event.c)
endif()

if(EFW_ENABLE_SCHEDULER)
    list(APPEND EFW_SOURCES src/core/scheduler.c)
endif()

if(EFW_ENABLE_HAL)
    list(APPEND EFW_SOURCES src/hal/hal_registry.c)
endif()

if(EFW_ENABLE_COMM)
    list(APPEND EFW_SOURCES src/comm/comm_registry.c)
endif()

if(EFW_ENABLE_MODULE)
    list(APPEND EFW_SOURCES src/module/module_registry.c)
endif()

if(EFW_ENABLE_SENSOR)
    list(APPEND EFW_SOURCES src/device/sensor_registry.c)
    if(EFW_ENABLE_SENSOR_LINE_TRACKING)
        list(APPEND EFW_SOURCES src/device/sensor/line_tracking.c)
    endif()
    if(EFW_ENABLE_SENSOR_IMU)
        list(APPEND EFW_SOURCES src/device/sensor/imu.c)
    endif()
    if(EFW_ENABLE_SENSOR_ENCODER)
        list(APPEND EFW_SOURCES src/device/sensor/encoder.c)
    endif()
    if(EFW_ENABLE_SENSOR_ULTRASONIC)
        list(APPEND EFW_SOURCES src/device/sensor/ultrasonic.c)
    endif()
    if(EFW_ENABLE_SENSOR_CUSTOM)
        list(APPEND EFW_SOURCES src/device/sensor/custom.c)
    endif()
endif()

if(EFW_ENABLE_ACTUATOR)
    list(APPEND EFW_SOURCES src/device/actuator_registry.c)
    if(EFW_ENABLE_ACTUATOR_MOTOR)
        list(APPEND EFW_SOURCES src/device/actuator/motor.c)
    endif()
endif()

if(EFW_ENABLE_ALGORITHM)
    list(APPEND EFW_SOURCES src/algorithm/algorithm_registry.c)
endif()

if(EFW_ENABLE_ALGO_PID)
    list(APPEND EFW_SOURCES src/algorithm/control/pid.c)
endif()

if(EFW_ENABLE_ALGO_MOVING_AVG)
    list(APPEND EFW_SOURCES src/algorithm/filter/moving_average.c)
endif()

if(EFW_ENABLE_ALGO_LOW_PASS)
    list(APPEND EFW_SOURCES src/algorithm/filter/low_pass.c)
endif()

if(EFW_ENABLE_ALGO_RAMP)
    list(APPEND EFW_SOURCES src/algorithm/control/ramp.c)
endif()

if(EFW_ENABLE_ALGO_ENCODER_SPEED)
    list(APPEND EFW_SOURCES src/algorithm/estimator/encoder_speed.c)
endif()

if(EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY)
    list(APPEND EFW_SOURCES src/algorithm/estimator/attitude_complementary.c)
endif()

if(EFW_ENABLE_STATE_MACHINE)
    list(APPEND EFW_SOURCES src/state/state_machine_registry.c)
endif()

if(EFW_ENABLE_DEBUG)
    list(APPEND EFW_SOURCES src/debug/efw_debug.c src/debug/efw_debug_litetune.c)
endif()

add_library(efw STATIC ${EFW_SOURCES})
target_link_libraries(efw PUBLIC m)

target_include_directories(efw PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(efw PUBLIC c_std_99)

target_compile_definitions(efw PUBLIC
    EFW_ENABLE_HAL=$<BOOL:${EFW_ENABLE_HAL}>
    EFW_ENABLE_COMM=$<BOOL:${EFW_ENABLE_COMM}>
    EFW_ENABLE_MODULE=$<BOOL:${EFW_ENABLE_MODULE}>
    EFW_ENABLE_SENSOR=$<BOOL:${EFW_ENABLE_SENSOR}>
    EFW_ENABLE_SENSOR_LINE_TRACKING=$<BOOL:${EFW_ENABLE_SENSOR_LINE_TRACKING}>
    EFW_ENABLE_SENSOR_IMU=$<BOOL:${EFW_ENABLE_SENSOR_IMU}>
    EFW_ENABLE_SENSOR_ENCODER=$<BOOL:${EFW_ENABLE_SENSOR_ENCODER}>
    EFW_ENABLE_SENSOR_ULTRASONIC=$<BOOL:${EFW_ENABLE_SENSOR_ULTRASONIC}>
    EFW_ENABLE_SENSOR_CUSTOM=$<BOOL:${EFW_ENABLE_SENSOR_CUSTOM}>
    EFW_ENABLE_ACTUATOR=$<BOOL:${EFW_ENABLE_ACTUATOR}>
    EFW_ENABLE_ACTUATOR_MOTOR=$<BOOL:${EFW_ENABLE_ACTUATOR_MOTOR}>
    EFW_ENABLE_ALGORITHM=$<BOOL:${EFW_ENABLE_ALGORITHM}>
    EFW_ENABLE_ALGO_PID=$<BOOL:${EFW_ENABLE_ALGO_PID}>
    EFW_ENABLE_ALGO_MOVING_AVG=$<BOOL:${EFW_ENABLE_ALGO_MOVING_AVG}>
    EFW_ENABLE_ALGO_LOW_PASS=$<BOOL:${EFW_ENABLE_ALGO_LOW_PASS}>
    EFW_ENABLE_ALGO_RAMP=$<BOOL:${EFW_ENABLE_ALGO_RAMP}>
    EFW_ENABLE_ALGO_ENCODER_SPEED=$<BOOL:${EFW_ENABLE_ALGO_ENCODER_SPEED}>
    EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY=$<BOOL:${EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY}>
    EFW_ENABLE_STATE_MACHINE=$<BOOL:${EFW_ENABLE_STATE_MACHINE}>
    EFW_ENABLE_EVENT=$<BOOL:${EFW_ENABLE_EVENT}>
    EFW_ENABLE_SCHEDULER=$<BOOL:${EFW_ENABLE_SCHEDULER}>
    EFW_ENABLE_DEBUG=$<BOOL:${EFW_ENABLE_DEBUG}>
)

if(EFW_BUILD_APPLICATIONS)
    add_executable(efw_app_simple_blink
        application/simple_blink/main.c
        application/simple_blink/app_bootstrap.c
        application/simple_blink/app_components.c
        application/simple_blink/app_platform.c
    )
    target_include_directories(efw_app_simple_blink PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/application/simple_blink
    )
    target_link_libraries(efw_app_simple_blink PRIVATE efw)

    add_executable(efw_app_smart_environment_controller
        application/smart_environment_controller/main.c
        application/smart_environment_controller/app_bootstrap.c
        application/smart_environment_controller/app_components.c
        application/smart_environment_controller/app_platform.c
    )
    target_include_directories(efw_app_smart_environment_controller PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/application/smart_environment_controller
    )
    target_link_libraries(efw_app_smart_environment_controller PRIVATE efw)

    add_executable(efw_app_line_tracking_car
        application/line_tracking_car/main.c
        application/line_tracking_car/app_bootstrap.c
        application/line_tracking_car/app_components.c
        application/line_tracking_car/app_platform.c
    )
    target_include_directories(efw_app_line_tracking_car PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/application/line_tracking_car
    )
    target_link_libraries(efw_app_line_tracking_car PRIVATE efw)
endif()

if(EFW_BUILD_TESTS)
    enable_testing()
    add_executable(efw_test_contract_sizes tests/contract_size_check.c)
    target_link_libraries(efw_test_contract_sizes PRIVATE efw)
    add_test(NAME efw_contract_sizes COMMAND efw_test_contract_sizes)

    add_executable(efw_sim_test tests/efw_sim_test.c)
    target_link_libraries(efw_sim_test PRIVATE efw m)
    add_test(NAME efw_sim_test COMMAND efw_sim_test)
endif()
