import pytest
import os
from codeguru_profiler_agent.__main__ import main
from codeguru_profiler_agent.profiler_builder import PG_NAME_ENV, ENABLED_ENV


class TestMain:
    @pytest.fixture(autouse=True)
    def around(self):
        # create a script file containing python code
        # this script will create a flag file so we can check if it was called correctly
        # existence of the flag file proves the script was called
        # the script also throws an exception if not passed the expected arguments
        self.script_file_name = 'script_file_for_test_main.py'
        self.flag_file_name = 'flag_file_for_main_test'
        self._write_script_file()
        self._clean_flag_file()
        yield
        self._clean_flag_file()
        self._clean_script_file()

    def test_it_starts_given_script_with_script_arguments(self):
        args = [self.script_file_name, '--where', 'zoo', 'foo']
        main(input_args=args)
        assert self._script_was_called()

    def test_it_starts_given_module_with_script_arguments(self):
        args = ['-m', self.script_file_name[:-3], '--where', 'zoo', 'foo']
        main(input_args=args)
        assert self._script_was_called()

    def test_it_passes_script_arguments_and_checks_the_values_of_all_arguments(self):
        args = [self.script_file_name, 'one', 'two', 'three']
        with pytest.raises(ValueError) as ve:
            main(input_args=args)
        assert str(ve.value).endswith("['setup.py', 'one', 'two', 'three']")

    def test_it_passes_script_arguments_and_checks_the_values_of_all_arguments_when_no_client_arguments_are_set(self):
        args = [self.script_file_name]
        with pytest.raises(ValueError) as ve:
            main(input_args=args)
        assert str(ve.value).endswith("['setup.py']")

    def test_it_exits_if_no_arguments(self):
        with pytest.raises(SystemExit) as se:
            main(input_args=[])
        assert se.value.code == 2

    def test_it_can_take_profiler_options_as_argument(self):
        args = ['-p', 'pg_name', '-r', 'eu-north-1', '-c', 'test-cred-profile', '--log', 'info',
                self.script_file_name, '--where', 'zoo', 'foo']
        main(input_args=args, start_profiler=lambda *rargs: True)
        assert self._script_was_called()

    def test_it_creates_profiler_with_provided_argument(self):
        args = ['-p', 'pg_name', '-r', 'eu-north-1', '-c', 'test-cred-profile', '--log', 'info',
                self.script_file_name, '--where', 'zoo', 'foo']
        ran_start_profiler = False

        def mock_start_profiler(options, env):
            nonlocal ran_start_profiler
            ran_start_profiler = True
            assert options.profiling_group_name == 'pg_name'
            assert options.region == 'eu-north-1'
            assert options.credential_profile == 'test-cred-profile'
            assert env == os.environ

        main(args, start_profiler=mock_start_profiler)
        assert ran_start_profiler

    def test_it_can_take_profiler_options_from_env(self):
        args = [self.script_file_name, '--where', 'zoo', 'foo']
        env = {PG_NAME_ENV: 'pg_name'}
        main(input_args=args, env=env)
        assert self._script_was_called()

    def test_it_can_run_a_module(self):
        args = ['-m', self.script_file_name[:-3], '--where', 'zoo', 'foo']
        main(input_args=args)
        assert self._script_was_called()

    def test_it_does_not_create_profiler_if_enabled_is_false(self):
        args = ['-p', 'pg_name', self.script_file_name, '--where', 'zoo', 'foo']
        env = {ENABLED_ENV: 'false'}
        main(input_args=args, env=env)
        from codeguru_profiler_agent.__main__ import profiler
        assert profiler is None

    def test_it_creates_profiler_if_enabled_is_true(self):
        args = ['-p', 'pg_name', self.script_file_name, '--where', 'zoo', 'foo']
        env = {ENABLED_ENV: 'true'}
        main(input_args=args, env=env)
        from codeguru_profiler_agent import Profiler
        from codeguru_profiler_agent.__main__ import profiler
        assert profiler is not None
        assert isinstance(profiler, Profiler)

    def _script_was_called(self):
        return os.path.exists(self.flag_file_name)

    def _clean_flag_file(self):
        if os.path.exists(self.flag_file_name):
            os.remove(self.flag_file_name)

    def _write_script_file(self):
        script_file = open(self.script_file_name, 'w')
        script_file.write("""import sys
if sys.argv != ['setup.py', '--where', 'zoo', 'foo']:
    raise ValueError('Wrong values of arguments, found ' + str(sys.argv))
open('{flag_file_name}','w')
""".format(script=self.script_file_name, flag_file_name=self.flag_file_name))
        script_file.close()

    def _clean_script_file(self):
        if os.path.exists(self.script_file_name):
            os.remove(self.script_file_name)
