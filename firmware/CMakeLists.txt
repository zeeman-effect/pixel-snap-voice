cmake_minimum_required(VERSION 3.16)

# ESP-IDF project. idf.py exports IDF_PATH before configure. A plain cmake
# run (the editor, or `cmake -S firmware`) leaves it empty, and
# "$ENV{IDF_PATH}/tools/cmake/project.cmake" becomes "/tools/cmake/project.cmake".
# Host-side builds live in sim/host and do not need the SDK.
if(DEFINED ENV{IDF_PATH} AND NOT "$ENV{IDF_PATH}" STREQUAL ""
   AND EXISTS "$ENV{IDF_PATH}/tools/cmake/project.cmake")
    include("$ENV{IDF_PATH}/tools/cmake/project.cmake")
else()
    message(STATUS
        "IDF_PATH is not an ESP-IDF checkout; not loading tools/cmake/project.cmake. "
        "Build firmware with idf.py from an ESP-IDF shell. "
        "Host tests: cmake -S sim/host -B build/host")
endif()

project(pixel_snap_voice)
