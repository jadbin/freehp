# coding=utf-8

import copy
from collections import MutableMapping
import inspect


class BaseConfig(MutableMapping):
    def __init__(self, values=None):
        self.attributes = {}
        self.update(values)

    def __getitem__(self, opt_name):
        if opt_name not in self:
            return None
        return self.attributes[opt_name]

    def __contains__(self, name):
        return name in self.attributes

    def get(self, name, default=None):
        return self[name] if self[name] is not None else default

    def getbool(self, name, default=None):
        v = self.get(name, default)
        return getbool(v)

    def getint(self, name, default=None):
        v = self.get(name, default)
        return getint(v)

    def getfloat(self, name, default=None):
        v = self.get(name, default)
        return getfloat(v)

    def getlist(self, name, default=None):
        v = self.get(name, default)
        return getlist(v)

    def __setitem__(self, name, value):
        self.set(name, value)

    def set(self, name, value):
        self.attributes[name] = value

    def update(self, values):
        if values is not None:
            if isinstance(values, BaseConfig):
                for name in values:
                    self.set(name, values[name])
            else:
                for name, value in values.items():
                    self.set(name, value)

    def delete(self, name):
        del self.attributes[name]

    def __delitem__(self, name):
        del self.attributes[name]

    def copy(self):
        return copy.deepcopy(self)

    def __iter__(self):
        return iter(self.attributes)

    def __len__(self):
        return len(self.attributes)


def getbool(v):
    try:
        return bool(int(v))
    except (ValueError, TypeError):
        if v in ("True", "true"):
            return True
        if v in ("False", "false"):
            return False
    return None


def getint(v):
    try:
        return int(v)
    except (ValueError, TypeError):
        pass
    return None


def getfloat(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        pass
    return None


def getlist(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.split(",")
    elif not hasattr(v, "__iter__"):
        v = [v]
    return list(v)


class Config(BaseConfig):
    def __init__(self, values=None):
        super().__init__()
        for v in KNOWN_SETTINGS.values():
            self.set(v.name, v.value)
        self.update(values)


class Setting:
    name = None
    cli = None
    metavar = None
    default = None
    action = None
    type = None
    nargs = None
    short_desc = None

    def __init__(self):
        self.value = self.default

    def add_argument(self, parser):
        if self.cli is None:
            return
        args = tuple(self.cli)
        kwargs = {'dest': self.name, 'help': '{} (default: {})'.format(self.short_desc, self.default)}
        if self.metavar is not None:
            kwargs['metavar'] = self.metavar
        if self.action is not None:
            kwargs['action'] = self.action
        if self.type is not None:
            kwargs['type'] = self.type
        if self.nargs is not None:
            kwargs['nargs'] = self.nargs

        parser.add_argument(*args, **kwargs)


class Daemon(Setting):
    name = 'daemon'
    cli = ['-d', '--daemon']
    action = 'store_true'
    default = False
    short_desc = 'run in daemon mode'


class PidFile(Setting):
    name = 'pid_file'
    cli = ['--pid-file']
    metavar = 'FILE'
    short_desc = 'PID file'


class LogFile(Setting):
    name = 'log_file'
    cli = ['--log-file']
    metavar = 'FILE'
    short_desc = 'log file'


class LogLevel(Setting):
    name = 'log_level'
    cli = ['-l', '--log-level']
    metavar = 'LEVEL'
    default = 'INFO'
    short_desc = 'log level'


class LogFormat(Setting):
    name = 'log_format'
    default = '%(asctime)s %(name)s [%(levelname)s] %(message)s'


class LogDateformat(Setting):
    name = 'log_dateformat'
    default = '%Y-%m-%d %H:%M:%S'


class Bind(Setting):
    name = 'bind'
    cli = ['-b', '--bind']
    metavar = 'ADDRESS'
    default = '0.0.0.0:6256'
    short_desc = 'the socket to bind'


class BlockTime(Setting):
    name = 'block_time'
    default = 7200


class MaxFailTimes(Setting):
    name = 'max_fail_times'
    default = 3


class MinAnonymity(Setting):
    name = 'min_anonymity'
    cli = ['--min-anonymity']
    metavar = 'INT'
    default = 0
    type = int
    short_desc = 'minimum anonymity level, 0: transparent, 1: anonymous, 2: elite proxy'


class Checker(Setting):
    name = 'checker'
    default = 'freehp.checker.HttpbinChecker'


class CheckerTimeout(Setting):
    name = 'checker_timeout'
    cli = ['--checker-timeout']
    metavar = 'FLOAT'
    default = 10
    type = float
    short_desc = 'timeout of checker in seconds'


class CheckerClients(Setting):
    name = 'checker_clients'
    default = 100


class CheckInterval(Setting):
    name = 'check_interval'
    default = 300


class ScrapInterval(Setting):
    name = 'scrap_interval'
    default = 300


class SpiderTimeout(Setting):
    name = 'spider_timeout'
    default = 30


class SpiderSleepTime(Setting):
    name = 'spider_sleep_time'
    default = 5


class SpiderHeaders(Setting):
    name = 'spider_headers'
    default = {
        'Connection': 'keep-alive',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.181 Safari/537.36',
        'Accept-Encoding': 'gzip, deflate, sdch',
        'Accept-Language': 'zh-CN,zh;q=0.8'
    }


class ProxyPages(Setting):
    name = 'proxy_pages'


class Address(Setting):
    name = 'address'


KNOWN_SETTINGS = {}

for _v in list(vars().values()):
    if inspect.isclass(_v) and issubclass(_v, Setting) and _v.name is not None:
        KNOWN_SETTINGS[_v.name] = _v()
