import pytest
import os
import threading

_pytestutils_before_global_counter = 0
_pytestutils_before_global_lock = threading.Lock()


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
