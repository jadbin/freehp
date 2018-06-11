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

PEER_CONF = "cache_peer {} parent {} 0 no-query weighted-round-robin weight=1 connect-fail-limit=2 allow-miss max-conn=5 name={}\n"


class Squid:
    def __init__(self, dest_file, tpl_file, freehp_address=DEFAULT_FREEHP_ADDRESS, squid=DEFAULT_SQUID,
                 max_num=DEFAULT_MAX_NUM, update_interval=DEFAULT_UPDATE_INTERVAL, timeout=DEFAULT_TIMEOUT, once=False):
        self.loop = asyncio.new_event_loop()
        self._dest_file = dest_file
        with open(tpl_file, 'rb') as f:
            self._template = f.read().decode()
        self._squid = squid
        self._max_num = max_num
        self._update_interval = update_interval
        self._timeout = timeout
        self._once = once
        if freehp_address.startswith('http://') or freehp_address.startswith('https://'):
            self._freehp_address = freehp_address
        else:
            self._freehp_address = 'http://' + freehp_address
        if not self._freehp_address.endswith('/'):
            self._freehp_address += '/'
        self._freehp_address += 'proxies'
        if max_num > 0:
            self._freehp_address = '{}?count={}'.format(self._freehp_address, max_num)
        self._future = None
        self._is_running = False

    def start(self):
        if not self._is_running:
            self._is_running = True
            asyncio.set_event_loop(self.loop)
            if self._once:
                log.info('Run only once')
                self.loop.run_until_complete(self._maintain_squid())
                log.info('Task is done')
            else:
                self._future = asyncio.ensure_future(self._maintain_squid_task(), loop=self.loop)
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
        if self._future:
            self._future.cancel()
        self._future = None
        await asyncio.sleep(0.001, loop=self.loop)
        self.loop.stop()

    async def _maintain_squid_task(self):
        while True:
            await self._maintain_squid()
            await asyncio.sleep(self._update_interval, loop=self.loop)

    async def _maintain_squid(self):
        data = []
        try:
            async with aiohttp.ClientSession(loop=self.loop) as session:
                with async_timeout.timeout(self._timeout, loop=self.loop):
                    async with session.request("GET", self._freehp_address) as resp:
                        body = await resp.read()
                        data = json.loads(body.decode('utf-8'))
                        log.debug('Get %s proxies', len(data))
        except CancelledError:
            raise
        except Exception:
            log.error("Error occurred when get proxies from '%s'", self._freehp_address, exc_info=True)

        if len(data) > 0:
            try:
                self._reconfigure_squid(data)
            except Exception:
                log.error("Error occurred when reconfigure squid", exc_info=True)

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
            with open(self._dest_file, 'w') as f:
                f.write(self._template)
            raise
