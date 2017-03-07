# coding=utf-8

from os.path import dirname, join
from freehp.utils.config import load_config_file

LOG_FILE = None
LOG_ENCODING = "utf-8"
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s %(name)s [%(levelname)s]: %(message)s"
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S"

AGENT_LISTEN = "0.0.0.0:8081"
DATA_DIR = "./"

SPIDER_UPDATE_TIME = 300
SPIDER_TIMEOUT = 30
SPIDER_SLEEP_TIME = 10

PROXY_QUEUE_SIZE = 500
PROXY_BACKUP_SIZE = 10000
PROXY_CHECKER_CLIENTS = 100
PROXY_CHECK_INTERVAL = 300
PROXY_BLOCK_TIME = 7200
PROXY_FAIL_TIMES = 3

_core_config = load_config_file(join(dirname(__file__), "core.yaml"))
INITIAL_PAGES = _core_config.get("initial_pages")
UPDATE_PAGES = _core_config.get("update_pages")
SCRAPER_RULES = _core_config.get("scraper_rules")
SPIDER_HEADERS = _core_config.get("spider_headers")
