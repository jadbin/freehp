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
    HTTP_CHECK_URL = 'http://httpbin.org/get'
    HTTPS_CHECK_URL = 'https://httpbin.org/get'
    POST_CHECK_URL = 'http://httpbin.org/post'

    def __init__(self, *, loop=None, checker_timeout=10, origin_ip=None):
        self.loop = loop or asyncio.get_event_loop()
        self.timeout = float(checker_timeout)
        self.origin_ip = origin_ip

    @classmethod
    def from_manager(cls, manager):
        config = manager.config
        return cls(loop=manager.loop, checker_timeout=config.get('checker_timeout'), origin_ip=config.get('origin_ip'))

    async def check_proxy(self, addr, https=False):
        anonymity = 0
        if not addr.startswith("http://"):
            proxy = "http://{0}".format(addr)
        else:
            proxy = addr
        try:
            async with aiohttp.ClientSession(loop=self.loop) as session:
                with async_timeout.timeout(self.timeout, loop=self.loop):
                    seed = str(random.randint(0, 99999999))
                    url = "{}?show_env=1&seed={}".format(self.HTTPS_CHECK_URL if https else self.HTTP_CHECK_URL, seed)
                    async with session.get(url, proxy=proxy, headers={'Connection': 'keep-alive'}) as resp:
                        body = await resp.read()
                        data = json.loads(body.decode())
                        if data['args'].get('seed') != seed:
                            return False
                        if self.origin_ip:
                            if self.origin_ip not in data['origin']:
                                anonymity = 1
                            if self._is_elite_proxy(data):
                                anonymity = 2
        except CancelledError:
            raise
        except Exception:
            return False
        log.debug("Proxy %s supports for %s", addr, 'HTTPS' if https else 'HTTP')
        return True, anonymity

    async def verify_post(self, addr):
        if not addr.startswith("http://"):
            proxy = "http://{0}".format(addr)
        else:
            proxy = addr
        try:
            async with aiohttp.ClientSession(loop=self.loop) as session:
                with async_timeout.timeout(self.timeout, loop=self.loop):
                    seed = str(random.randint(0, 99999999))
                    form_data = aiohttp.FormData()
                    form_data.add_field('seed', seed)
                    async with session.post(self.POST_CHECK_URL, data=form_data, proxy=proxy) as resp:
                        body = await resp.read()
                        data = json.loads(body.decode())
                        if data['form'].get('seed') != seed:
                            return False
        except CancelledError:
            raise
        except Exception:
            return False
        log.debug("Proxy %s supports for POST", addr)
        return True

    def _is_elite_proxy(self, data):
        if ',' in data['origin']:
            return False
        if 'Proxy-Connection' in data['headers']:
            return False
        if ',' in data['headers']['Via']:
            return False
        return True
