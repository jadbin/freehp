# coding=utf-8

import re
import asyncio
import logging

import aiohttp
import async_timeout

log = logging.getLogger(__name__)


class ProxySpider:
    def __init__(self, config):
        self._initial_pages = self._pages_from_config(config.get("initial_pages"))
        self._update_pages = self._pages_from_config(config.get("update_pages"))
        self._proxy_finder = ProxyScraperManager.from_config(config)
        self._update_time = config.getint("spider_update_time")
        self._timeout = config.getint("spider_timeout")
        self._sleep_time = config.getint("spider_sleep_time")
        self._headers = config.get("spider_headers", {})
        self._loop = None
        self._callback = None

    @staticmethod
    def _pages_from_config(config):
        def _get_pages(**kw):
            url = kw["url"]
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "http://{}".format(url)
            page = kw.get("page")
            if not page:
                return [url]
            res = []
            start, end = page.split("-")
            start, end = int(start), int(end)
            i = start
            while i <= end:
                res.append(url.replace("[page]", str(i)))
                i += 1
            return res

        if not config:
            return []
        dm = re.compile(r"^https?://([^/]*)")
        top_dm = re.compile(r"([a-zA-Z0-9\-]+\.[a-zA-Z0-9\-]+)$")
        k = {}
        res = []
        for i in config:
            j = _get_pages(**i)
            if j:
                d = top_dm.search(dm.search(j[0]).group(1)).group(1)
                if d in k:
                    k[d] += j
                else:
                    k[d] = j
                    res.append(j)
        return res

    def bind(self, loop, callback):
        self._loop = loop
        self._callback = callback
        for urls in self._initial_pages:
            if not urls:
                continue
            asyncio.ensure_future(self._update_proxy(urls), loop=self._loop)
        for urls in self._update_pages:
            if not urls:
                continue
            asyncio.ensure_future(self._update_proxy_regularly(urls), loop=self._loop)

    async def _update_proxy_regularly(self, urls):
        sleep_time = self._update_time
        while True:
            await asyncio.sleep(sleep_time, loop=self._loop)
            await self._update_proxy(urls)

    async def _update_proxy(self, urls):
        for u in urls:
            retry_cnt = 3
            while retry_cnt > 0:
                retry_cnt -= 1
                try:
                    async with aiohttp.ClientSession(loop=self._loop) as session:
                        with async_timeout.timeout(self._timeout, loop=self._loop):
                            async with session.request("GET", u, headers=self._headers) as resp:
                                url = str(resp.url)
                                body = await resp.read()
                except Exception as e:
                    log.info("{} error occurred when update proxy on url={}: {}".format(type(e), u, e))
                else:
                    retry_cnt = 0
                    addr_list = self._proxy_finder.find_proxy(url, body)
                    log.debug("Find {} proxies on the page '{}'".format(len(addr_list), u))
                    if addr_list:
                        await self._callback(*addr_list)
            await asyncio.sleep(self._sleep_time, loop=self._loop)


class ProxyScraperManager:
    def __init__(self, *scrapers):
        self._finders = [i for i in scrapers]

    @classmethod
    def from_config(cls, config):
        scrapers = []
        scraper_rules = config.get("scraper_rules")
        if not isinstance(scraper_rules, list):
            scraper_rules = [scraper_rules]
        for i in scraper_rules:
            scrapers.append(RegexProxyScraper(i.get("url_match"), i.get("proxy_match")))
        return cls(*scrapers)

    def find_proxy(self, url, body):
        res = []
        for i in self._finders:
            t = i.find_proxy(url, body)
            if t:
                res += t
        return res


class RegexProxyScraper:
    def __init__(self, url_match, proxy_match):
        self._url_match = re.compile(url_match)
        self._proxy_match = re.compile(proxy_match.encode("utf-8"))

    def find_proxy(self, url, body):
        if self._url_match.search(url):
            res = []
            for i in self._proxy_match.findall(body):
                if isinstance(i, tuple):
                    res.append("{}:{}".format(i[0].decode("utf-8"), i[1].decode("utf-8")))
                else:
                    res.append(i.decode("utf-8"))
            return res
