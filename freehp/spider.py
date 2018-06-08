# coding=utf-8

import time
import asyncio
import logging

import aiohttp
import async_timeout

from freehp.extractor import extract_proxies

log = logging.getLogger(__name__)


class ProxySpider:
    def __init__(self, config, loop=None):
        self._proxy_pages = config.get('proxy_pages', {})
        log.debug('Details of proxy pages:')
        for i in self._proxy_pages:
            log.debug('# {}: {}', i, len(self._proxy_pages[i]))
        self._scrap_interval = config.getint("scrap_interval")
        self._timeout = config.getint("spider_timeout")
        self._sleep_time = config.getint("spider_sleep_time")
        self._headers = config.get("spider_headers", {})
        self._loop = loop or asyncio.get_event_loop()

        self._futures = []
        self._receivers = []

    @classmethod
    def from_manager(cls, manager):
        return cls(manager.config, loop=manager.loop)

    def subscribe(self, receiver):
        self._receivers.append(receiver)

    def open(self):
        for p in self._proxy_pages:
            f = asyncio.ensure_future(self._update_proxy_task(self._proxy_pages[p]), loop=self._loop)
            self._futures.append(f)

    def close(self):
        for f in self._futures:
            f.cancel()

    async def _update_proxy_task(self, urls):
        while True:
            t = await self._update_proxy(urls)
            t = self._scrap_interval - t
            if t < self._sleep_time:
                self._sleep_time = t
            await asyncio.sleep(t, loop=self._loop)

    async def _update_proxy(self, urls):
        start_time = time.time()
        for url in urls:
            retry_cnt = 3
            while retry_cnt > 0:
                retry_cnt -= 1
                try:
                    async with aiohttp.ClientSession(loop=self._loop) as session:
                        with async_timeout.timeout(self._timeout, loop=self._loop):
                            async with session.request("GET", url, headers=self._headers) as resp:
                                body = await resp.read().decode('utf-8', errors='ignore')
                except Exception as e:
                    log.info("{} error occurred when scrap proxy on url={}: {}".format(type(e), url, e))
                else:
                    retry_cnt = 0
                    proxies = extract_proxies(body)
                    log.debug("Find {} proxies on the page '{}'".format(len(proxies), url))
                    if proxies:
                        for r in self._receivers:
                            await r(proxies)
            await asyncio.sleep(self._sleep_time, loop=self._loop)
        return time.time() - start_time
