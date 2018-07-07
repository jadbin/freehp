# coding=utf-8

import aiohttp
from aiohttp import web
import async_timeout

from freehp.checker import HttpbinChecker


async def make_proxy_server(aiohttp_server, loop):
    async def process(request):
        async with aiohttp.ClientSession(loop=loop) as session:
            with async_timeout.timeout(60, loop=loop):
                async with session.request("GET", request.raw_path) as resp:
                    body = await resp.read()
                    return web.Response(status=resp.status,
                                        body=body,
                                        headers=resp.headers)

    app = web.Application(loop=loop)
    app.router.add_route("GET", "/{tail:.*}", process)
    server = await aiohttp_server(app)
    return server


class TestHttpbinChecker:
    async def test_check_proxy(self, aiohttp_server, loop):
        server = await make_proxy_server(aiohttp_server, loop)
        checker = HttpbinChecker(loop=loop)
        res = await checker.check_proxy("{}:{}".format(server.host, server.port))
        assert res and res[0] is True
        res = await checker.check_proxy("{}:{}".format(server.host, server.port - 1))
        assert not res
