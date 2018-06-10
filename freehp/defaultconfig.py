# coding=utf-8

log_file = None
log_level = 'INFO'
log_format = '%(asctime)s %(name)s [%(levelname)s] %(message)s'
log_dateformat = '%Y-%m-%d %H:%M:%S'

daemon = False

bind = '0.0.0.0:6256'

block_time = 7200
max_fail_times = 2

check_interval = 300
checker_cls = 'freehp.checker.HttpbinChecker'
checker_clients = 100

scrap_interval = 300
spider_timeout = 30
spider_sleep_time = 5
spider_headers = {
    'Connection': 'keep-alive',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.181 Safari/537.36',
    'Accept-Encoding': 'gzip, deflate, sdch',
    'Accept-Language': 'zh-CN,zh;q=0.8'
}
proxy_pages = None
