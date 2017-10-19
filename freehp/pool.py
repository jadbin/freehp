# coding=utf-8

import json
import time
import asyncio
import logging
from collections import deque
import random

import aiohttp
import async_timeout

from freehp.errors import NoProxyAvailable
from freehp.data import PriorityQueue, ProxyInfo

log = logging.getLogger(__name__)


def deasync(func):
    def perform_deasync(self, *args, **kwargs):
        if self.asyn:
            res = func(self, *args, **kwargs)
        else:
            res = self.loop.run_until_complete(func(self, *args, **kwargs))
        return res

    return perform_deasync


class SimpleProxyPool:
    def __init__(self, agent_addr, *, min_success_rate=.0, min_count=0,
                 update_interval=300, auth=None, params=None, timeout=20, loop=None):
        """
        SimpleProxyPool constructor.

        agent_addr - Proxy agent address.
        min_success_rate - (optional) The minimum acceptable success rate of a proxy.
        min_count - (optional) The least number of proxies in the proxy list.
          It works when pass the `min_success_rate` parameter.
        update_interval - (optional) Time interval to update the proxy list from proxy agent.
        auth - (optional) Http Basic Auth tuple.
        params - (optional) Prameters dictionary be sent in the query.
        timeout - (optional) Timeout when connects proxy agent.
        loop - (optional) Event loop.
        """
        self.agent_addr = agent_addr
        if loop is None:
            self.asyn = False
            self.loop = asyncio.new_event_loop()
        else:
            self.asyn = True
            self.loop = loop
        self.auth = auth
        if self.auth is not None:
            if isinstance(self.auth, tuple):
                self.auth = aiohttp.BasicAuth(*self.auth)
            elif not isinstance(self.auth, aiohttp.BasicAuth):
                raise TypeError('The type of "auth" must be tuple or aiohttp.BasicAuth')
        self.params = params or {}
        self.timeout = timeout
        self.update_interval = update_interval
        self.min_success_rate = min_success_rate
        self.min_count = min_count
        self._last_update = 0
        self._update_lock = asyncio.Lock(loop=self.loop)
        self.proxies = []

    @deasync
    async def get_proxy(self):
        """
        随机获取其中的某个代理.
        """
        await self._check_update()
        if len(self.proxies) == 0:
            raise NoProxyAvailable
        return self.proxies[random.randint(0, len(self.proxies) - 1)]

    async def _check_update(self):
        async with self._update_lock:
            t = time.time()
            if t > self._last_update:
                await self._update_proxy_list()
                if len(self.proxies) > 0:
                    self._last_update = t + self.update_interval

    async def _update_proxy_list(self):
        try:
            self.params['detail'] = ''
            async with aiohttp.ClientSession(loop=self.loop) as session:
                with async_timeout.timeout(self.timeout, loop=self.loop):
                    async with session.request('GET', self.agent_addr,
                                               auth=self.auth,
                                               params=self.params) as resp:
                        body = await resp.read()
                        proxies = json.loads(body.decode('utf-8'))
                        if len(proxies) > 0:
                            res = []
                            for p in proxies:
                                if self.min_success_rate > 0:
                                    if p['success'] >= self.min_success_rate * (p['success'] + p['fail']):
                                        res.append(p['addr'])
                                    elif self.min_count > 0 and len(res) < self.min_count:
                                        res.append(p['addr'])
                                    else:
                                        break
                                else:
                                    res.append(p['addr'])
                            self.proxies = res
        except Exception:
            log.warning("Error occurred when get proxy list", exc_info=True)


class ProxyPool:
    pool_ratio = 0.8

    def __init__(self, agent_addr, *, pool_size=100, block_time=3600, max_fail_times=2,
                 update_interval=300, auth=None, params=None, timeout=20, loop=None):
        """
        ProxyPool constructor.

        agent_addr - Proxy agent address.
        pool_size - (optional) The size of the pool.
        block_time - (optional) Time for blocking a proxy.
        max_fail_times - (optional) The maximum acceptable number of the continuous failure of a proxy.
        update_interval - (optional) Time interval to update the proxy list from proxy agent.
        auth - (optional) Http Basic Auth tuple.
        params - (optional) Prameters dictionary be sent in the query.
        timeout - (optional) Timeout when connects proxy agent.
        loop - (optional) Event loop.
        """
        self.agent_addr = agent_addr
        if loop is None:
            self.asyn = False
            self.loop = asyncio.new_event_loop()
        else:
            self.asyn = True
            self.loop = loop
        self.auth = auth
        if self.auth is not None:
            if isinstance(self.auth, tuple):
                self.auth = aiohttp.BasicAuth(*self.auth)
            elif not isinstance(self.auth, aiohttp.BasicAuth):
                raise TypeError('The type of "auth" must be tuple or aiohttp.BasicAuth')
        self.params = params or {}
        self.timeout = timeout

        self.update_interval = update_interval
        self._last_update = 0
        self._update_lock = asyncio.Lock(loop=self.loop)
        self.max_fail_times = max_fail_times

        self._proxies = {}

        self._pool = PriorityQueue(pool_size)
        self._pool_p = PriorityQueue(pool_size)
        self._pool_n = PriorityQueue(pool_size)

        self.backup_size = pool_size * 5
        self._backup = PriorityQueue(self.backup_size)
        self._backup_p = PriorityQueue(self.backup_size)
        self._backup_n = PriorityQueue(self.backup_size)

        self.block_time = block_time
        self._trash = {}
        self._block_queue = deque()

    @deasync
    async def get_proxy(self):
        """
        获取代理.

        返回代理的地址.
        """
        await self._check_update()
        if len(self._pool) <= 0 and len(self._backup) <= 0:
            raise NoProxyAvailable
        if len(self._pool) <= 0:
            return self._get_proxy_from_backup()
        if len(self._backup) <= 0:
            return self._get_proxy_from_pool()
        if random.random() < self.pool_ratio:
            return self._get_proxy_from_pool()
        return self._get_proxy_from_backup()

    def feed_back(self, addr, ok):
        """
        反馈代理是否可用.

        addr - 代理的地址.
        ok - 反馈结果，如果为True表示可用，False表示不可用.
        """
        if addr not in self._proxies:
            if addr in self._trash:
                proxy = self._trash[addr]
                if proxy.fail <= self.max_fail_times:
                    if ok:
                        proxy.good += 1
                        proxy.fail = 0
                        del self._trash[proxy.addr]
                        proxy.timestamp = time.time()
                        self._add_proxy(proxy)
                    else:
                        proxy.bad += 1
                        proxy.fail += 1
            return
        proxy = self._proxies[addr]
        if proxy.status == proxy.IN_POOL:
            self._pop_pool(proxy)
        elif proxy.status == proxy.IN_BACKUP:
            self._pop_backup(proxy)
        else:
            log.error("Illegal status of proxy {}: {}".format(proxy.addr, proxy.status))
            proxy = None
        if proxy is not None:
            proxy.timestamp = time.time()
            if ok:
                proxy.good += 1
                proxy.fail = 0
                if not self._pool.is_full():
                    self._push_pool(proxy)
                    proxy = None
                else:
                    p = self._pool_n.top()
                    if (proxy.rate, proxy.timestamp) > (p.rate, p.timestamp):
                        self._pop_pool(p)
                        self._push_pool(proxy)
                        proxy = p
            else:
                proxy.bad += 1
                proxy.fail += 1
                if proxy.fail > self.max_fail_times:
                    self._throw_proxy(proxy)
                    proxy = None
                if not self._pool.is_full():
                    if len(self._backup) > 0:
                        p = self._backup_p.top()
                        self._pop_backup(p)
                        self._push_pool(p)
        if proxy is not None:
            self._push_backup(proxy)

    def _get_proxy_from_pool(self):
        p = self._pool.top()
        del self._pool[p]
        self._pool.push(p, -time.time())
        return p.addr

    def _get_proxy_from_backup(self):
        p = self._backup.top()
        del self._backup[p]
        self._backup.push(p, -time.time())
        return p.addr

    def _add_new_proxy(self, proxy):
        if proxy.addr in self._trash:
            p = self._trash[proxy.addr]
            if p.fail > self.max_fail_times:
                return
            del self._trash[proxy.addr]
            p.timestamp = proxy.timestamp
            self._add_proxy(p)
        elif proxy.addr not in self._proxies:
            self._add_proxy(proxy)

    def _add_proxy(self, proxy):
        self._proxies[proxy.addr] = proxy
        if not self._pool.is_full():
            self._push_pool(proxy)
            proxy = None
        if proxy is not None:
            if self._backup.is_full():
                p = self._backup_n.top()
                if (proxy.rate, -proxy.fail, proxy.timestamp) > (p.rate, -p.fail, p.timestamp):
                    self._pop_backup(p)
                    self._push_backup(proxy)
                    proxy = p
            else:
                self._push_backup(proxy)
                proxy = None
        if proxy is not None:
            self._throw_proxy(proxy)

    def _throw_proxy(self, proxy):
        if proxy.addr in self._proxies:
            del self._proxies[proxy.addr]
        if proxy.addr not in self._trash and proxy.good + proxy.bad > 0:
            proxy.timestamp = time.time()
            self._trash[proxy.addr] = proxy
            self._block_queue.append((proxy.addr, proxy.timestamp))

    async def _check_update(self):
        async with self._update_lock:
            t = time.time()
            if t > self._last_update:
                await self._update_proxy_list()
                if len(self._pool) + len(self._backup) > 0:
                    self._last_update = t + self.update_interval

    async def _update_proxy_list(self):
        try:
            self.params['detail'] = ''
            async with aiohttp.ClientSession(loop=self.loop) as session:
                with async_timeout.timeout(self.timeout, loop=self.loop):
                    async with session.request('GET',
                                               self.agent_addr,
                                               auth=self.auth,
                                               params=self.params) as resp:
                        body = await resp.read()
                        proxies = json.loads(body.decode('utf-8'))

                        self._remove_block()
                        t = time.time()
                        for p in proxies:
                            r = 0.8 * (p['success'] / (p['success'] + p['fail'] + 1.0))
                            proxy = PoolProxyInfo(p['addr'], t, base_rate=r)
                            self._add_new_proxy(proxy)
        except Exception:
            log.warning("Error occurred when get proxy list", exc_info=True)

    def _remove_block(self):
        """
        移除过期的封禁代理
        """
        t = time.time()
        while len(self._block_queue) > 0:
            addr, timestamp = self._block_queue[0]
            if timestamp + self.block_time > t:
                break
            self._block_queue.popleft()
            if addr in self._trash:
                p = self._trash[addr]
                if p.timestamp - 0.001 < timestamp:
                    del self._trash[addr]

    def _push_pool(self, proxy):
        self._pool.push(proxy, -time.time())
        self._pool_p.push(proxy, (proxy.rate, proxy.timestamp))
        self._pool_n.push(proxy, (-proxy.rate, -proxy.timestamp))
        proxy.status = proxy.IN_POOL

    def _pop_pool(self, proxy):
        del self._pool[proxy]
        del self._pool_p[proxy]
        del self._pool_n[proxy]
        proxy.status = None

    def _push_backup(self, proxy):
        self._backup.push(proxy, -time.time())
        self._backup_p.push(proxy, (proxy.rate, -proxy.fail, proxy.timestamp))
        self._backup_n.push(proxy, (-proxy.rate, proxy.fail, -proxy.timestamp))
        proxy.status = proxy.IN_BACKUP

    def _pop_backup(self, proxy):
        del self._backup[proxy]
        del self._backup_p[proxy]
        del self._backup_n[proxy]
        proxy.status = None


class PoolProxyInfo(ProxyInfo):
    IN_POOL = 1
    IN_BACKUP = 2

    def __init__(self, *args, base_rate=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_rate = base_rate
        self.status = None

    @property
    def rate(self):
        tot = self.good + self.bad
        if tot < 10:
            rho = 2 * (1 / (1 + 2 ** (-tot)) - 0.5)
            return rho * self.good / (tot + 1) + (1.0 - rho) * self.base_rate
        return self.good / (tot + 1)
