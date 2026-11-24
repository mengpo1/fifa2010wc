# fifa2010wc J2 step A7 (docs/J2_A7_SYNTHETIC_CHAIN.md): a host program built the way the
# game executable will be, from code that the installed `rexglue` generated, with no game
# data.
#
# The input is the C++ that `rexglue recompile-tests` writes from the PowerPC instruction
# tests of the ReXGlue v0.11.0 source tree (tests/ppc/asm, BSD-3-Clause), assembled by the
# GNU binutils of nixpkgs. nix/checks.nix (a7-synthetic-chain) produces it and passes its
# folder as A7_GENERATED_DIR. Nothing here reads an XEX, an ISO or a file of the game.
#
# The target goes through rexglue_configure_target, the function that rexglue_setup_target
# calls for the game host (lib/cmake/rexglue/rexglue_project.cmake of the SDK package): the
# same link flags, linker (REXGLUE_LLD), $ORIGIN RUNPATH and staging of the SDK libraries.

cmake_minimum_required(VERSION 3.25)

project(fifa2010wc_a7_chain LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if (NOT A7_GENERATED_DIR OR NOT IS_DIRECTORY "${A7_GENERATED_DIR}")
  message(FATAL_ERROR "A7_GENERATED_DIR must name the output folder of rexglue recompile-tests")
endif ()

find_package(rexglue 0.11 CONFIG REQUIRED)
find_package(Catch2 3 CONFIG REQUIRED)

file(GLOB A7_CASE_SOURCES "${A7_GENERATED_DIR}/ppc_test_cases_*.cpp")
if (NOT A7_CASE_SOURCES)
  message(FATAL_ERROR "No ppc_test_cases_*.cpp in ${A7_GENERATED_DIR}")
endif ()

add_executable(a7_ppc_tests "${A7_GENERATED_DIR}/ppc_test_functions.cpp" ${A7_CASE_SOURCES})
target_include_directories(a7_ppc_tests PRIVATE "${A7_GENERATED_DIR}")
target_link_libraries(a7_ppc_tests PRIVATE rex::kernel rex::simde Catch2::Catch2WithMain)
# The same as the upstream ppc_tests target (tests/ppc/CMakeLists.txt of ReXGlue v0.11.0).
target_compile_options(
  a7_ppc_tests PRIVATE -UTRACY_ENABLE -UREXGLUE_ENABLE_PROFILING -UREXGLUE_ENABLE_PERF_COUNTERS
)

rexglue_configure_target(a7_ppc_tests)
