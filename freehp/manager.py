# coding=utf-8

import json
import time
import asyncio
import logging
from asyncio.queues import Queue
from io import StringIO
from collections import deque

import yaml
from aiohttp import web, ClientSession
import async_timeout

from .spider import ProxySpider
from .utils import load_object, load_config_file
from .errors import NetworkError
from .config import BaseConfig

log = logging.getLogger(__name__)


class ProxyManager:
    def __init__(self, config):
        self.config = config
        self.loop = asyncio.new_event_loop()

        self._checker = self._load_checker(config.get("checker_cls"))
        self._checker_clients = config.getint("checker_clients")

        self._check_interval = config.getint("check_interval")
        self._block_time = config.getint("block_time")
        self._proxy_queue = ProxyQueue(max_fail_times=config.getint("max_fail_times"))

        self._spider = ProxySpider(self._get_spider_config(config.get('spider_config')),
                                   loop=self.loop)

        self._listen = config.get("listen")

        self._futures = []
        self._wait_queue = Queue(loop=self.loop)
        self._is_running = False

    def start(self):
        if not self._is_running:
            self._is_running = True
            asyncio.set_event_loop(self.loop)
            self._init_server()
            self._init_checker()
            self._init_spider()
            try:
                self.loop.run_forever()
            except Exception:
                log.error("Unexpected error occurred when run loop", exc_info=True)
                raise
            finally:
                self.loop.close()

    async def shutdown(self):
        pass

    def _init_server(self):
        log.info("Start manager on '{}'".format(self._listen))
        app = web.Application(logger=log, loop=self.loop)
        app.router.add_route("GET", "/", self.get_proxies)
        host, port = self._listen.split(":")
        port = int(port)
        self.loop.run_until_complete(
            self.loop.create_server(app.make_handler(access_log=None, loop=self.loop), host, port))

    def _get_spider_config(self, config_path):
        if config_path.startswith("http://") or config_path.startswith("https://"):
            config = self.loop.run_until_complete(self._download_spider_config(config_path))
            if config is None:
                raise NetworkError("Unable to get the configuration of spider: {}".format(config_path))
        else:
            config = load_config_file(config_path)
        return BaseConfig(config)

    async def _download_spider_config(self, url):
        try:
            async with ClientSession(loop=self.loop) as session:
                with async_timeout.timeout(20, loop=self.loop):
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
        if hasattr(checker_cls, "from_agent"):
            checker = checker_cls.from_agent(self)
        else:
            checker = checker_cls()
        return checker

    async def _find_expired_proxy(self):
        while True:
            proxy = self._proxy_queue.get_expired_proxy()
            if proxy is not None:
                await self._wait_queue.put(proxy)
            else:
                await asyncio.sleep(5, loop=self.loop)

    async def _check_proxy(self):
        while True:
            proxy = await self._wait_queue.get()
            ok = await self._checker.check_proxy(proxy.addr)
            t = int(time.time())
            proxy.timestamp = t + self._check_interval
            self._proxy_db.update_timestamp(proxy)
            self._proxy_queue.feed_back(proxy, ok)

    async def get_proxies(self, request):
        params = request.GET
        count = params.get("count", 0)
        if count:
            count = int(count)
        detail = "detail" in params
        log.info("GET '/', count={}, detail={}".format(count, detail))
        proxy_list = self._get_proxies(count, detail=detail)
        return web.Response(body=json.dumps(proxy_list).encode("utf-8"),
                            charset="utf-8",
                            content_type="application/json")

    def _get_proxies(self, count, detail=False):
        t = self._proxy_queue.get_proxies(count)
        res = []
        for p in t:
            if detail:
                res.append({"addr": p.addr, "success": p.good, "fail": p.bad})
            else:
                res.append(p.addr)
        return res


class ProxyQueue:
    def __init__(self, max_fail_times=2):
        self._max_fail_times = max_fail_times
        self._queue = deque()
        self._backup = deque()

    def get_proxies(self, count):
        total = len(self._queue)
        if count <= 0 or total < count:
            count = total
        res = [i for i in self._queue]
        res.sort(key=lambda k: k.rate, reverse=True)
        return res[:count]

    def add_proxy(self, proxy):
        if proxy.fail == 0:
            self._queue.append(proxy)
        else:
            self._backup.append(proxy)

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
        p = None
        if len(self._queue) > 0 and len(self._backup) > 0:
            if t > self._queue[0].timestamp and t > self._backup[0].timestamp:
                if self._queue[0].timestamp > self._backup[0].timestamp:
                    p = self._backup.popleft()
                else:
                    p = self._queue.popleft()
            elif t > self._queue[0].timestamp:
                p = self._queue.popleft()
            elif t > self._backup[0].timestamp:
                p = self._backup.popleft()
        elif len(self._queue) > 0:
            if t > self._queue[0].timestamp:
                p = self._queue.popleft()
        elif len(self._backup) > 0:
            if t > self._backup[0].timestamp:
                p = self._backup.popleft()
        return p


class ProxyInfo:
    def __init__(self, addr, timestamp, *, good=0, bad=0, fail=1):
        self.addr = addr
        self.timestamp = timestamp
        self.good = good
        self.bad = bad
        self.fail = fail

    @property
    def rate(self):
        return self.good / (self.good + self.bad + 1.0)
