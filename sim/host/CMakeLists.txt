cmake_minimum_required(VERSION 3.16)
project(psv_host C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_compile_definitions(HOST_SIM)

if(MSVC)
  add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
  add_compile_options(/W4)
else()
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

set(PSV_CORE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../firmware/core")

add_library(psv_core STATIC
  "${PSV_CORE_DIR}/recorder.c"
  "${PSV_CORE_DIR}/wav.c"
  "${PSV_CORE_DIR}/clock_fmt.c"
)
target_include_directories(psv_core PUBLIC "${PSV_CORE_DIR}")

set(PSV_HOST_HAL
  hal_storage.c
  hal_clock.c
  hal_audio.c
)

add_executable(recorder_test
  test_recorder.c
  ${PSV_HOST_HAL}
)
target_include_directories(recorder_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(recorder_test PRIVATE psv_core)

add_executable(recorder_sim
  main_sim.c
  ${PSV_HOST_HAL}
)
target_include_directories(recorder_sim PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}"
  "${PSV_CORE_DIR}"
)
target_link_libraries(recorder_sim PRIVATE psv_core)
if(NOT MSVC)
  target_link_libraries(recorder_sim PRIVATE m)
endif()

enable_testing()
add_test(NAME recorder_test COMMAND recorder_test WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
