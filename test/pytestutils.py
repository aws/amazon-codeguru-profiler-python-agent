import pytest
import os
import threading

_pytestutils_before_global_counter = 0
_pytestutils_before_global_lock = threading.Lock()

_pytestutils_is_there_any_test_marked_with_focus = False


def before(before_function):
    """
    Decorator for tagging a function as running before the tests. This works by decorating it further with a
    pytest.fixture(autouse=True) which makes pytest automatically trigger its execution before the tests.

    Additionally, this function keeps a global counter that's used to generate unique names for the pytest fixtures,
    as otherwise they would take their name from the function being decorated, which would "break" nested use, e.g.
    consider:

        class TestA:
            @pytest.fixture(autouse=True)
            def before(self):
                print("This is the top level before")

            class TestB:
                @pytest.fixture(autouse=True)
                def before(self):
                    print("this is the inner before")

                def test_it_does_stuff(self):
                    print("this is the test")

    This does not run both before functions (as the inner one shadows the outer one), whereas with our decorator

        class TestA:
            @custom_before
            def before(self):
                print("This is the top level before")

            class TestB:
                @custom_before
                def before(self):
                    print("this is the inner before")

                def test_it_does_stuff(self):
                    print("this is the test")

    works as expected.
    """
    global _pytestutils_before_global_counter

    with _pytestutils_before_global_lock:
        unique_fixture_name = \
            "wrapped_before_{}".format(_pytestutils_before_global_counter)
        _pytestutils_before_global_counter += 1

    return pytest.fixture(
        autouse=True, name=unique_fixture_name)(before_function)


def focus(decorated_test):
    """
    Decorator for tagging a function or class as being in focus, and to switch the test suite execution to "focused
    execution mode". When the test suite is in "focused execution mode", only functions and classes marked with @focus
    are run, all others are skipped.

    When there are no functions/classes marked with @focus, the test suite goes back to the usual mode, and all tests
    are run.

    The focused execution mode is useful for quickly and without needing to edit any more configuration/files selecting
    only a subset of the tests for execution, to speed up testing cycles.

    This decorator is inspired by similar IDE features (e.g. https://blogs.oracle.com/geertjan/run-focused-test-method )
    and other test libraries (e.g. https://medium.com/table-xi/focus-your-rspec-workflow-4cd5798d2a3e ).

    Limitation when used with Pytest < 3.6: @focus does not extend to nested classes, see
    https://github.com/pytest-dev/pytest/issues/199 and https://github.com/pytest-dev/pytest/pull/3317 for details.

    This feature is broken into several pieces:
    * The @focus decorator sets a global variable to trigger the focused execution mode, and additionally marks any
      test method or class with the "pytestutils_focus" marker
    * In pytestutils_focus.py a pytest plugin is provided that when in focused execution mode, skips any tests not
      marked with the "pytestutils_focus" marker
    * In conftest.py we enable the pytest plugin
    """
    _validate_focus_enabled()

    global _pytestutils_is_there_any_test_marked_with_focus

    _pytestutils_is_there_any_test_marked_with_focus = True

    return pytest.mark.pytestutils_focus(decorated_test)


def _validate_focus_enabled():
    if os.environ.get("PYTESTUTILS_ALLOW_FOCUS") in ("1", "true", "yes"):
        return
    raise RuntimeError("""
Found tests annotated with @focus decorator, but the PYTESTUTILS_ALLOW_FOCUS environment variable is not set in the
current environment.

If you found this error in a CI environment, it means someone committed test code with a @focus annotation -- please
check for and remove it from the codebase.

If you found this error and you wanted to use @focus for your own development work, please add a PYTESTUTILS_ALLOW_FOCUS
enviroment variable set to 1 (e.g. `export PYTESTUTILS_ALLOW_FOCUS=1`) to your execution environment to make this error
go away.

Thanks for using @focus!
        """)
