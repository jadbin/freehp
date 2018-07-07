# coding=utf-8

import time
import asyncio
import logging
from asyncio import CancelledError

import aiohttp
import async_timeout

from freehp.extractor import extract_proxies

log = logging.getLogger(__name__)


class ProxySpider:
    def __init__(self, config, loop=None):
        self._proxy_pages = config.get('proxy_pages', {})
        log.debug('Details of proxy pages: %s', [i for i in self._proxy_pages])
        self._scrap_interval = config.getint("scrap_interval")
        self._timeout = config.getint("spider_timeout")
        self._sleep_time = config.getint("spider_sleep_time")
        self._headers = config.get("spider_headers", {})
        self._loop = loop or asyncio.get_event_loop()

        self.futures = None
        self._receivers = []

    @classmethod
    def from_manager(cls, manager):
        return cls(manager.config, loop=manager.loop)

    def subscribe(self, receiver):
        self._receivers.append(receiver)

    def open(self):
        self.futures = []
        for p in self._proxy_pages:
            f = asyncio.ensure_future(self._update_proxy_task(self._proxy_pages[p]), loop=self._loop)
            self.futures.append(f)

    def close(self):
        if self.futures:
            for f in self.futures:
                f.cancel()
            self.futures = None

    async def _update_proxy_task(self, urls):
        if not isinstance(urls, list):
            urls = [urls]
        while True:
            t = await self._update_proxy(urls)
            t = self._scrap_interval - t
            if t > self._sleep_time:
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
                                body = await resp.read()
                                body = body.decode('utf-8', errors='ignore')
                except CancelledError:
                    raise
                except Exception as e:
                    log.info("Failed to scrap proxy on '%s': %s", url, e)
                else:
                    retry_cnt = 0
                    proxies = extract_proxies(body)
                    log.debug("Find %s proxies on the page '%s'", len(proxies), url)
                    if proxies:
                        for r in self._receivers:
                            await r(proxies)
                await asyncio.sleep(self._sleep_time, loop=self._loop)
        return time.time() - start_time
