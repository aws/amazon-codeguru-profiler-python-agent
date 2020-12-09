import pytest
import test.pytestutils as pytestutils


def pytest_runtest_setup(item):
    if pytestutils._pytestutils_is_there_any_test_marked_with_focus and not item.get_marker(
            name='pytestutils_focus'):
        pytest.skip("Test skipped in focus mode")
