# AirPlay 2 Receiver for ESP32
cmake_minimum_required(VERSION 3.16)

# Read firmware version from version.txt
file(READ "${CMAKE_SOURCE_DIR}/version.txt" PROJECT_VER)
string(STRIP "${PROJECT_VER}" PROJECT_VER)

# Add components directory
set(EXTRA_COMPONENT_DIRS "${CMAKE_SOURCE_DIR}/components")

include($ENV{IDF_PATH}/tools/cmake/version.cmake)
if(IDF_VERSION_MAJOR LESS 5 OR (IDF_VERSION_MAJOR EQUAL 5 AND IDF_VERSION_MINOR LESS 5))
    message(WARNING
        "ESP-IDF ${IDF_VERSION_MAJOR}.${IDF_VERSION_MINOR}.${IDF_VERSION_PATCH} detected. "
        "This project is developed and tested against ESP-IDF >= 5.5. "
        "Please upgrade with: cd $ENV{IDF_PATH} && git fetch && git checkout v5.5.2 && ./install.sh")
endif()

# Board configs live in config/, so ESP-IDF no longer finds sdkconfig.defaults
# by itself — it only auto-detects one at the project root. Without this a bare
# "idf.py build" would silently configure with no defaults at all instead of
# failing, so restore the base layer when the caller has not chosen one.
if(NOT SDKCONFIG_DEFAULTS AND NOT DEFINED ENV{SDKCONFIG_DEFAULTS})
    set(SDKCONFIG_DEFAULTS "${CMAKE_SOURCE_DIR}/config/sdkconfig.defaults")
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(airplay2-receiver VERSION ${PROJECT_VER})

# Build a SPIFFS image from data/ and flash it alongside the firmware.
# Partition label "storage" matches partitions.csv; it holds the web UI.
# Flash firmware + SPIFFS together with: idf.py build flash
spiffs_create_partition_image(storage "${CMAKE_SOURCE_DIR}/data" FLASH_IN_PROJECT)
