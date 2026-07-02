cmake_minimum_required(VERSION 3.15)
project(efw_debug_test C)

set(CMAKE_C_STANDARD 99)

# 包含路径
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/../../include
    ${CMAKE_CURRENT_SOURCE_DIR}/..
)

# 定义宏
add_definitions(-DEFW_DEBUG_ENABLE=1)
add_definitions(-DNDEBUG=0)

# 源文件
set(MOCK_SOURCES
    mock_platform.c
    mock_efw_stubs.c
)

set(TEST_SOURCES
    perf_test.c
    test_debug_perf.c
)

set(DEBUG_SOURCES
    ../../src/debug/efw_debug.c
    ../../src/debug/efw_debug_fast.c
    ../../src/debug/efw_debug_async.c
)

# 构建测试可执行文件
add_executable(debug_perf_test
    ${MOCK_SOURCES}
    ${TEST_SOURCES}
    ${DEBUG_SOURCES}
)
target_link_libraries(debug_perf_test m)

# EFW 框架开销测试
add_executable(efw_overhead_test
    ${MOCK_SOURCES}
    perf_test.c
    test_efw_overhead.c
    ${DEBUG_SOURCES}
)
target_link_libraries(efw_overhead_test m)

# 添加测试
enable_testing()
add_test(NAME debug_perf_test COMMAND debug_perf_test)
