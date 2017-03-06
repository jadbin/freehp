# coding=utf-8

from os.path import join, dirname
from freehp.utils.config import load_config_file

default_config = {
    "log_file": None,
    "log_encoding": "utf-8",
    "log_level": "INFO",
    "log_format": "%(asctime)s %(name)s [%(levelname)s]: %(message)s",
    "log_dateformat": "%Y-%m-%d %H:%M:%S",
    "agent_listen": "0.0.0.0:8080",
    "spider_update_time": 300,
    "spider_timeout": 30,
    "spider_sleep_time": 10,
    "data_dir": "./",
    "proxy_queue_size": 500,
    "proxy_backup_size": 10000,
    "proxy_checker_clients": 100,
    "proxy_check_interval": 300,
    "proxy_block_time": 7200,
    "proxy_fail_times": 3
}

core_config = load_config_file(join(dirname(__file__), "core.yaml"))
for k, v in core_config.items():
    default_config[k] = v
