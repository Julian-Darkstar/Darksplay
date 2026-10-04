execute_process(COMMAND "${HOST_EXECUTABLE}"
    RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE error)
if(NOT "${result}" STREQUAL "0")
    message(FATAL_ERROR "Host failed: ${result}; ${error}")
endif()
if(NOT "${output}" STREQUAL "Darksplay host 0.0.1-dev\n")
    message(FATAL_ERROR "Unexpected host output: ${output}")
endif()
