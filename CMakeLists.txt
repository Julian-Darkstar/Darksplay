cmake_minimum_required(VERSION 3.20)
project(Darksplay VERSION 0.0.1 LANGUAGES CXX)

include(CTest)
add_subdirectory(host)
if(BUILD_TESTING)
    add_subdirectory(tests)
endif()
