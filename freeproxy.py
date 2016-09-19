# coding=utf-8

import os
import re
import sys
import json
import yaml
import asyncio
import logging
import threading
import logging.config

import aiohttp

log = logging.getLogger("freeproxy")


class ProxySpider:
    def __init__(self, initial_pages, update_pages, *, update_time=300, timeout=30, sleep_time=10, headers=None, local_config=None):
        self._initial_pages = initial_pages
        self._update_pages = update_pages
        if local_config is None:
            local_config = {}
        self._proxy_finder = _ProxyFinderManager.from_config(local_config)
        self._proxy_sender = _ProxySenderManager.from_config(local_config)
        self._update_time = update_time
        self._timeout = timeout
        self._sleep_time = sleep_time
        if not headers:
            headers = {}
        self._headers = headers
        self._loop = None

    @classmethod
    def from_config(cls, config):
        initial_pages = cls._pages_from_config(config.get("initial_pages"))
        update_pages = cls._pages_from_config(config.get("update_pages"))
        kw = {}
        if "proxy_update_time" in config:
            kw["update_time"] = config["proxy_update_time"]
        if "spider_timeout" in config:
            kw["timeout"] = config["spider_timeout"]
        if "spider_sleep_time" in config:
            kw["sleep_time"] = config["spider_sleep_time"]
        if "spider_headers" in config:
            kw["headers"] = config["spider_headers"]
        return cls(initial_pages, update_pages, **kw, local_config=config)

    @classmethod
    def _pages_from_config(cls, config):
        def _get_pages(**kw):
            url = kw["url"]
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "http://{0}".format(url)
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
        k = {}
        res = []
        for i in config:
            j = _get_pages(**i)
            if j:
                d = dm.findall(j[0])[0]
                if d in k:
                    k[d] += j
                else:
                    k[d] = j
                    res.append(j)
        return res

    def start(self):
        def _start():
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_forever()
            except Exception:
                log.error("Unexpected error occurred when run loop", exc_info=True)
                raise
            finally:
                self._loop.close()
                self._loop = None

        self._loop = asyncio.new_event_loop()
        for urls in self._initial_pages:
            if not urls:
                continue
            asyncio.ensure_future(self._update_proxy(urls), loop=self._loop)
        for urls in self._update_pages:
            if not urls:
                continue
            asyncio.ensure_future(self._update_proxy_regularly(urls), loop=self._loop)
        t = threading.Thread(target=_start)
        t.start()

    def stop(self):
        if self._loop is not None:
            self._loop.call_soon_threadsafe(lambda: self._loop.stop())

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
                    with aiohttp.ClientSession(loop=self._loop) as session:
                        with aiohttp.Timeout(self._timeout, loop=self._loop):
                            async with session.request("GET", u, headers=self._headers) as resp:
                                url = resp.url
                                body = await resp.read()
                except Exception as e:
                    log.warning("{0} error occurred when update proxy on url={1}: {2}".format(type(e), u, e))
                else:
                    retry_cnt = 0
                    addr_list = self._proxy_finder.find_proxy(url, body)
                    log.debug("Find {0} proxies on the page '{1}'".format(len(addr_list), u))
                    if addr_list:
                        self._proxy_sender.send_proxy(*addr_list)
            await asyncio.sleep(self._sleep_time, loop=self._loop)


class _ProxyFinderManager:
    def __init__(self, *finders):
        self._finders = [i for i in finders]

    @classmethod
    def from_config(cls, config):
        finders = []
        proxy_rules = config.get("proxy_rules")
        if not isinstance(proxy_rules, list):
            proxy_rules = [proxy_rules]
        for i in proxy_rules:
            finders.append(_RegexProxyFinder(i.get("url_match"), i.get("proxy_match")))
        return cls(*finders)

    def find_proxy(self, url, body):
        res = []
        for i in self._finders:
            t = i.find_proxy(url, body)
            if t:
                res += t
        return res


class _RegexProxyFinder:
    def __init__(self, url_match, proxy_match):
        self._url_match = re.compile(url_match)
        self._proxy_match = re.compile(proxy_match.encode("utf-8"))

    def find_proxy(self, url, body):
        if self._url_match.search(url):
            res = []
            for i in self._proxy_match.findall(body):
                if isinstance(i, tuple):
                    res.append("{0}:{1}".format(i[0].decode("utf-8"), i[1].decode("utf-8")))
                else:
                    res.append(i.decode("utf-8"))
            return res


class _ProxySenderManager:
    def __init__(self, *agent_addr):
        self._agent_addr = [i for i in agent_addr]

    @classmethod
    def from_config(cls, config):
        agent_addr = config.get("agent_addr")
        if not isinstance(agent_addr, list):
            agent_addr = [agent_addr]
        return cls(*agent_addr)

    def send_proxy(self, *proxy):
        async def _send():
            for addr in self._agent_addr:
                if not addr.startswith("http://"):
                    addr = "http://{0}".format(addr)
                try:
                    with aiohttp.ClientSession() as session:
                        async with session.request("POST", addr, data=body) as resp:
                            if resp.status != 200:
                                log.debug("Unsuccessfully post proxy to '{0}'".format(addr))
                except Exception:
                    log.debug("Unexpected error occurred when post proxy to '{0}'".format(addr), exc_info=True)

        proxy_list = [i for i in proxy]
        body = json.dumps(proxy_list).encode("utf-8")
        asyncio.ensure_future(_send())


class SystemBoot:
    def start(self, argv):
        params = self._get_params(argv)
        config_file = os.path.abspath(params.get("config"))
        config = self._load_config(config_file)
        logging.config.dictConfig(self._load_config(params.get("logger")))
        spider = ProxySpider.from_config(config)
        spider.start()

    @staticmethod
    def _load_config(file):
        with open(file, "r", encoding="utf-8") as f:
            d = yaml.load(f)
            return d

    @staticmethod
    def _get_params(argv):
        params = {}
        key, value = None, None
        for i in argv:
            if i.startswith("-"):
                if key:
                    params.setdefault(key, value)
                key, value = i.lstrip("-"), None
            else:
                if value is None:
                    value = i
                else:
                    if not isinstance(value, list):
                        value = [value]
                    value.append(i)
        if key:
            params.setdefault(key, value)
        return params


def main(argv=None):
    if argv is None:
        argv = sys.argv
    argv = argv[1:]
    cmd = argv[0]
    argv = argv[1:]
    if cmd == "start":
        boot = SystemBoot()
        boot.start(argv)
    else:
        raise ValueError(cmd)


if __name__ == "__main__":
    main()
