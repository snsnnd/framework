cmake_minimum_required(VERSION 3.15)

project(efw C)

add_library(efw STATIC
    src/algorithm/algorithms.c
    src/core/registry.c
    src/hal/hal_comm_registry.c
)

target_include_directories(efw PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(efw PUBLIC c_std_99)

option(EFW_BUILD_EXAMPLES "Build EFW host examples" OFF)

if(EFW_BUILD_EXAMPLES)
    add_executable(efw_example_basic
        examples/basic_baremetal_app.c
    )
    target_link_libraries(efw_example_basic PRIVATE efw)
endif()
