# coding=utf-8

import copy
from collections import MutableMapping
import types

from freehp import defaultconfig


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
        for key in dir(defaultconfig):
            if not key.startswith("_"):
                value = getattr(defaultconfig, key)
                if not isinstance(value, (types.FunctionType, types.ModuleType, type)):
                    self.set(key.lower(), value)
        self.update(values)
