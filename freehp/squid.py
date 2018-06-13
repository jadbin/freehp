# coding=utf-8

import logging
import asyncio
import signal
import json
from asyncio import CancelledError
import os

import aiohttp
import async_timeout

log = logging.getLogger(__name__)

DEFAULT_UPDATE_INTERVAL = 60
DEFAULT_FREEHP_ADDRESS = 'localhost:6256'
DEFAULT_SQUID = 'squid3'
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_NUM = 0
DEFAULT_MIN_ANONYMITY = 1
DEFAULT_HTTPS = False
DEFAULT_POST = False

PEER_CONF = "cache_peer {} parent {} 0 no-query weighted-round-robin weight=1 connect-fail-limit=2 allow-miss max-conn=5 name={}\n"


class Squid:
    def __init__(self, dest_file, tpl_file, squid=DEFAULT_SQUID, update_interval=DEFAULT_UPDATE_INTERVAL,
                 timeout=DEFAULT_TIMEOUT, once=False, **kwargs):
        self.loop = asyncio.new_event_loop()
        self._dest_file = dest_file
        with open(tpl_file, 'rb') as f:
            self._template = f.read().decode()
        self._squid = squid
        self._update_interval = update_interval
        self._timeout = timeout
        self._once = once
        self._request_url = self._construct_request_url(**kwargs)
        self._futures = None
        self._is_running = False

    def _construct_request_url(self, freehp_address=DEFAULT_FREEHP_ADDRESS, max_num=DEFAULT_MAX_NUM,
                               min_anonymity=DEFAULT_MIN_ANONYMITY, https=DEFAULT_HTTPS, post=DEFAULT_POST, **kwargs):
        if freehp_address.startswith('http://') or freehp_address.startswith('https://'):
            url = freehp_address
        else:
            url = 'http://' + freehp_address
        if not url.endswith('/'):
            url += '/'
        url += 'proxies'
        url = '{}?count={}&min_anonymity={}'.format(url, max_num, min_anonymity)
        if https:
            url += '&https'
        if post:
            url += '&post'
        return url

    def start(self):
        if not self._is_running:
            self._is_running = True
            asyncio.set_event_loop(self.loop)
            if self._once:
                log.info('Run only once')
                self.loop.run_until_complete(self._maintain_squid())
                self._is_running = False
                log.info('Task is done')
            else:
                self._futures = []
                f = asyncio.ensure_future(self._maintain_squid_task(), loop=self.loop)
                self._futures.append(f)
                self.loop.add_signal_handler(signal.SIGINT,
                                             lambda loop=self.loop: asyncio.ensure_future(self.shutdown(), loop=loop))
                self.loop.add_signal_handler(signal.SIGTERM,
                                             lambda loop=self.loop: asyncio.ensure_future(self.shutdown(), loop=loop))
                log.info('Run forever')
                try:
                    self.loop.run_forever()
                except Exception:
                    log.error("Unexpected error occurred when run loop", exc_info=True)
                    raise

    async def shutdown(self):
        if not self._is_running:
            return
        self._is_running = False
        log.info("Shutdown now")
        if self._futures:
            for f in self._futures:
                f.cancel()
            self._futures = None
        await asyncio.sleep(0.001, loop=self.loop)
        self.loop.stop()
        self._recover_configuration()

    async def _maintain_squid_task(self):
        while True:
            await self._maintain_squid()
            await asyncio.sleep(self._update_interval, loop=self.loop)

    async def _maintain_squid(self):
        data = []
        try:
            async with aiohttp.ClientSession(loop=self.loop) as session:
                with async_timeout.timeout(self._timeout, loop=self.loop):
                    async with session.get(self._request_url) as resp:
                        body = await resp.read()
                        data = json.loads(body.decode('utf-8'))
                        log.debug('Get %s proxies', len(data))
        except CancelledError:
            raise
        except Exception:
            log.error("Failed to get proxies from '%s'", self._request_url, exc_info=True)

        if len(data) > 0:
            try:
                self._reconfigure_squid(data)
            except Exception:
                log.error("Failed to reconfigure squid", exc_info=True)

    def _reconfigure_squid(self, proxies):
        lines = [self._template, '\n# cache_peer configuration\n']
        for p in proxies:
            host, port = p.split(':')
            lines.append(PEER_CONF.format(host, port, host + '.' + port))
        with open(self._dest_file, 'w') as f:
            f.writelines(lines)
        log.info('Reconfigure squid with %s proxies, conf=%s', len(proxies), self._dest_file)
        try:
            if os.system('{} -k reconfigure'.format(self._squid)) != 0:
                raise RuntimeError
        except RuntimeError:
            self._recover_configuration()
            raise

    def _recover_configuration(self):
        with open(self._dest_file, 'w') as f:
            f.write(self._template)
