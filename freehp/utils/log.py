# coding=utf-8

import logging


def configure_logging(config):
    logger = logging.getLogger("freehp")
    logger.setLevel(config["log_level"])
    log_stream_handler = logging.StreamHandler()
    log_stream_handler.setLevel(config["log_level"])
    log_formatter = logging.Formatter(config["log_format"], config["log_dateformat"])
    log_stream_handler.setFormatter(log_formatter)
    logger.addHandler(log_stream_handler)
