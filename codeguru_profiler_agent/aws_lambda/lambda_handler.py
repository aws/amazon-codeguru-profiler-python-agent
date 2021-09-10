import os
import importlib
from codeguru_profiler_agent.aws_lambda.profiler_decorator import with_lambda_profiler
from codeguru_profiler_agent.agent_metadata.aws_lambda import HANDLER_ENV_NAME_FOR_CODEGURU_KEY
HANDLER_ENV_NAME = "_HANDLER"


def restore_handler_env(original_handler, env=os.environ):
    env[HANDLER_ENV_NAME] = original_handler


def load_handler(handler_extractor, env=os.environ, original_handler_env_key=HANDLER_ENV_NAME_FOR_CODEGURU_KEY):
    try:
        original_handler_name = env.get(original_handler_env_key)
        if not original_handler_name:
            raise ValueError("Could not find module and function name from " + HANDLER_ENV_NAME_FOR_CODEGURU_KEY
                             + " environment variable")

        # Delegate to the lambda code to load the customer's module and function.
        customer_handler_function = handler_extractor(original_handler_name)

        restore_handler_env(original_handler_name, env)
        return customer_handler_function
    except:
        # Using print here as logger would probably not be properly initiated at this point.
        print("Could not load the handler function to decorate it with CodeGuru Profiler."
              + " If the exception error does not help you, please try removing the CodeGuru Profiler layer"
              + " from your lambda function and contact AWS support.")
        raise


def _python36_extractor(bootstrap_module, original_handler_name):
    """
    The lambda bootstrap code for python 3.6 was different than for later versions, instead of the _get_handler
    function there was a more complex _get_handlers function with more parameters
    """
    # TODO FIXME Review if the support for python 3.6 bootstrap can be improved.
    # This returns both a init_handler and the function, we apply the init right away as we are in init process
    init_handler, customer_handler_function = bootstrap_module._get_handlers(
        handler=original_handler_name,
        mode='event',  # with 'event' it will return the function as is (handlerfn in the lambda code)
        # 'http' would return wsgi.handle_one(sockfd, ('localhost', 80), handlerfn) instead
        invokeid='unknown_id')  # FIXME invokeid is used for error handling, need to see if we can get it
    init_handler()
    return customer_handler_function


def get_lambda_handler_extractor():
    """
    This loads and returns a function from lambda or RIC source code that is able to load the customer's
    handler function.
    WARNING !! This is a bit dangerous since we are calling internal functions from other modules that we do not
    officially depend on. The idea is that this code should run only in a lambda function environment where we can know
    what is available. However if lambda developers decide to change their internal code it could impact this !
    """
    # First try to load the lambda RIC if it is available (i.e. python 3.9)
    # See https://github.com/aws/aws-lambda-python-runtime-interface-client
    ric_bootstrap_module = _try_to_load_module("awslambdaric.bootstrap")
    if ric_bootstrap_module is not None and hasattr(ric_bootstrap_module, '_get_handler'):
        return ric_bootstrap_module._get_handler

    # If no RIC module is available there should be a bootstrap module available
    # do not catch ModuleNotFoundError exceptions here as we cannot do anything if this fails.
    bootstrap_module = importlib.import_module("bootstrap")
    if hasattr(bootstrap_module, '_get_handler'):
        return bootstrap_module._get_handler
    else:
        return lambda handler_name: _python36_extractor(bootstrap_module, handler_name)


def _try_to_load_module(module_name):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None


# We need to load the customer's handler function since the lambda framework loaded our function instead.
# We want to delegate this work to the lambda framework so we need to find the appropriate method that does it
# (depends on python versions) so we can call it.
# This should be done at import time which means it is done when lambda frameworks loads our module
handler_extractor = get_lambda_handler_extractor()

# Now load the actual customer's handler function.
handler_function = load_handler(handler_extractor)


# WARNING: Do not rename this file, this function or HANDLER_ENV_NAME_FOR_CODEGURU without changing the bootstrap script
@with_lambda_profiler()
def call_handler(event, context):
    return handler_function(event, context)
