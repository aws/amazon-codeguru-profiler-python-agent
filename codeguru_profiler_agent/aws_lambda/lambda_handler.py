import os
import logging
from codeguru_profiler_agent.aws_lambda.profiler_decorator import with_lambda_profiler
from codeguru_profiler_agent.agent_metadata.aws_lambda import HANDLER_ENV_NAME_FOR_CODEGURU_KEY
HANDLER_ENV_NAME = "_HANDLER"
logger = logging.getLogger(__name__)


def restore_handler_env(original_handler, env=os.environ):
    env[HANDLER_ENV_NAME] = original_handler


def load_handler(bootstrap_module, env=os.environ, original_handler_env_key=HANDLER_ENV_NAME_FOR_CODEGURU_KEY):
    try:
        original_handler_name = env.get(original_handler_env_key)
        if not original_handler_name:
            raise ValueError("Could not find module and function name from " + HANDLER_ENV_NAME_FOR_CODEGURU_KEY
                             + " environment variable")

        # Delegate to the lambda code to load the customer's module.
        if hasattr(bootstrap_module, '_get_handler'):
            customer_handler_function = bootstrap_module._get_handler(original_handler_name)
        else:
            # TODO FIXME Review if the support for python 3.6 bootstrap can be improved.
            # This returns both a init_handler and the function, we apply the init right away as we are in init process
            init_handler, customer_handler_function = bootstrap_module._get_handlers(
                handler=original_handler_name,
                mode='event',  # with 'event' it will return the function as is (handlerfn in the lambda code)
                               # 'http' would return wsgi.handle_one(sockfd, ('localhost', 80), handlerfn) instead
                invokeid='unknown_id')  # FIXME invokeid is used for error handling, need to see if we can get it
            init_handler()
        restore_handler_env(original_handler_name, env)
        return customer_handler_function
    except:
        # Using print here as logger would probably not be properly initiated at this point.
        print("Could not load the handler function to decorate it with CodeGuru Profiler."
              + " If the exception error does not help you, please try removing the CodeGuru Profiler layer"
              + " from your lambda function and contact AWS support.")
        raise


# Load the customer's handler, this should be done at import time which means it is done when lambda frameworks
# loads our module. We load the bootstrap module by string name so that IDE does not complain
lambda_bootstrap_module = __import__("bootstrap")
handler_function = load_handler(lambda_bootstrap_module)


# WARNING: Do not rename this file, this function or HANDLER_ENV_NAME_FOR_CODEGURU without changing the bootstrap script
@with_lambda_profiler()
def call_handler(event, context):
    return handler_function(event, context)
