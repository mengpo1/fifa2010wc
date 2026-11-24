# fifa2010wc: native recompilation of 2010 FIFA World Cup South Africa.
#
# Milestone J1 skeleton (docs/ROADMAP.md): toolchain, platform selection and SDK discovery.
# It builds nothing yet. The host executable comes at J2, through the SDK functions
# rexglue_project and rexglue_setup_target, from the user's own private game files.
# No game data is read or needed by this file.

cmake_minimum_required(VERSION 3.25)

project(
  fifa2010wc
  VERSION 0.1.0
  DESCRIPTION "Native recompilation of 2010 FIFA World Cup South Africa"
  LANGUAGES CXX
)

# D-005: C++23 and Clang 20 or newer, the requirements of ReXGlue v0.11.0.
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if (NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang" OR CMAKE_CXX_COMPILER_VERSION VERSION_LESS 20)
  message(FATAL_ERROR "fifa2010wc requires Clang 20 or newer "
                      "(found ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION})")
endif ()

# D-001 and D-006: the platform layer is chosen here, and only here. Linux x86_64 is the
# only platform before J6; macOS ARM64 keeps its folder so that the layout does not change.
if (CMAKE_SYSTEM_NAME STREQUAL "Linux" AND CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|AMD64)$")
  set(FIFA2010WC_PLATFORM "linux")
elseif (CMAKE_SYSTEM_NAME STREQUAL "Darwin" AND CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64)$")
  message(FATAL_ERROR "macOS ARM64 is planned for milestone J6 (docs/ROADMAP.md) "
                      "and is not available yet")
else ()
  message(FATAL_ERROR "Unsupported platform ${CMAKE_SYSTEM_NAME} ${CMAKE_SYSTEM_PROCESSOR}: "
                      "fifa2010wc targets Linux x86_64 (docs/DECISIONS.md D-001)")
endif ()

set(FIFA2010WC_LAYERS app hooks platform/common "platform/${FIFA2010WC_PLATFORM}")
foreach (layer IN LISTS FIFA2010WC_LAYERS)
  if (NOT IS_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/${layer}")
    message(FATAL_ERROR "Missing layer folder ${layer}/ (docs/DECISIONS.md D-006)")
  endif ()
endforeach ()

# J1 finding P-05 and J2 step A7 (docs/J2_A7_SYNTHETIC_CHAIN.md §5): ReXGlue links every
# binary with the ld.lld named by REXGLUE_LLD, or else with the first ld.lld on PATH. Only the
# wrapped ld.lld of the dev shell gives the binaries their RUNPATH entries, and `nix develop`
# keeps the PATH of the machine, where another ld.lld can come first. The presets read
# REXGLUE_LLD from the dev shell. Three checks stop the configure step:
# 1. the variable is not set in the environment;
# 2. the cache value differs from the environment;
# 3. a program linked with that ld.lld does not start without LD_LIBRARY_PATH (review P-47:
#    the first two only check where the value comes from, not what the linker does).
# The third is a probe on one small program. It does not replace the dependency check of the
# real host after its link (docs/J2_PLAN.md §4.5).
if ("$ENV{REXGLUE_LLD}" STREQUAL "")
  message(FATAL_ERROR "REXGLUE_LLD is not set in the environment: configure from `nix develop` "
                      "with a preset of CMakePresets.json")
endif ()
if (NOT REXGLUE_LLD STREQUAL "$ENV{REXGLUE_LLD}")
  message(FATAL_ERROR "REXGLUE_LLD is '${REXGLUE_LLD}', not the wrapped ld.lld of the dev shell "
                      "($ENV{REXGLUE_LLD})")
endif ()
set(_lld_probe_dir "${CMAKE_BINARY_DIR}/CMakeFiles/fifa2010wc_lld_probe")
file(WRITE "${_lld_probe_dir}/probe.cpp"
     "#include <string>\nint main() { std::string text(\"runpath\"); return text.size() == 7 ? 0 : 1; }\n"
)
try_compile(
  _lld_probe_built SOURCES "${_lld_probe_dir}/probe.cpp"
  LINK_OPTIONS "--ld-path=${REXGLUE_LLD}"
  OUTPUT_VARIABLE _lld_probe_build_log
  COPY_FILE "${_lld_probe_dir}/probe"
)
if (NOT _lld_probe_built)
  message(FATAL_ERROR "A program cannot be linked with REXGLUE_LLD (${REXGLUE_LLD}):\n"
                      "${_lld_probe_build_log}")
endif ()
execute_process(
  COMMAND "${CMAKE_COMMAND}" -E env --unset=LD_LIBRARY_PATH --unset=LD_PRELOAD
          "${_lld_probe_dir}/probe"
  RESULT_VARIABLE _lld_probe_status
  OUTPUT_VARIABLE _lld_probe_output
  ERROR_VARIABLE _lld_probe_output
)
if (NOT _lld_probe_status EQUAL 0)
  message(FATAL_ERROR "A program linked with REXGLUE_LLD (${REXGLUE_LLD}) does not start "
                      "without LD_LIBRARY_PATH (${_lld_probe_status}): it is not the wrapped "
                      "ld.lld of the dev shell. ${_lld_probe_output}")
endif ()

# D-011: the ReXGlue SDK v0.11.0 package, built from source by the flake
# (nix/rexglue-sdk.nix). `nix develop` puts it on CMAKE_PREFIX_PATH.
find_package(rexglue 0.11 CONFIG REQUIRED)

message(STATUS "fifa2010wc ${PROJECT_VERSION}")
message(STATUS "  Platform layer: platform/${FIFA2010WC_PLATFORM}")
message(STATUS "  ReXGlue SDK: ${rexglue_VERSION} (${rexglue_DIR})")
message(STATUS "  Host executable: not built before J2")
