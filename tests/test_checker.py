# coding=utf-8

import aiohttp
from aiohttp import web
import async_timeout

from freehp.checker import HttpbinChecker, ResponseMatchChecker


async def make_proxy_server(test_server, loop):
    async def get_proxies(request):
        async with aiohttp.ClientSession(loop=loop) as session:
            with async_timeout.timeout(10, loop=loop):
                async with session.request("GET", request.raw_path) as resp:
                    body = await resp.read()
                    return web.Response(body=body,
                                        headers=resp.headers)

    app = web.Application()
    app.router.add_route("GET", "/{tail:.*}", get_proxies)
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


class TestResponseMatchChecker:
    def test_match_status(self):
        assert ResponseMatchChecker.match_status("200", 200) is True
        assert ResponseMatchChecker.match_status(200, 200) is True
        assert ResponseMatchChecker.match_status("2xX", 201) is True
        assert ResponseMatchChecker.match_status("40x", 403) is True
        assert ResponseMatchChecker.match_status("40X", 403) is True
        assert ResponseMatchChecker.match_status("50x", 403) is False
        assert ResponseMatchChecker.match_status("~20X", 200) is False
        assert ResponseMatchChecker.match_status("!20x", 400) is True
        assert ResponseMatchChecker.match_status("0200", 200) is False

    async def test_check_proxy(self, test_server, loop):
        server = await make_proxy_server(test_server, loop)
        checker = ResponseMatchChecker("http://httpbin.org/",
                                       http_status="20x",
                                       url_pattern=r"httpbin\.org",
                                       body_pattern=r"HTTP Client Testing Service",
                                       loop=loop)
        ok = await checker.check_proxy("{}:{}".format(server.host, server.port))
        assert ok is True

    async def test_wrong_http_status(self, test_server, loop):
        server = await make_proxy_server(test_server, loop)
        checker2 = ResponseMatchChecker("http://httpbin.org/",
                                        http_status=201,
                                        url_pattern=r"httpbin\.org",
                                        body_pattern=r"HTTP Client Testing Service",
                                        loop=loop)
        assert await checker2.check_proxy("{}:{}".format(server.host, server.port)) is False

    async def test_wrong_url_pattern(self, test_server, loop):
        server = await make_proxy_server(test_server, loop)
        checker3 = ResponseMatchChecker("http://httpbin.org/",
                                        http_status=200,
                                        url_pattern=r"httpbin\.com",
                                        body_pattern=r"HTTP Client Testing Service",
                                        loop=loop)
        assert await checker3.check_proxy("{}:{}".format(server.host, server.port)) is False

    async def test_wrong_body_pattern(self, test_server, loop):
        server = await make_proxy_server(test_server, loop)
        checker4 = ResponseMatchChecker("http://httpbin.org/",
                                        http_status=200,
                                        url_pattern=r"httpbin\.com",
                                        body_pattern=r"Http Client Testing Service",
                                        loop=loop)
        assert await checker4.check_proxy("{}:{}".format(server.host, server.port)) is False

    async def test_no_body_pattern(self, test_server, loop):
        server = await make_proxy_server(test_server, loop)
        checker5 = ResponseMatchChecker("http://httpbin.org/",
                                        http_status=200,
                                        url_pattern=r"httpbin\.org",
                                        loop=loop)
        assert await checker5.check_proxy("{}:{}".format(server.host, server.port)) is True
