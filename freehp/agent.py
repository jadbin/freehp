# coding=utf-8

import os
import re
import json
import time
import asyncio
import logging

import aiohttp
from aiohttp import web
import async_timeout

from freehp.ds import PriorityQueue
from freehp.data import ProxyInfo, ProxyDb

log = logging.getLogger(__name__)


class Agent:
    def __init__(self, config):
        self._agent_listen = config.get("agent_listen")
        self._loop = asyncio.new_event_loop()
        self._managers = {}
        self._proxy_db = ProxyDb(os.path.join(config.get("data_dir"), "proxydb"))
        self._semaphore = asyncio.Semaphore(config.get("proxy_checker_clients"), loop=self._loop)
        proxy_checkers_config = config.get("proxy_checkers")
        if proxy_checkers_config:
            for k, v in proxy_checkers_config.items():
                checker = ProxyChecker(**v, loop=self._loop, semaphore=self._semaphore)
                self._managers[k] = ProxyManager(k, checker, self._proxy_db, config)
        self._is_running = False

    def start(self):
        if not self._is_running:
            self._is_running = True
            asyncio.set_event_loop(self._loop)
            self._add_server()
            self._add_managers()
            try:
                self._loop.run_forever()
            except Exception:
                log.error("Unexpected error occurred when run loop", exc_info=True)
                raise
            finally:
                self._loop.close()

    def _add_server(self):
        log.info("Start agent server on '{}'".format(self._agent_listen))
        app = web.Application(logger=log, loop=self._loop)
        app.router.add_route("GET", "/proxy/{key}", self.get_proxy_list)
        host, port = self._agent_listen.split(":")
        port = int(port)
        self._loop.run_until_complete(self._loop.create_server(app.make_handler(access_log=None), host, port))

    def _add_managers(self):
        for manager in self._managers.values():
            asyncio.ensure_future(manager.check_proxy_regularly(), loop=self._loop)

    async def get_proxy_list(self, request):
        key = request.match_info.get("key")
        params = request.GET
        count = params.get("count", 0)
        if count:
            count = int(count)
        detail = "detail" in params
        log.info("GET '/{}', count={}, detail={}".format(key, count, detail))
        if key in self._managers:
            proxy_list = self._managers[key].get_proxy_list(count, detail=detail)
            return web.Response(body=json.dumps(proxy_list).encode("utf-8"),
                                charset="utf-8",
                                content_type="application/json")

        return web.Response(body=b"404: Not Found",
                            status=404,
                            charset="utf-8",
                            content_type="text/plain")


class ProxyManager:
    def __init__(self, name, checker, proxy_db, config):
        self._name = name
        self._checker = checker
        self._proxy_db = proxy_db
        self._check_interval = config.get("proxy_check_interval")
        self._block_time = config.get("proxy_block_time")
        self._fail_times = config.get("proxy_fail_times")
        queue_size = config.get("proxy_queue_size")
        backup_size = config.get("proxy_backup_size")
        self._time_line = PriorityQueue(queue_size + backup_size)
        self._proxy_list = PriorityQueue(queue_size)
        self._queue = PriorityQueue(queue_size)
        self._backup = PriorityQueue(backup_size)

    def get_proxy_list(self, count, *, detail=False):
        res = []
        total = len(self._queue)
        if not count or total < count:
            count = total
        t = []
        i = 1
        while i <= count:
            proxy = self._proxy_list.top()
            del self._proxy_list[proxy.queue_index]
            del self._queue[proxy.queue_index]
            t.append(proxy)
            if detail:
                res.append({"addr": proxy.addr, "success": proxy.good, "fail": proxy.bad})
            else:
                res.append(proxy.addr)
            i += 1
        for proxy in t:
            i = self._queue.push(proxy, (-proxy.rate, -proxy.timestamp))
            self._proxy_list.push(proxy, (proxy.rate, proxy.timestamp))
            proxy.queue_index = i
        return res

    def add_proxy(self, *addr_list):
        t = int(time.time())
        for addr in addr_list:
            try:
                proxy = self._proxy_db.find_proxy(self._name, addr)
                if proxy and t - proxy.timestamp <= self._block_time:
                    continue
                proxy = ProxyInfo(addr, t)
                self._proxy_db.update_timestamp(self._name, proxy)
                if self._backup.is_full():
                    p = self._backup.top()
                    if (proxy.rate, -proxy.fail) >= (p.rate, -p.fail):
                        self._pop_backup(p)
                        self._push_backup(proxy)
                else:
                    self._push_backup(proxy)
            except Exception:
                log.warning("Unexpected error occurred when add proxy '{0}'".format(addr), exc_info=True)

    async def check_proxy_regularly(self, loop):
        while True:
            proxy = None
            t = int(time.time())
            if len(self._time_line) > 0:
                p = self._time_line.top()
                if t > p.timestamp:
                    if p.status == p.IN_QUEUE:
                        self._pop_queue(p)
                    elif p.status == p.IN_BACKUP:
                        self._pop_backup(p)
                    proxy = p
            if proxy is not None:
                await self._checker.check_proxy(proxy.addr, lambda ok, proxy=proxy: self._handle_result(proxy, ok))
            else:
                await asyncio.sleep(5, loop=loop)

    def _handle_result(self, proxy, ok):
        t = int(time.time())
        proxy.timestamp = t + self._check_interval
        self._proxy_db.update_timestamp(self._name, proxy)
        if ok:
            proxy.good += 1
            proxy.fail = 0
            if self._queue.is_full():
                p = self._queue.top()
                if proxy.rate > p.rate:
                    self._pop_queue(p)
                    self._push_queue(proxy)
                    proxy = p
            else:
                self._push_queue(proxy)
                proxy = None
        else:
            proxy.bad += 1
            proxy.fail += 1
            if proxy.fail > self._fail_times:
                proxy = None
        if proxy is not None:
            if self._backup.is_full():
                p = self._backup.top()
                if (proxy.rate, -proxy.fail) > (p.rate, -p.fail):
                    self._pop_backup(p)
                    self._push_backup(proxy)
            else:
                self._push_backup(proxy)

    def _push_queue(self, proxy):
        proxy.line_index = self._time_line.push(proxy, -proxy.timestamp)
        proxy.queue_index = self._queue.push(proxy, (-proxy.rate, -proxy.timestamp))
        self._proxy_list.push(proxy, (proxy.rate, proxy.timestamp))
        proxy.status = proxy.IN_QUEUE

    def _pop_queue(self, proxy):
        del self._time_line[proxy.line_index]
        del self._queue[proxy.queue_index]
        del self._proxy_list[proxy.queue_index]
        proxy.status = None

    def _push_backup(self, proxy):
        proxy.line_index = self._time_line.push(proxy, -proxy.timestamp)
        proxy.queue_index = self._backup.push(proxy, (-proxy.rate, proxy.fail))
        proxy.status = proxy.IN_BACKUP

    def _pop_backup(self, proxy):
        del self._time_line[proxy.line_index]
        del self._backup[proxy.queue_index]
        proxy.status = None


class ProxyChecker:
    def __init__(self, url, response, timeout=10, loop=None, semaphore=None, **kwargs):
        self._url = url
        self._http_status = 200
        self._url_match = None
        self._body_match = None
        if response:
            if "http_status" in response:
                self._http_status = response["http_status"]
            if "url_match" in response:
                self._url_match = re.compile(response["url_match"])
            if "body_match" in response:
                if "encoding" in response:
                    encoding = response["encoding"]
                else:
                    encoding = "utf-8"
                self._body_match = re.compile(response["body_match"].encode(encoding))
        self._timeout = timeout
        self._loop = loop or asyncio.get_event_loop()
        self._semaphore = semaphore

    async def check_proxy(self, addr, callback):
        async def _check():
            if not addr.startswith("http://"):
                proxy = "http://{0}".format(addr)
            else:
                proxy = addr
            try:
                with aiohttp.ClientSession(loop=self._loop) as session:
                    with async_timeout.timeout(self._timeout, loop=self._loop):
                        async with session.request("GET", self._url, proxy=proxy) as resp:
                            if resp.status != self._http_status:
                                return False
                            if self._url_match and not self._url_match.search(resp.url):
                                return False
                            body = await resp.read()
                            if self._body_match and not self._body_match.search(body):
                                return False
            except Exception:
                return False
            return True

        async def _task():
            ok = await _check()
            try:
                callback(ok)
            except Exception:
                log.warning("Unexpected error occurred in callback", exc_info=True)
            finally:
                if self._semaphore:
                    self._semaphore.release()

        if self._semaphore:
            await self._semaphore.acquire()
        asyncio.ensure_future(_task(), loop=self._loop)
