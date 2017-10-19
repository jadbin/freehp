# coding=utf-8

from os.path import join
import json
import time
import asyncio
import logging
from asyncio.queues import Queue
from io import StringIO
import yaml

from aiohttp import web, ClientSession
import async_timeout

from freehp.data import ProxyInfo, ProxyDb, PriorityQueue
from freehp.spider import ProxySpider
from freehp.utils.project import load_object
from freehp.utils.config import load_config_file
from freehp.errors import DownloadingError
from freehp.config import BaseConfig

log = logging.getLogger(__name__)


class ProxyAgent:
    def __init__(self, config):
        self.config = config
        self._loop = asyncio.new_event_loop()
        config.set('loop', self._loop)

        self._proxy_db = ProxyDb(join(config.get("data_dir"), "freehp-agent.db"))
        self._proxy_db.create_table()

        self._checker = self._load_checker(config.get("checker_cls"))
        self._checker_clients = config.getint("checker_clients")

        self._check_interval = config.getint("check_interval")
        self._block_time = config.getint("block_time")
        self._proxy_queue = ProxyQueue(config.getint("queue_size"), max_fail_times=config.getint("max_fail_times"))

        self._spider = ProxySpider(self._get_spider_config(config.get('spider_config')))

        self._agent_listen = config.get("agent_listen")

        self._futures = []
        self._wait_queue = Queue(loop=self._loop)
        self._is_running = False

    def start(self):
        if not self._is_running:
            self._is_running = True
            asyncio.set_event_loop(self._loop)
            self._init_server()
            self._init_checker()
            self._init_spider()
            try:
                self._loop.run_forever()
            except Exception:
                log.error("Unexpected error occurred when run loop", exc_info=True)
                raise
            finally:
                self._loop.close()

    def _init_server(self):
        log.info("Start agent server on '{}'".format(self._agent_listen))
        app = web.Application(logger=log, loop=self._loop)
        app.router.add_route("GET", "/", self.get_proxies)
        host, port = self._agent_listen.split(":")
        port = int(port)
        self._loop.run_until_complete(
            self._loop.create_server(app.make_handler(access_log=None, loop=self._loop), host, port))

    def _get_spider_config(self, config_path):
        if config_path.startswith("http://") or config_path.startswith("https://"):
            config = self._loop.run_until_complete(self._download_spider_config(config_path))
            if config is None:
                raise DownloadingError("Unable to download the configuration of spider: {}".format(config_path))
        else:
            config = load_config_file(config_path)
        return BaseConfig(config)

    async def _download_spider_config(self, url):
        try:
            async with ClientSession(loop=self._loop) as session:
                with async_timeout.timeout(20, loop=self._loop):
                    async with session.request("GET", url) as resp:
                        if resp.status / 100 != 2:
                            log.error("Failed to download spider configuration")
                        else:
                            body = await resp.read()
                            return yaml.load(StringIO(body.decode('utf-8')))
        except Exception:
            log.error("Unexpected error occurred when download spider configuration", exc_info=True)

    def _init_spider(self):
        log.info("Initialize spider")
        self._spider.bind(self._loop, self._add_proxy)

    async def _add_proxy(self, *addr_list):
        t = int(time.time())
        for addr in addr_list:
            try:
                proxy = self._proxy_db.find_proxy(addr)
                if proxy and t - proxy.timestamp <= self._block_time:
                    continue
                proxy = AgentProxyInfo(addr, t)
                self._proxy_db.update_timestamp(proxy)
                await self._wait_queue.put(proxy)
            except Exception:
                log.warning("Unexpected error occurred when add proxy '{0}'".format(addr), exc_info=True)

    def _init_checker(self):
        log.info("Initialize checker, clients={}".format(self._checker_clients))
        f = asyncio.ensure_future(self._find_expired_proxy(), loop=self._loop)
        self._futures.append(f)
        for i in range(self._checker_clients):
            f = asyncio.ensure_future(self._check_proxy(), loop=self._loop)
            self._futures.append(f)

    def _load_checker(self, cls_path):
        checker_cls = load_object(cls_path)
        if hasattr(checker_cls, "from_config"):
            checker = checker_cls.from_config(self.config)
        else:
            checker = checker_cls()
        return checker

    async def _find_expired_proxy(self):
        while True:
            proxy = self._proxy_queue.get_expired_proxy()
            if proxy is not None:
                await self._wait_queue.put(proxy)
            else:
                await asyncio.sleep(5, loop=self._loop)

    async def _check_proxy(self):
        while True:
            proxy = await self._wait_queue.get()
            ok = await self._checker.check_proxy(proxy.addr)
            t = int(time.time())
            proxy.timestamp = t + self._check_interval
            self._proxy_db.update_timestamp(proxy)
            self._proxy_queue.feed_back(proxy, ok)

    async def get_proxies(self, request):
        key = request.match_info.get("key")
        params = request.GET
        count = params.get("count", 0)
        if count:
            count = int(count)
        detail = "detail" in params
        log.info("GET '/{}', count={}, detail={}".format(key, count, detail))
        proxy_list = self._get_proxies(count, detail=detail)
        return web.Response(body=json.dumps(proxy_list).encode("utf-8"),
                            charset="utf-8",
                            content_type="application/json")

    def _get_proxies(self, count, detail=False):
        t = self._proxy_queue.get_proxies(count)
        res = []
        for proxy in t:
            if detail:
                res.append({"addr": proxy.addr, "success": proxy.good, "fail": proxy.bad})
            else:
                res.append(proxy.addr)
        return res


class ProxyQueue:
    def __init__(self, queue_size, *, max_fail_times=2):
        self._max_fail_times = max_fail_times
        backup_size = 10 * queue_size
        self._time_line = PriorityQueue(queue_size + backup_size)
        self._proxy_list = PriorityQueue(queue_size)
        self._queue = PriorityQueue(queue_size)
        self._backup = PriorityQueue(backup_size)

    def get_proxies(self, count):
        res = []
        total = len(self._queue)
        if count <= 0 or total < count:
            count = total
        i = 1
        while i <= count:
            proxy = self._proxy_list.top()
            del self._proxy_list[proxy]
            del self._queue[proxy]
            res.append(proxy)
            i += 1
        for proxy in res:
            self._queue.push(proxy, (-proxy.rate, -proxy.timestamp))
            self._proxy_list.push(proxy, (proxy.rate, proxy.timestamp))
        return res

    def add_proxy(self, proxy):
        if proxy.fail == 0:
            if self._queue.is_full():
                p = self._queue.top()
                if proxy.rate >= p.rate:
                    self._pop_queue(p)
                    self._push_queue(proxy)
                    proxy = p
            else:
                self._push_queue(proxy)
                proxy = None
        if proxy is not None:
            if self._backup.is_full():
                p = self._backup.top()
                if (proxy.rate, -proxy.fail) >= (p.rate, -p.fail):
                    self._pop_backup(p)
                    self._push_backup(proxy)
            else:
                self._push_backup(proxy)

    def feed_back(self, proxy, ok):
        if ok:
            proxy.good += 1
            proxy.fail = 0
            self.add_proxy(proxy)
        else:
            proxy.bad += 1
            proxy.fail += 1
            if proxy.fail <= self._max_fail_times:
                self.add_proxy(proxy)

    def get_expired_proxy(self):
        t = int(time.time())
        if len(self._time_line) > 0:
            p = self._time_line.top()
            if t > p.timestamp:
                if p.status == p.IN_QUEUE:
                    self._pop_queue(p)
                elif p.status == p.IN_BACKUP:
                    self._pop_backup(p)
                return p

    def _push_queue(self, proxy):
        self._time_line.push(proxy, -proxy.timestamp)
        self._queue.push(proxy, (-proxy.rate, -proxy.timestamp))
        self._proxy_list.push(proxy, (proxy.rate, proxy.timestamp))
        proxy.status = proxy.IN_QUEUE

    def _pop_queue(self, proxy):
        del self._time_line[proxy]
        del self._queue[proxy]
        del self._proxy_list[proxy]
        proxy.status = None

    def _push_backup(self, proxy):
        self._time_line.push(proxy, -proxy.timestamp)
        self._backup.push(proxy, (-proxy.rate, proxy.fail))
        proxy.status = proxy.IN_BACKUP

    def _pop_backup(self, proxy):
        del self._time_line[proxy]
        del self._backup[proxy]
        proxy.status = None


class AgentProxyInfo(ProxyInfo):
    IN_QUEUE = 1
    IN_BACKUP = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.status = None
