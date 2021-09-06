from test.pytestutils import before
import sys
import os
import pytest


def handler_function(event, context):
    if event == "expected_event" and context == "expected_context":
        return "expected result"
    return "wrong result"


init_handler_has_been_called = False
python36_extractor_has_been_called = False


def init_handler():
    global init_handler_has_been_called
    init_handler_has_been_called = True


class BootstrapModuleMock:
    def _get_handler(self, handler):
        if handler == "handler_module.handler_function":
            return handler_function


class BootstrapPython36ModuleMock:
    # for python3.6 version of lambda runtime bootstrap
    def _get_handlers(self, handler, mode, invokeid):
        global python36_extractor_has_been_called
        python36_extractor_has_been_called = True
        if handler == "handler_module.handler_function" and mode == "event":
            return init_handler, handler_function


class RicBootstrapModuleMock:
    def _get_handler(self, handler):
        if handler == "handler_module.handler_function":
            return handler_function


class TestLambdaHandler:
    class TestWhenLambdaHandlerModuleIsLoaded:
        @pytest.fixture(autouse=True)
        def around(self):
            # simulate that we are in a lambda environment where the bootstrap module is available
            os.environ['HANDLER_ENV_NAME_FOR_CODEGURU'] = 'handler_module.handler_function'
            sys.modules['bootstrap'] = BootstrapModuleMock()
            yield
            del sys.modules['bootstrap']
            del os.environ['HANDLER_ENV_NAME_FOR_CODEGURU']
            if '_HANDLER' in os.environ:
                del os.environ['_HANDLER']

        def test_it_loads_the_handler_function(self):
            import codeguru_profiler_agent.aws_lambda.lambda_handler as lambda_handler_module
            assert lambda_handler_module.handler_function == handler_function

        def test_call_handler_calls_the_inner_handler(self):
            import codeguru_profiler_agent.aws_lambda.lambda_handler as lambda_handler_module
            assert lambda_handler_module.call_handler(event="expected_event",
                                                      context="expected_context") == "expected result"

    class TestGetHandlerExtractor:
        class TestWhenRicIsAvailable:
            @pytest.fixture(autouse=True)
            def around(self):
                # simulate that we are in a lambda environment where the awslambdaric.bootstrap module is available
                self.module_available = RicBootstrapModuleMock()
                sys.modules['awslambdaric.bootstrap'] = self.module_available
                yield
                del sys.modules['awslambdaric.bootstrap']

            def test_it_loads_the_ric_module_code(self):
                from codeguru_profiler_agent.aws_lambda.lambda_handler import get_lambda_handler_extractor
                result = get_lambda_handler_extractor()
                assert result == self.module_available._get_handler

        class TestWhenLambdaBootstrapIsAvailable:
            @pytest.fixture(autouse=True)
            def around(self):
                # simulate that we are in a lambda environment where the awslambdaric.bootstrap module is not available
                # but bootstrap from lambda is available.
                self.module_available = BootstrapModuleMock()
                if 'awslambdaric.bootstrap' in sys.modules:
                    del sys.modules['awslambdaric.bootstrap']
                sys.modules['bootstrap'] = self.module_available
                yield
                del sys.modules['bootstrap']

            def test_it_loads_the_lambda_module_code(self):
                from codeguru_profiler_agent.aws_lambda.lambda_handler import get_lambda_handler_extractor
                result = get_lambda_handler_extractor()
                assert result == self.module_available._get_handler

        class TestWhenPython36LambdaBootstrapCalls:
            class TestWhenHandlerEnvIsSetProperly:
                @pytest.fixture(autouse=True)
                def around(self):
                    # simulate that we are in a lambda environment where the awslambdaric.bootstrap module is available
                    sys.modules['bootstrap'] = BootstrapPython36ModuleMock()
                    global init_handler_has_been_called
                    init_handler_has_been_called = False
                    global python36_extractor_has_been_called
                    python36_extractor_has_been_called = False
                    yield
                    del sys.modules['bootstrap']

                def test_it_uses_the_old_bootstrap_code(self):
                    from codeguru_profiler_agent.aws_lambda.lambda_handler import get_lambda_handler_extractor
                    # call extractor
                    get_lambda_handler_extractor()("handler_module.handler_function")
                    assert python36_extractor_has_been_called

                def test_it_calls_the_init_handler(self):
                    from codeguru_profiler_agent.aws_lambda.lambda_handler import get_lambda_handler_extractor
                    # call extractor
                    get_lambda_handler_extractor()("handler_module.handler_function")
                    assert init_handler_has_been_called

    class TestLoadHandlerFunction:
        class TestWhenHandlerEnvIsSetProperly:
            @before
            def before(self):
                self.extractor = BootstrapModuleMock()._get_handler
                self.env = {"HANDLER_ENV_NAME_FOR_CODEGURU": "handler_module.handler_function"}

            def test_it_returns_the_handler_function(self):
                from codeguru_profiler_agent.aws_lambda.lambda_handler import load_handler
                assert load_handler(self.extractor, self.env) == handler_function

            def test_it_resets_handler_env_variable(self):
                from codeguru_profiler_agent.aws_lambda.lambda_handler import load_handler
                load_handler(self.extractor, self.env)
                assert self.env['_HANDLER'] == "handler_module.handler_function"

        class TestWhenHandlerEnvIsMissing:
            @before
            def before(self):
                self.extractor = BootstrapModuleMock()._get_handler
                self.env = {}

            def test_it_throws_value_error(self):
                with pytest.raises(ValueError):
                    from codeguru_profiler_agent.aws_lambda.lambda_handler import load_handler
                    load_handler(self.extractor, self.env)
