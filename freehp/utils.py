# coding=utf-8

import os
from os.path import isfile
import logging
from importlib import import_module
from asyncio import CancelledError
import inspect

import aiohttp
import async_timeout
import json


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


def iter_settings(config):
    for key, value in config.items():
        if not key.startswith('_') and not inspect.ismodule(value) and not inspect.isfunction(value):
            yield key, value


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


def be_daemon():
    if os.fork():
        os._exit(0)
    os.setsid()
    if os.fork():
        os._exit(0)
    os.umask(0o22)
    os.closerange(0, 3)
    fd_null = os.open(os.devnull, os.O_RDWR)
    if fd_null != 0:
        os.dup2(fd_null, 0)
    os.dup2(fd_null, 1)
    os.dup2(fd_null, 2)


async def get_origin_ip(loop):
    import re
    ip = None
    ip_reg = re.compile('^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$')
    try:
        async with aiohttp.ClientSession(loop=loop) as session:
            with async_timeout.timeout(30, loop=loop):
                async with session.request('GET', 'http://httpbin.org/get') as resp:
                    body = await resp.read()
                    data = json.loads(body.decode())
                    ip = data['origin']
        assert ip_reg.match(ip) is not None
    except CancelledError:
        raise
    except Exception:
        pass
    return ip
