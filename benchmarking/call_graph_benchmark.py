# Call graph benchmark
# ====================
#
# This benchmark measures:
#
# * The performance of inserting samples into the call graph
# * The memory overhead of the call graph
#
# It works by loading a JSON call graph downloaded from the Amazon Profiler backend, which is then "sliced" into its
# composing samples, which are then fed to our own call graph implementation. This allows us to simulate memory usage
# with a real profile, as well as insertion performance.
#
# The output of this process mostly mirrors the input profile, but note that:
# * every non-runnable state is also mapped to runnable (as that's all we support for Python)
# * if there are rounding errors in the original profile, the resulting profile may also have a few counts off
#
# By default this benchmark runs in the performance profiling mode; to get the memory information
# set the MEMORY_INFO environment variable to 1.
#
# How to run (built-in python or using pyenv):
# * See `python benchmarking/call_graph_benchmark.py --help` for options
# * `PRINT_INFO=1 MEMORY_INFO=1 INPUT_FILE=test_input_profiler_small.json python benchmarking/call_graph_benchmark.py --inherit-environ INPUT_FILE` prints both
#   performance and memory info (after a default number of runs)
#
# How to run (brazil):
# * See `brazil-test-exec python benchmarking/call_graph_benchmark.py --help` for options
# * `PRINT_INFO=1 MEMORY_INFO=1 INPUT_FILE=test_input_profiler_small.json brazil-test-exec python benchmarking/call_graph_benchmark.py --inherit-environ INPUT_FILE`
#
# Note: When testing multiple variants of some code that are toggled via an environment variable, the
# `--inherit-environ SOME_VARIABLE` option needs to be passed otherwise the variable is not correctly considered during
# the test runs. For instance without passing `--inherit-environ INPUT_FILE` the `INPUT_FILE` will not be correctly
# picked up during benchmarking and cause an error.
#
# Dependencies:
#
# * perf - https://pypi.org/project/perf/
# * Pympler - https://pypi.org/project/Pympler/
#

import sys
import json
import copy
import perf
import os
from pympler import asizeof

from codeguru_profiler_agent.utils.time import current_milli_time

sys.path += ["../src/", "src/"]
import codeguru_profiler_agent
from codeguru_profiler_agent.model.profile import Profile
from codeguru_profiler_agent.model.sample import Sample

# Increase recursion limit, to allow for deeper stacks
sys.setrecursionlimit(sys.getrecursionlimit() * 10)

INPUT_FILE = os.environ.get("INPUT_FILE")
PRINT_INFO = os.environ.get("PRINT_INFO") == "1"
MEMORY_INFO = os.environ.get("MEMORY_INFO") == "1"
SAMPLES_INJECTED_CAP = 125000

# Simple test profile:
# `wget "https://profiler-backend.amazon.com/v1/profiles/AmazonProfilerRubyAgentTestWebsite%2FTesting?start=1529391600000&end=1529395199999" -O test_input_simple.json.gz`
#
# Regular test profile:
# `wget "https://profiler-backend.amazon.com/v1/profiles/AmazonProfilerService%2FProd?start=1529485500000&end=1529486099999" -O test_input_profiler_small.json.gz`
#
# Don't forget to `gunzip` the result!

# Extract a stack sample from the current call_graph, modifying it in-place
# Note: The stack samples are in bottom-to-top format (which is compatible with the python sampling APIs, if a bit
# unexpected when coming in from other languages)
def scrape_stack_sample_from(call_graph_node, current_stack, is_root=False):
    state = decrement_state(call_graph_node)
    if not state:
        return False

    if not is_root:
        current_stack.append(call_graph_node["name"])

    if "children" in call_graph_node:
        for child_node in call_graph_node["children"]:
            changed = scrape_stack_sample_from(child_node, current_stack)
            if changed:
                return True

    return True

# Generator that returns stack samples for the given call graph, modifying it in-place
def scrape_stack_samples(call_graph_root):
    while True:
        stack = []
        scrape_stack_sample_from(call_graph_root, stack, is_root=True)

        if len(stack) > 0:
            yield stack
        else:
            break

# In-place decrements the states counter for the first positive state, if any
def decrement_state(call_graph_node):
    states = call_graph_node["states"]
    for state, count in states.items():
        if count > 0:
            states[state] -= 1
            return state
    return None

def inject_sample_loop(call_graph_root, samples_injected_cap):
    profile = Profile("benchmark", 0, 0, current_milli_time())

    for stack in scrape_stack_samples(call_graph_root):
        profile.add(Sample([stack]))
        if samples_injected_cap and profile.callgraph.runnable_count >= samples_injected_cap:
            break

    return profile

def load_and_create_profile(samples_injected_cap = SAMPLES_INJECTED_CAP):
    if not INPUT_FILE:
        raise Exception("Please specify INPUT_FILE env flag")
    input_call_graph = json.load(open(INPUT_FILE))["profileData"]
    return inject_sample_loop(input_call_graph, samples_injected_cap)

def print_stats_for(profile):
    print("Profile number of samples: " + str(profile.callgraph.runnable_count))
    maximum_object_graph_depth_for_measurement = 2**32
    print("Profile size (bytes): " + str(asizeof.asizeof(profile, limit=maximum_object_graph_depth_for_measurement)))

if PRINT_INFO:
    print("Using python " + sys.version)
    print("Samples injected cap: " + str(SAMPLES_INJECTED_CAP))

if MEMORY_INFO:
    print("Getting memory info...")
    print_stats_for(load_and_create_profile(samples_injected_cap=None)) # No samples cap when printing memory info

runner = perf.Runner()
runner.bench_func("load_and_create_profile", load_and_create_profile)
