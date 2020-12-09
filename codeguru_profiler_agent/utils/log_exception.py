
def log_exception(logger, message):
    logger.info(message)
    logger.debug("Caught exception: ", exc_info=True)
