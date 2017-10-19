# coding=utf-8

import asyncio
import json
import random
import pytest
from aiohttp import web

from freehp.pool import deasync, ProxyPool, SimpleProxyPool
from freehp.errors import NoProxyAvailable


class DeasyncClass:
    def __init__(self, loop=None):
        if loop is None:
            self.asyn = False
            self.loop = asyncio.new_event_loop()
        else:
            self.asyn = True
            self.loop = loop

    @deasync
    async def perform_deasync(self):
        return True


def test_deasync(loop):
    a = DeasyncClass()
    assert a.perform_deasync() is True
    b = DeasyncClass(loop)
    assert loop.run_until_complete(b.perform_deasync()) is True


class TestSimplePool:
    random_iter = 0

    async def test_get_proxy(self, monkeypatch, test_server, loop):
        monkeypatch.setattr(random, 'randint', self.randint)
        server = await self.make_server(test_server)
        pool = SimpleProxyPool("http://{}:{}".format(server.host, server.port), loop=loop)
        target_list = [i for i in range(10)] * 2
        for i in range(20):
            assert await pool.get_proxy() == target_list[i]
        self.random_iter = 0

    async def test_no_proxy_available(self, monkeypatch, test_server, loop):
        monkeypatch.setattr(random, 'randint', self.randint)
        server = await self.make_server(test_server)
        pool = SimpleProxyPool("http://{}:{}".format(server.host, server.port), loop=loop)
        server.proxy_list = []
        with pytest.raises(NoProxyAvailable):
            await pool.get_proxy()
        server.proxy_list = self.make_proxy_list()
        assert await pool.get_proxy() == 0
        pool._last_update = 0
        server.proxy_list = []
        assert await pool.get_proxy() == 1
        self.random_iter = 0

    async def test_min_success_rate(self, monkeypatch, test_server, loop):
        monkeypatch.setattr(random, 'randint', self.randint)
        server = await self.make_server(test_server)
        pool = SimpleProxyPool("http://{}:{}".format(server.host, server.port),
                               min_success_rate=0.8, loop=loop)
        target_list = [i for i in range(7)] * 2
        for i in range(len(target_list)):
            assert await pool.get_proxy() == target_list[i]
        self.random_iter = 0

    async def test_min_count(self, monkeypatch, test_server, loop):
        monkeypatch.setattr(random, 'randint', self.randint)
        server = await self.make_server(test_server)
        pool = SimpleProxyPool("http://{}:{}".format(server.host, server.port),
                               min_success_rate=0.8, min_count=8, loop=loop)
        target_list = [i for i in range(8)] * 2
        for i in range(len(target_list)):
            assert await pool.get_proxy() == target_list[i]
        self.random_iter = 0

    async def test_update_another_proxy_list(self, monkeypatch, test_server, loop):
        monkeypatch.setattr(random, 'randint', self.randint)
        server = await self.make_server(test_server)
        pool = SimpleProxyPool("http://{}:{}".format(server.host, server.port), loop=loop)
        assert await pool.get_proxy() == 0
        pool._last_update = 0
        server.proxy_list = self.make_another_proxy_list()
        target_list = ([i for i in range(11, 20)] + [10]) * 2
        for i in range(len(target_list)):
            assert await pool.get_proxy() == target_list[i]
        self.random_iter = 0

    def make_proxy_list(self):
        proxy_list = []
        for i in range(10):
            proxy_list.append({"addr": i, "success": 10 - i, "fail": 1})
        return proxy_list

    def make_another_proxy_list(self):
        proxy_list = []
        for i in range(10):
            proxy_list.append({"addr": 10 + i, "success": 10 - i, "fail": 1})
        return proxy_list

    async def make_server(self, test_server):
        def get_proxies(request):
            return web.Response(body=json.dumps(server.proxy_list).encode("utf-8"),
                                charset="utf-8",
                                content_type="application/json")

        app = web.Application()
        app.router.add_route("GET", "/", get_proxies)
        server = await test_server(app)
        server.proxy_list = self.make_proxy_list()
        return server

    def randint(self, a, b):
        res = a + self.random_iter % (b - a + 1)
        self.random_iter += 1
        return res


class TestProxyPool:
    random_iter = 0

    async def test_update_proxy_list_initially(self, test_server, loop):
        server = await self.make_server(test_server)
        pool = ProxyPool("http://{}:{}".format(server.host, server.port), loop=loop, pool_size=2)
        await pool._update_proxy_list()
        assert len(pool._proxies) == 12 and len(pool._pool) == 2 and len(pool._backup) == 10
        for i in range(2):
            assert i in pool._proxies
            p = pool._proxies[i]
            assert p in pool._pool
            assert p.addr == i and p.good == 0 and p.bad == 0 and p.fail == 1
            assert abs(p.base_rate - 0.8 * (20 - i) / (20 - i + 2)) < 0.001
        for i in range(2, 12):
            assert i in pool._proxies
            p = pool._proxies[i]
            assert p in pool._backup
            assert p.addr == i and p.good == 0 and p.bad == 0 and p.fail == 1
            assert abs(p.base_rate - 0.8 * (20 - i) / (20 - i + 2)) < 0.001
        assert len(pool._trash) == 0

    async def test_update_another_proxy_list(self, test_server, loop):
        server = await self.make_server(test_server)
        pool = ProxyPool("http://{}:{}".format(server.host, server.port), loop=loop, pool_size=2)
        await pool._update_proxy_list()
        pool._last_update = 0
        server.proxy_list = self.make_another_proxy_list()
        await pool._update_proxy_list()
        assert len(pool._proxies) == 12 and len(pool._pool) == 2 and len(pool._backup) == 10
        for i in range(20, 25):
            assert i in pool._proxies and pool._proxies[i] in pool._backup
        for i in range(2, 7):
            assert i in pool._proxies and pool._proxies[i] in pool._backup
        assert len(pool._trash) == 0

    async def test_get_proxy(self, test_server, monkeypatch, loop):
        monkeypatch.setattr(random, 'random', self.myrandom)
        server = await self.make_server(test_server)
        pool = ProxyPool("http://{}:{}".format(server.host, server.port), loop=loop, pool_size=2)
        target_list = []
        k = 0
        a = [0, 1]
        ai = 0
        b = [i for i in range(2, 12)]
        bi = 0
        for i in range(100):
            if k < 8:
                target_list.append(a[ai])
                ai += 1
                if ai >= len(a):
                    ai = 0
            else:
                target_list.append(b[bi])
                bi += 1
                if bi >= len(b):
                    bi = 0
            k += 1
            if k >= 10:
                k = 0
        for i in range(100):
            assert await pool.get_proxy() == target_list[i]
        self.random_iter = 0

    async def test_no_proxy_available(self, test_server, loop):
        server = await self.make_server(test_server)
        pool = ProxyPool("http://{}:{}".format(server.host, server.port), loop=loop, pool_size=2)
        server.proxy_list = []
        with pytest.raises(NoProxyAvailable):
            await pool.get_proxy()

    async def test_feed_back(self, test_server, loop):
        server = await self.make_server(test_server)
        pool = ProxyPool("http://{}:{}".format(server.host, server.port), loop=loop, pool_size=2)
        await pool._update_proxy_list()
        pool.feed_back(0, False)
        assert len(pool._pool) == 2 and len(pool._backup) == 10 and len(pool._proxies) == 12
        assert pool._proxies[0] in pool._backup and pool._proxies[2] in pool._pool
        pool.feed_back(11, False)
        assert len(pool._pool) == 2 and len(pool._backup) == 10 and len(pool._proxies) == 12
        assert pool._proxies[11] in pool._backup
        for i in range(1, 11):
            pool.feed_back(i, False)
        assert len(pool._pool) == 2 and len(pool._backup) == 10 and len(pool._proxies) == 12
        for i in range(2):
            assert pool._proxies[i] in pool._pool
        for i in range(3, 12):
            assert pool._proxies[i] in pool._backup
        p11 = pool._proxies[11]
        pool.feed_back(11, False)
        assert len(pool._pool) == 2 and len(pool._backup) == 9 and len(pool._proxies) == 11 and len(pool._trash) == 1
        assert p11 not in pool._backup and p11 not in pool._proxies and 11 in pool._trash
        pool.feed_back(0, True)
        assert len(pool._pool) == 2 and len(pool._backup) == 9 and len(pool._proxies) == 11
        assert pool._proxies[0] in pool._pool
        p1 = pool._proxies[1]
        pool.feed_back(1, False)
        assert len(pool._pool) == 2 and len(pool._backup) == 8 and len(pool._proxies) == 10 and len(pool._trash) == 2
        assert p1 not in pool._pool and p1 not in pool._proxies and 1 in pool._trash and pool._proxies[2] in pool._pool
        pool.feed_back(3, True)
        assert len(pool._pool) == 2 and len(pool._backup) == 8 and len(pool._proxies) == 10 and len(pool._trash) == 2
        assert pool._proxies[3] in pool._pool and pool._proxies[2] in pool._backup
        pool.feed_back(4, True)
        assert len(pool._pool) == 2 and len(pool._backup) == 8 and len(pool._proxies) == 10 and len(pool._trash) == 2
        assert pool._proxies[4] in pool._backup

    async def test_feed_back_in_trash(self, test_server, loop):
        server = await self.make_server(test_server)
        pool = ProxyPool("http://{}:{}".format(server.host, server.port), loop=loop, pool_size=2)
        await pool._update_proxy_list()
        pool.feed_back(0, False)
        pool._last_update = 0
        await pool._update_proxy_list()
        assert 0 in pool._trash
        assert pool._trash[0].good == 0 and pool._trash[0].bad == 1 and pool._trash[0].fail == 2
        pool.feed_back(0, False)
        assert 0 in pool._trash
        assert pool._trash[0].good == 0 and pool._trash[0].bad == 2 and pool._trash[0].fail == 3
        pool.feed_back(0, False)
        assert 0 in pool._trash
        assert pool._trash[0].good == 0 and pool._trash[0].bad == 2 and pool._trash[0].fail == 3
        pool.feed_back(0, True)
        assert 0 in pool._trash
        assert pool._trash[0].good == 0 and pool._trash[0].bad == 2 and pool._trash[0].fail == 3
        pool.feed_back(1, False)
        pool._last_update = 0
        await pool._update_proxy_list()
        assert 1 in pool._trash
        assert pool._trash[1].good == 0 and pool._trash[1].bad == 1 and pool._trash[1].fail == 2
        pool.feed_back(1, True)
        assert 1 in pool._trash
        assert pool._trash[1].good == 1 and pool._trash[1].bad == 1 and pool._trash[1].fail == 0
        for i in range(2):
            pool.feed_back(1, True)
        assert 1 in pool._trash
        assert pool._trash[1].good == 3 and pool._trash[1].bad == 1 and pool._trash[1].fail == 0
        pool.feed_back(2, False)
        pool.feed_back(1, True)
        assert 1 not in pool._trash and 1 in pool._proxies and pool._proxies[1] in pool._backup
        assert len(pool._trash) == 2 and 2 in pool._trash

    async def test_add_new_proxy_from_trash(self, test_server, loop):
        server = await self.make_server(test_server)
        pool = ProxyPool("http://{}:{}".format(server.host, server.port), loop=loop, pool_size=2)
        await pool._update_proxy_list()
        pool.feed_back(0, False)
        pool._last_update = 0
        await pool._update_proxy_list()
        assert len(pool._trash) == 1 and 0 in pool._trash
        pool.feed_back(1, False)
        assert len(pool._trash) == 1
        pool._last_update = 0
        server.proxy_list = [{"addr": 0, "success": 20, "fail": 1}]
        await pool._update_proxy_list()
        assert len(pool._trash) == 1 and 1 in pool._trash
        assert 0 in pool._proxies
        p0 = pool._proxies[0]
        assert p0 in pool._backup
        assert p0.good == 0 and p0.bad == 1 and p0.fail == 2

    async def test_block_proxy(self, test_server, loop):
        server = await self.make_server(test_server)
        pool = ProxyPool("http://{}:{}".format(server.host, server.port), loop=loop, pool_size=2)
        await pool._update_proxy_list()
        pool.feed_back(0, False)
        pool.feed_back(0, False)
        assert len(pool._trash) == 1 and 0 in pool._trash
        assert len(pool._block_queue) == 1 and pool._block_queue[0][0] == 0
        pool.block_time = 1
        pool._remove_block()
        assert len(pool._block_queue) == 1 and pool._block_queue[0][0] == 0
        pool._last_update = 0
        await pool._update_proxy_list()
        assert len(pool._trash) == 1 and 0 in pool._trash
        assert 12 in pool._proxies and pool._proxies[12] in pool._backup
        for i in range(1, 13):
            pool.feed_back(i, True)
        pool.block_time = 0
        pool._remove_block()
        assert len(pool._block_queue) == 0 and len(pool._trash) == 0
        pool.block_time = 1
        pool._last_update = 0
        server.proxy_list = [{"addr": 0, "success": 20, "fail": 1}]
        await pool._update_proxy_list()
        assert 0 in pool._proxies
        p0 = pool._proxies[0]
        assert p0 in pool._backup and p0.good == 0 and p0.bad == 0 and p0.fail == 1
        assert len(pool._trash) == 1 and 12 not in pool._proxies and 12 in pool._trash

    def make_proxy_list(self):
        proxy_list = []
        for i in range(20):
            proxy_list.append({"addr": i, "success": 20 - i, "fail": 1})
        return proxy_list

    def make_another_proxy_list(self):
        proxy_list = []
        for i in range(5):
            proxy_list.append({"addr": 20 + i, "success": 25 - i, "fail": 1})
        return proxy_list

    async def make_server(self, test_server):
        def get_proxies(request):
            return web.Response(body=json.dumps(server.proxy_list).encode("utf-8"),
                                charset="utf-8",
                                content_type="application/json")

        app = web.Application()
        app.router.add_route("GET", "/", get_proxies)
        server = await test_server(app)
        server.proxy_list = self.make_proxy_list()
        return server

    def myrandom(self):
        res = self.random_iter * 0.1
        self.random_iter += 1
        if self.random_iter >= 10:
            self.random_iter = 0
        return res
