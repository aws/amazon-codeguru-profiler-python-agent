"""
This module handles all interactions with python sys and traceback library for sampling.
"""
import linecache
import threading
import traceback

from codeguru_profiler_agent.model.frame import Frame

TRUNCATED_FRAME = Frame(name="<Truncated>")

TIME_SLEEP_FRAME = Frame(name="<Sleep>")


def get_stacks(threads_to_sample, excluded_threads, max_depth):
    """
    Attempts to extract the call stacks for the threads listed in threads_to_sample.

    :param threads_to_sample: list of threads to be sampled, expected in the same format as sys._current_frames().items()
    :param excluded_threads: set of thread names to be excluded from sampling
    :param max_depth: the maximum number of frames a stack can have
    :returns: a list of lists of call stacks of all chosen threads; any thread stacks deeper than max_depth will be truncated and the TRUNCATED_FRAME_NAME will be added as a replacement of the **TOPMOST** frames of the stack
    """
    stacks = []
    if max_depth < 0:
        max_depth = 0
    for thread_id, end_frame in threads_to_sample:
        if _is_excluded(thread_id, excluded_threads):
            continue

        stacks.append(_extract_frames(end_frame, max_depth))

    return stacks


def _is_zombie(thread):
    return True if thread is None else False


def _is_excluded(thread_id, excluded_threads):
    thread = threading._active.get(thread_id)
    return _is_zombie(thread) or thread.name in excluded_threads


def _extract_class(frame_locals):
    """
    See https://stackoverflow.com/questions/2203424/python-how-to-retrieve-class-information-from-a-frame-object/2544639#2544639
    for the details behind the implementation. The way to use to extract class from method relies on the fact that
    "self" is passed as an argument in the function and it points to the class which owns this function.
    """
    try:
        return frame_locals['self'].__class__.__name__
    except Exception:
        # Fail to get the class name should not block the whole sample
        return None


def _extract_stack(stack, max_depth):
    """Create a list of Frame from a list of FrameSummary.

    :param stack: A list of FrameSummary.
    """
    result = []
    for raw_frame, line_no in stack:
        co = raw_frame.f_code
        result.append(
            Frame(name=co.co_name, class_name=_extract_class(raw_frame.f_locals), line_no=line_no,
                  file_path=co.co_filename)
        )
    if len(stack) < max_depth:
        last_frame, last_frame_line_no = stack[-1]
        _maybe_append_time_sleep(result, last_frame, last_frame_line_no)
    return result


def _maybe_append_time_sleep(result, frame, line_no):
    line = linecache.getline(frame.f_code.co_filename, line_no).strip()
    if "sleep(" in line:
        result.append(TIME_SLEEP_FRAME)


def _extract_frames(end_frame, max_depth):
    stack = list(traceback.walk_stack(end_frame))[::-1][0:max_depth]
    stack_entries = _extract_stack(stack, max_depth)

    if len(stack_entries) == max_depth:
        stack_entries[-1] = TRUNCATED_FRAME

    return stack_entries
