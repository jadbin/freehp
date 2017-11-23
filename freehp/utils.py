# coding=utf-8

import logging
from importlib import import_module

import yaml


def load_config_file(file):
    with open(file, "r", encoding="utf-8") as f:
        d = yaml.load(f)
        return d


def load_object(path):
    if isinstance(path, str):
        dot = path.rindex(".")
        module, name = path[:dot], path[dot + 1:]
        mod = import_module(module)
        return getattr(mod, name)
    return path


def configure_logging(name, config):
    log_level = config.get('log_level')
    log_format = config.get('log_format')
    log_dateformat = config.get('log_dateformat')
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    filename = config.get('log_file')
    if filename:
        handler = logging.FileHandler(filename)
    else:
        handler = logging.StreamHandler()
    handler.setLevel(log_level)
    formatter = logging.Formatter(log_format, log_dateformat)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
