add_test(NAME host_smoke
    COMMAND "${CMAKE_COMMAND}"
        "-DHOST_EXECUTABLE=$<TARGET_FILE:darksplay-host>"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/host_smoke.cmake")
