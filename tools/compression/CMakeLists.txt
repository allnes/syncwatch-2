cmake_minimum_required(VERSION 3.30)
project(SyncWatchCompressionProbe LANGUAGES C)

set(ZLIB_BUILD_SHARED OFF CACHE BOOL "" FORCE)
set(ZLIB_BUILD_STATIC ON CACHE BOOL "" FORCE)
set(ZLIB_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(ZLIB_INSTALL OFF CACHE BOOL "" FORCE)
foreach(feature GVMAT64 INFBACK9 CRC32VX)
    set(ZLIB_WITH_${feature} OFF CACHE BOOL "" FORCE)
endforeach()
foreach(binding ADA BLAST IOSTREAM3 MINIZIP PUFF TESTZLIB ZLIB1_DLL)
    set(ZLIB_BUILD_${binding} OFF CACHE BOOL "" FORCE)
endforeach()
add_subdirectory("${SYNCWATCH_ZLIB_SOURCE}" upstream EXCLUDE_FROM_ALL)
set_property(TARGET zlibstatic PROPERTY POSITION_INDEPENDENT_CODE ON)

if(MSVC)
    # MSVC records build paths in COFF metadata even for optimized builds.
    # Remap compiler inputs, not the resulting archive bytes.
    cmake_path(NATIVE_PATH CMAKE_BINARY_DIR NORMALIZE native_build)
    cmake_path(NATIVE_PATH SYNCWATCH_ZLIB_SOURCE NORMALIZE native_source)
    target_compile_options(zlibstatic PRIVATE /experimental:deterministic
        "/pathmap:${native_build}=syncwatch-build"
        "/pathmap:${native_source}=zlib-source")
    set_property(TARGET zlibstatic APPEND PROPERTY STATIC_LIBRARY_OPTIONS /Brepro)
endif()

if(SYNCWATCH_ZLIB_ARTIFACT)
    add_library(accepted_zlib STATIC IMPORTED)
    set_target_properties(accepted_zlib PROPERTIES
        IMPORTED_LOCATION "${SYNCWATCH_ZLIB_ARTIFACT}"
        INTERFACE_INCLUDE_DIRECTORIES "${SYNCWATCH_ZLIB_HEADERS}")
    get_target_property(public_definitions zlibstatic INTERFACE_COMPILE_DEFINITIONS)
    set_property(TARGET accepted_zlib PROPERTY INTERFACE_COMPILE_DEFINITIONS "${public_definitions}")
    set(probe_library accepted_zlib)
else()
    set(probe_library zlibstatic)
endif()

add_executable(zlib_probe probe.c)
target_link_libraries(zlib_probe PRIVATE ${probe_library})
target_compile_features(zlib_probe PRIVATE c_std_11)
if(MSVC)
    target_compile_definitions(zlib_probe PRIVATE _CRT_SECURE_NO_WARNINGS)
    target_compile_options(zlib_probe PRIVATE /W4 /WX)
else()
    target_compile_options(zlib_probe PRIVATE -Wall -Wextra -Werror)
endif()
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/library-$<CONFIG>.txt" CONTENT "$<TARGET_FILE:zlibstatic>")
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/probe-$<CONFIG>.txt" CONTENT "$<TARGET_FILE:zlib_probe>")
