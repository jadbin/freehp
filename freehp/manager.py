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
from freehp import defaultconfig

log = logging.getLogger(__name__)


class ProxyManager:
    def __init__(self, config):
        self.config = config
        self.loop = asyncio.new_event_loop()

        self._checker = self._load_checker(config.get("checker_cls"))
        self._check_interval = self.config.get('check_interval')
        self._block_time = config.getint("block_time")
        self._proxy_queue = ProxyQueue(max_fail_times=config.getint("max_fail_times"),
                                       min_anonymity=config.getint('min_anonymity'))
        self._spider = ProxySpider.from_manager(self)
        self._spider.subscribe(self._add_proxy)

        self._proxy_db = {}

        self._wait_queue = Queue(loop=self.loop)
        self._label_queue = Queue(loop=self.loop)
        self._futures = None
        self._futures_done = None
        self._check_futures = None
        self._check_futures_done = None
        self._label_futures = None
        self._label_futures_done = None
        self._is_running = False

    def start(self):
        if not self._is_running:
            self._is_running = True
            asyncio.set_event_loop(self.loop)
            self._futures = []
            self._futures_done = set()
            self._check_futures = []
            self._check_futures_done = set()
            self._label_futures = []
            self._label_futures_done = set()
            self._init_server()
            self._init_checker()
            self._spider.open()
            f = asyncio.ensure_future(self._supervisor(), loop=self.loop)
            self._futures.append(f)
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
            self._futures_done = None
        if self._check_futures:
            for f in self._check_futures:
                f.cancel()
            self._check_futures = None
            self._check_futures_done = None
        if self._label_futures:
            for f in self._label_futures:
                f.cancel()
            self._label_futures = None
            self._label_futures_done = None
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
                log.warning("Failed to add proxy '%s'", p, exc_info=True)

    def _init_checker(self):
        checker_clients = self.config.getint('checker_clients')
        log.info("Initialize checker, clients=%s", checker_clients)
        f = asyncio.ensure_future(self._find_expired_proxy_task(), loop=self.loop)
        self._futures.append(f)
        for i in range(checker_clients):
            f = asyncio.ensure_future(self._check_proxy_task(), loop=self.loop)
            self._check_futures.append(f)
        for i in range(checker_clients):
            f = asyncio.ensure_future(self._label_proxy_task(), loop=self.loop)
            self._label_futures.append(f)
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
        while True:
            proxy = await self._wait_queue.get()
            res = await self._checker.check_proxy(proxy.addr)
            t = int(time.time())
            proxy.timestamp = t + self._check_interval
            self._proxy_queue.feed_back(proxy, res)
            if res:
                await self._label_queue.put(proxy)

    async def _remove_blocked_proxy_task(self):
        while True:
            await asyncio.sleep(self._block_time, loop=self.loop)
            t = time.time()
            for i in list(self._proxy_db.keys()):
                if t - self._proxy_db[i].timestamp > self._block_time:
                    del self._proxy_db[i]

    async def _label_proxy_task(self):
        while True:
            proxy = await self._label_queue.get()
            t = time.time()
            if t > proxy.timestamp:
                continue
            https = await self._checker.check_proxy(proxy.addr, https=True)
            if https and https[1] > 0:
                proxy.https = True
            else:
                proxy.https = False
            post = await self._checker.verify_post(proxy.addr)
            proxy.post = post

    async def _supervisor(self):
        def supervise(name, futures, futures_done):
            for i in range(len(futures)):
                f = futures[i]
                if f.done():
                    if i not in futures_done:
                        futures.add(i)
                        reason = "cancelled" if f.cancelled() else str(f.exception())
                        log.error("%s[%s] is shut down: %s", name, i, reason)
                        self._check_futures[i] = None

        while True:
            await asyncio.sleep(600, loop=self.loop)
            supervise('Check future', self._check_futures, self._check_futures_done)
            supervise('Label future', self._label_futures, self._label_futures_done)
            supervise('Future', self._futures, self._futures_done)

    async def get_proxies(self, request):
        params = request.rel_url.query
        count = params.get("count", 0)
        if count:
            count = int(count)
        kwargs = {}
        if 'order' in params:
            kwargs['order'] = params.get('order')
        if 'detail' in params:
            kwargs['detail'] = True
        if 'https' in params:
            kwargs['https'] = True
        if 'post' in params:
            kwargs['post'] = True
        min_anonymity = params.get('min_anonymity')
        if min_anonymity is not None:
            kwargs['min_anonymity'] = int(min_anonymity)
        log.info('GET /proxies %s', kwargs)
        proxy_list = self._get_proxies(count, **kwargs)
        return web.Response(body=json.dumps(proxy_list).encode("utf-8"),
                            charset="utf-8",
                            content_type="application/json")

    def _get_proxies(self, count, detail=False, order='rate', https=False, post=False, min_anonymity=0):
        t = self._proxy_queue.get_proxies()
        if min_anonymity > 0:
            t = [i for i in t if i.anonymity >= min_anonymity]
        if https:
            t = [i for i in t if i.https]
        if post:
            t = [i for i in t if i.post]
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
                res.append({"address": p.addr, "success": p.good, "fail": p.bad,
                            'timestamp': p.timestamp - self._check_interval,
                            'anonymity': p.anonymity, 'https': p.https, 'post': p.post})
            else:
                res.append(p.addr)
        return res


class ProxyQueue:
    def __init__(self, max_fail_times=defaultconfig.max_fail_times, min_anonymity=defaultconfig.min_anonymity):
        self._max_fail_times = max_fail_times
        self._min_anonymity = min_anonymity
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

    def feed_back(self, proxy, res):
        ok = False
        if res:
            anonymity = res[1]
            proxy.anonymity = anonymity
            if anonymity >= self._min_anonymity:
                ok = True
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
    def __init__(self, addr, timestamp, *, good=0, bad=0, fail=1, anonymity=0, https=False, post=False):
        self.addr = addr
        self.timestamp = timestamp
        self.good = good
        self.bad = bad
        self.fail = fail
        self.anonymity = anonymity
        self.https = https
        self.post = post

    @property
    def rate(self):
        return self.good / (self.good + self.bad + 1.0)
