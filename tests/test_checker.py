# coding=utf-8

import aiohttp
from aiohttp import web
import async_timeout

from freehp.checker import HttpbinChecker


async def make_proxy_server(test_server, loop):
    async def process(request):
        async with aiohttp.ClientSession(loop=loop) as session:
            with async_timeout.timeout(60, loop=loop):
                async with session.request("GET", request.raw_path) as resp:
                    body = await resp.read()
                    return web.Response(status=resp.status,
                                        body=body,
                                        headers=resp.headers)

    app = web.Application()
    app.router.add_route("GET", "/{tail:.*}", process)
    server = await test_server(app)
    return server


class TestHttpbinChecker:
    async def test_check_proxy(self, test_server, loop):
        server = await make_proxy_server(test_server, loop)
        checker = HttpbinChecker(loop=loop)
        ok = await checker.check_proxy("{}:{}".format(server.host, server.port))
        assert ok is True
        ok = await checker.check_proxy("{}:{}".format(server.host, server.port - 1))
        assert ok is False
