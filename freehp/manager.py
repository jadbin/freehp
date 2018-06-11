# coding=utf-8

import json
import time
import asyncio
import logging
from asyncio.queues import Queue
from collections import deque
import signal
from asyncio import CancelledError

from aiohttp import web

from freehp.spider import ProxySpider
from freehp.utils import load_object

log = logging.getLogger(__name__)


class ProxyManager:
    def __init__(self, config):
        self.config = config
        self.loop = asyncio.new_event_loop()

        self._checker = self._load_checker(config.get("checker_cls"))
        self._block_time = config.getint("block_time")
        self._proxy_queue = ProxyQueue(max_fail_times=config.getint("max_fail_times"))
        self._spider = ProxySpider.from_manager(self)
        self._spider.subscribe(self._add_proxy)

        self._proxy_db = {}

        self._futures = None
        self._wait_queue = Queue(loop=self.loop)
        self._is_running = False

    def start(self):
        if not self._is_running:
            self._is_running = True
            asyncio.set_event_loop(self.loop)
            self._futures = []
            self._init_server()
            self._init_checker()
            self._spider.open()
            self.loop.add_signal_handler(signal.SIGINT,
                                         lambda loop=self.loop: asyncio.ensure_future(self.shutdown(), loop=loop))
            self.loop.add_signal_handler(signal.SIGTERM,
                                         lambda loop=self.loop: asyncio.ensure_future(self.shutdown(), loop=loop))
            try:
                self.loop.run_forever()
            except Exception:
                log.error("Unexpected error occurred when run loop", exc_info=True)
                raise

    async def shutdown(self):
        if not self._is_running:
            return
        self._is_running = False
        log.info("Shutdown now")
        self._spider.close()
        if self._futures:
            for f in self._futures:
                f.cancel()
            self._futures = None
        await asyncio.sleep(0.001, loop=self.loop)
        self.loop.stop()

    def _init_server(self):
        bind = self.config.get('bind')
        log.info("Bind to '%s'", bind)
        app = web.Application(logger=log, loop=self.loop)
        app.router.add_route("GET", "/proxies", self.get_proxies)
        host, port = bind.split(":")
        port = int(port)
        self.loop.run_until_complete(
            self.loop.create_server(app.make_handler(access_log=None, loop=self.loop), host, port))

    async def _add_proxy(self, proxies):
        t = int(time.time())
        for p in proxies:
            try:
                proxy = self._proxy_db.get(p)
                if proxy and t - proxy.timestamp <= self._block_time:
                    continue
                proxy = ProxyInfo(p, t)
                self._proxy_db[p] = proxy
                await self._wait_queue.put(proxy)
            except CancelledError:
                raise
            except Exception:
                log.warning("Unexpected error occurred when add proxy '%s'", p, exc_info=True)

    def _init_checker(self):
        checker_clients = self.config.getint('checker_clients')
        log.info("Initialize checker, clients=%s", checker_clients)
        f = asyncio.ensure_future(self._find_expired_proxy_task(), loop=self.loop)
        self._futures.append(f)
        for i in range(checker_clients):
            f = asyncio.ensure_future(self._check_proxy_task(), loop=self.loop)
            self._futures.append(f)
        f = asyncio.ensure_future(self._remove_blocked_proxy_task(), loop=self.loop)
        self._futures.append(f)

    def _load_checker(self, cls_path):
        checker_cls = load_object(cls_path)
        if hasattr(checker_cls, "from_manager"):
            checker = checker_cls.from_manager(self)
        else:
            checker = checker_cls()
        return checker

    async def _find_expired_proxy_task(self):
        while True:
            proxy = self._proxy_queue.get_expired_proxy()
            if proxy is not None:
                await self._wait_queue.put(proxy)
            else:
                await asyncio.sleep(5, loop=self.loop)

    async def _check_proxy_task(self):
        check_interval = self.config.get('check_interval')
        while True:
            proxy = await self._wait_queue.get()
            ok = await self._checker.check_proxy(proxy.addr)
            t = int(time.time())
            proxy.timestamp = t + check_interval
            self._proxy_queue.feed_back(proxy, ok)

    async def _remove_blocked_proxy_task(self):
        while True:
            await asyncio.sleep(self._block_time, loop=self.loop)
            t = time.time()
            for i in list(self._proxy_db.keys()):
                if t - self._proxy_db[i].timestamp > self._block_time:
                    del self._proxy_db[i]

    async def get_proxies(self, request):
        params = request.rel_url.query
        count = params.get("count", 0)
        if count:
            count = int(count)
        detail = "detail" in params
        order = params.get('order', 'rate')
        log.info("GET '/', count=%s, detail=%s, order=%s", count, detail, order)
        proxy_list = self._get_proxies(count, detail=detail, order=order)
        return web.Response(body=json.dumps(proxy_list).encode("utf-8"),
                            charset="utf-8",
                            content_type="application/json")

    def _get_proxies(self, count, detail=False, order='rate'):
        t = self._proxy_queue.get_proxies()
        if count <= 0 or len(t) < count:
            count = len(t)
        if order == 'rate':
            t.sort(key=lambda k: k.rate, reverse=True)
        elif order == 'time':
            t.sort(key=lambda k: k.timestamp, reverse=True)
        t = t[:count]

        res = []
        for p in t:
            if detail:
                res.append({"addr": p.addr, "success": p.good, "fail": p.bad, "timestamp": p.timestamp})
            else:
                res.append(p.addr)
        return res


class ProxyQueue:
    def __init__(self, max_fail_times=2):
        self._max_fail_times = max_fail_times
        self._queue = deque()
        self._backup = deque()

    def get_proxies(self):
        res = [i for i in self._queue]
        return res

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
