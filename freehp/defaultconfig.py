# coding=utf-8

log_file = None
log_encoding = 'utf-8'
log_level = 'INFO'
log_format = '%(asctime)s %(name)s [%(levelname)s]: %(message)s'
log_dateformat = '%Y-%m-%d %H:%M:%S'

agent_listen = '0.0.0.0:8081'
agent_auth = None
data_dir = './'

spider_config = 'http://rawcdn.githack.com/jadbin/freehp-config/master/spider.yaml'

queue_size = 1000
block_time = 7200
max_fail_times = 2

checker_clients = 100
check_interval = 300
checker_cls = 'freehp.checker.HttpbinChecker'
