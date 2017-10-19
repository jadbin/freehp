# coding=utf-8

import re
import json
import random
import asyncio
import logging

import aiohttp
import async_timeout

log = logging.getLogger(__name__)


class HttpbinChecker:
    def __init__(self, *, loop=None, timeout=10):
        self._loop = loop or asyncio.get_event_loop()
        self._timeout = int(timeout)

    @classmethod
    def from_config(cls, config):
        c = config.get("httpbin_checker") or {}
        return cls(loop=config.get("loop"), **c)

    async def check_proxy(self, addr):
        if not addr.startswith("http://"):
            proxy = "http://{0}".format(addr)
        else:
            proxy = addr
        try:
            async with aiohttp.ClientSession(loop=self._loop) as session:
                with async_timeout.timeout(self._timeout, loop=self._loop):
                    seed = str(random.randint(0, 99999999))
                    url = "http://httpbin.org/get?seed={}".format(seed)
                    async with session.request("GET", url, proxy=proxy) as resp:
                        body = await resp.read()
                        data = json.loads(body.decode('utf-8'))
                        if "args" not in data:
                            return False
                        args = data["args"]
                        if "seed" not in args or args["seed"] != seed:
                            return False
        except Exception:
            return False
        log.debug("Proxy {} is OK".format(addr))
        return True


class ResponseMatchChecker:
    def __init__(self, url, *, http_status=200, url_pattern=None, body_pattern=None, body_encoding='utf-8', timeout=10,
                 loop=None):
        self._url = url
        self._http_status = http_status
        if url_pattern is None:
            self._url_match = None
        else:
            self._url_match = re.compile(url_pattern)
        if body_pattern is None:
            self._body_match = None
        else:
            self._body_match = re.compile(body_pattern.encode(body_encoding))
        self._timeout = int(timeout)
        self._loop = loop or asyncio.get_event_loop()

    @classmethod
    def from_config(cls, config):
        c = config.get("response_match_checker") or {}
        return cls(loop=config.get("loop"), **c)

    async def check_proxy(self, addr):
        if not addr.startswith("http://"):
            proxy = "http://{0}".format(addr)
        else:
            proxy = addr
        try:
            async with aiohttp.ClientSession(loop=self._loop) as session:
                with async_timeout.timeout(self._timeout, loop=self._loop):
                    async with session.request("GET", self._url, proxy=proxy) as resp:
                        url = str(resp.url)
                        if not self.match_status(self._http_status, resp.status):
                            return False
                        if self._url_match and not self._url_match.search(url):
                            return False
                        body = await resp.read()
                        if self._body_match and not self._body_match.search(body):
                            return False
        except Exception:
            return False
        return True

    @staticmethod
    def match_status(pattern, status):
        if isinstance(pattern, int):
            return pattern == status
        verse = False
        if pattern.startswith("!") or pattern.startswith("~"):
            verse = True
            pattern = pattern[1:]
        s = str(status)
        n = len(s)
        match = True
        if len(pattern) != n:
            match = False
        else:
            i = 0
            while i < n:
                if pattern[i] != "x" and pattern[i] != "X" and pattern[i] != s[i]:
                    match = False
                    break
                i += 1
        if verse:
            match = not match
        return match
