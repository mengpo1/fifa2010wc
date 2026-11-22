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

# D-011: the ReXGlue SDK v0.11.0 package, built from source by the flake
# (nix/rexglue-sdk.nix). `nix develop` puts it on CMAKE_PREFIX_PATH.
find_package(rexglue 0.11 CONFIG REQUIRED)

message(STATUS "fifa2010wc ${PROJECT_VERSION}")
message(STATUS "  Platform layer: platform/${FIFA2010WC_PLATFORM}")
message(STATUS "  ReXGlue SDK: ${rexglue_VERSION} (${rexglue_DIR})")
message(STATUS "  Host executable: not built before J2")
