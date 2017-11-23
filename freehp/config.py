# coding=utf-8

import copy
from collections import MutableMapping
import types

from . import defaultconfig

CONFIG_PRIORITIES = {
    "default": 0,
    "project": 10,
    "cmdline": 20
}


def get_config_priority(priority):
    if isinstance(priority, str):
        return CONFIG_PRIORITIES[priority]
    else:
        return priority


class ConfigAttribute:
    def __init__(self, value, priority):
        self.value = value
        self.priority = priority

    def set(self, value, priority):
        if priority >= self.priority:
            self.value = value
            self.priority = priority

    def __repr__(self):
        return "<ConfigAttribute value={self.value!r} priority={self.priority}>".format(self=self)


class BaseConfig(MutableMapping):
    def __init__(self, values=None, priority="project"):
        self.attributes = {}
        self.update(values, priority)

    def __getitem__(self, opt_name):
        if opt_name not in self:
            return None
        return self.attributes[opt_name].value

    def __contains__(self, name):
        return name in self.attributes

    def get(self, name, default=None):
        return self[name] if self[name] is not None else default

    def getbool(self, name, default=None):
        v = self.get(name, default)
        try:
            return bool(int(v))
        except (ValueError, TypeError):
            if v in ("True", "true"):
                return True
            if v in ("False", "false"):
                return False
        return None

    def getint(self, name, default=None):
        v = self.get(name, default)
        try:
            return int(v)
        except (ValueError, TypeError):
            pass
        return None

    def getfloat(self, name, default=None):
        v = self.get(name, default)
        try:
            return float(v)
        except (ValueError, TypeError):
            pass
        return None

    def getlist(self, name, default=None):
        v = self.get(name, default)
        if v is None:
            return None
        if isinstance(v, str):
            v = v.split(",")
        elif not hasattr(v, "__iter__"):
            v = [v]
        return list(v)

    def getpriority(self, name):
        if name not in self:
            return None
        return self.attributes[name].priority

    def __setitem__(self, name, value):
        self.set(name, value)

    def set(self, name, value, priority="project"):
        priority = get_config_priority(priority)
        if name not in self:
            if isinstance(value, ConfigAttribute):
                self.attributes[name] = value
            else:
                self.attributes[name] = ConfigAttribute(value, priority)
        else:
            self.attributes[name].set(value, priority)

    def update(self, values, priority="project"):
        if values is not None:
            if isinstance(values, BaseConfig):
                for name in values:
                    self.set(name, values[name], values.getpriority(name))
            else:
                for name, value in values.items():
                    self.set(name, value, priority)

    def delete(self, name, priority="project"):
        priority = get_config_priority(priority)
        if priority >= self.getpriority(name):
            del self.attributes[name]

    def __delitem__(self, name):
        del self.attributes[name]

    def copy(self):
        return copy.deepcopy(self)

    def __iter__(self):
        return iter(self.attributes)

    def __len__(self):
        return len(self.attributes)


class Config(BaseConfig):
    def __init__(self, values=None, priority="project"):
        super().__init__()
        for key in dir(defaultconfig):
            if not key.startswith("_"):
                value = getattr(defaultconfig, key)
                if not isinstance(value, (types.FunctionType, types.ModuleType, type)):
                    self.set(key.lower(), value, "default")
        self.update(values, priority)
