# coding=utf-8

import json
import random
import asyncio
import logging
from asyncio import CancelledError

import aiohttp
import async_timeout

log = logging.getLogger(__name__)


class HttpbinChecker:
    def __init__(self, *, loop=None, timeout=10):
        self._loop = loop or asyncio.get_event_loop()
        self._timeout = int(timeout)

    @classmethod
    def from_manager(cls, manager):
        c = manager.config.get("httpbin_checker") or {}
        return cls(loop=manager.loop, **c)

    async def check_proxy(self, addr):
        anonymity = 0
        if not addr.startswith("http://"):
            proxy = "http://{0}".format(addr)
        else:
            proxy = addr
        try:
            async with aiohttp.ClientSession(loop=self._loop) as session:
                with async_timeout.timeout(self._timeout, loop=self._loop):
                    seed = str(random.randint(0, 99999999))
                    url = "http://httpbin.org/get?seed={}".format(seed)
                    async with session.request("GET", url, proxy=proxy, headers={'Connection': 'keep-alive'}) as resp:
                        body = await resp.read()
                        data = json.loads(body.decode('utf-8'))
                        if data['args'].get('seed') != seed:
                            return False
                        # remove transparent proxy
                        if ',' in data['origin']:
                            anonymity = 1
                        if 'Via' not in data['headers'] and 'Proxy-Connection' not in data['headers']:
                            anonymity = 2

        except CancelledError:
            raise
        except Exception:
            return False
        log.debug("Proxy %s is OK", addr)
        return True, anonymity
