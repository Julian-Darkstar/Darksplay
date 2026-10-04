add_executable(darksplay-host src/main.cpp)
target_compile_features(darksplay-host PRIVATE cxx_std_20)
set_target_properties(darksplay-host PROPERTIES CXX_EXTENSIONS OFF)
