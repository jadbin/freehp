# coding=utf-8

from os.path import isfile

import logging
from importlib import import_module


def load_object(path):
    if isinstance(path, str):
        dot = path.rindex(".")
        module, name = path[:dot], path[dot + 1:]
        mod = import_module(module)
        return getattr(mod, name)
    return path


def load_config(fname):
    if fname is None or not isfile(fname):
        raise ValueError('{} is not a file'.format(fname))
    code = compile(open(fname, 'rb').read(), fname, 'exec')
    cfg = {
        "__builtins__": __builtins__,
        "__name__": "__config__",
        "__file__": fname,
        "__doc__": None,
        "__package__": None
    }
    exec(code, cfg, cfg)
    return cfg


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
