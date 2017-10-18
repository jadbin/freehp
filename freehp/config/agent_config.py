# coding=utf-8

import sys

from freehp.config import BaseConfig

LOG_FILE = None
LOG_ENCODING = "utf-8"
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s %(name)s [%(levelname)s]: %(message)s"
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S"

AGENT_LISTEN = "0.0.0.0:8081"
AGENT_AUTH = None
DATA_DIR = "./"

SPIDER_CONFIG = "http://rawcdn.githack.com/jadbin/freehp-config/master/spider.yaml"

QUEUE_SIZE = 1000
BLOCK_TIME = 7200
MAX_FAIL_TIMES = 2

CHECKER_CLIENTS = 100
CHECK_INTERVAL = 300
CHECKER_CLS = "freehp.checker.HttpbinChecker"


class AgentConfig(BaseConfig):
    def __init__(self, values=None, priority="project"):
        super().__init__()
        mod = sys.modules[__name__]
        for key in dir(mod):
            if key.isupper():
                self.set(key.lower(), getattr(mod, key), "default")
        self.update(values, priority)
