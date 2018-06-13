# coding=utf-8

import json
import random
import asyncio
import logging
from asyncio import CancelledError
import re

import aiohttp
import async_timeout

log = logging.getLogger(__name__)

IP_REG = re.compile('^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$')

HTTP_CHECK_URL = 'http://httpbin.org/get'
HTTPS_CHECK_URL = 'https://httpbin.org/get'
POST_CHECK_URL = 'http://httpbin.org/post'


class HttpbinChecker:
    def __init__(self, *, loop=None, timeout=10):
        self.loop = loop or asyncio.get_event_loop()
        self.timeout = int(timeout)

        self.origin_ip = self.loop.run_until_complete(self.get_origin_ip())
        if not self.origin_ip:
            raise RuntimeError('Failed to get origin IP address')
        log.info('Origin IP address: %s', self.origin_ip)

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
            async with aiohttp.ClientSession(loop=self.loop) as session:
                with async_timeout.timeout(self.timeout, loop=self.loop):
                    seed = str(random.randint(0, 99999999))
                    url = "{}?show_env=1&seed={}".format(HTTP_CHECK_URL, seed)
                    async with session.get(url, proxy=proxy, headers={'Connection': 'keep-alive'}) as resp:
                        body = await resp.read()
                        data = json.loads(body.decode())
                        if data['args'].get('seed') != seed:
                            return False
                        if self.origin_ip not in data['origin']:
                            anonymity = 1
                        if self._is_elite_proxy(data):
                            anonymity = 2
        except CancelledError:
            raise
        except Exception:
            return False
        log.debug("Proxy %s is OK", addr)
        return True, anonymity

    async def verify_https(self, addr):
        if not addr.startswith("http://"):
            proxy = "http://{0}".format(addr)
        else:
            proxy = addr
        try:
            async with aiohttp.ClientSession(loop=self.loop) as session:
                with async_timeout.timeout(self.timeout, loop=self.loop):
                    seed = str(random.randint(0, 99999999))
                    url = "{}?seed={}".format(HTTPS_CHECK_URL, seed)
                    async with session.get(url, proxy=proxy) as resp:
                        body = await resp.read()
                        data = json.loads(body.decode())
                        if data['args'].get('seed') != seed:
                            return False
        except CancelledError:
            raise
        except Exception:
            return False
        log.debug("Proxy %s supports for HTTPS", addr)
        return True

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
                    async with session.post(POST_CHECK_URL, data=form_data, proxy=proxy) as resp:
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

    async def get_origin_ip(self):
        ip = None
        try:
            async with aiohttp.ClientSession(loop=self.loop) as session:
                with async_timeout.timeout(self.timeout, loop=self.loop):
                    async with session.request('GET', HTTP_CHECK_URL) as resp:
                        body = await resp.read()
                        data = json.loads(body.decode())
                        ip = data['origin']
            assert IP_REG.match(ip) is not None
        except CancelledError:
            raise
        except Exception:
            pass
        return ip

    def _is_elite_proxy(self, data):
        if ',' in data['origin']:
            return False
        if 'Proxy-Connection' in data['headers']:
            return False
        if ',' in data['headers']['Via']:
            return False
        return True
