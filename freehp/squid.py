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

PEER_CONF = 'cache_peer {} parent {} 0 no-query weighted-round-robin weight=1 connect-fail-limit=2 allow-miss max-conn=5 name={}\n'
PEER_ACCESS_CONF = 'cache_peer_access {} {} {}\n'


class Squid:
    def __init__(self, dest_file, tpl_file, squid=DEFAULT_SQUID, update_interval=DEFAULT_UPDATE_INTERVAL,
                 timeout=DEFAULT_TIMEOUT, once=False, min_anonymity=DEFAULT_MIN_ANONYMITY, **kwargs):
        self.loop = asyncio.new_event_loop()
        self._dest_file = dest_file
        with open(tpl_file, 'rb') as f:
            self._template = f.read().decode()
        self._squid = squid
        self._update_interval = update_interval
        self._timeout = timeout
        self._once = once
        self._min_anonymity = min_anonymity
        self._request_urls = self._construct_request_urls(**kwargs)
        self._futures = None
        self._is_running = False

    def _construct_request_urls(self, address=DEFAULT_FREEHP_ADDRESS, max_num=DEFAULT_MAX_NUM,
                                https=DEFAULT_HTTPS, post=DEFAULT_POST, **kwargs):
        if not address.startswith('http://') and not address.startswith('https://'):
            address = 'http://' + address
        if not address.endswith('/'):
            address += '/'
        address += 'proxies'

        urls = []
        url = '{}?count={}&min_anonymity={}&detail'.format(address, max_num, self._min_anonymity)
        urls.append(url)
        if https:
            url = '{}?count={}&https&detail'.format(address, max_num)
            urls.append(url)
        if post:
            url = '{}?count={}&min_anonymity={}&post&detail'.format(address, max_num, self._min_anonymity)
            urls.append(url)
        return urls

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
        proxies = set()
        try:
            for url in self._request_urls:
                async with aiohttp.ClientSession(loop=self.loop) as session:
                    with async_timeout.timeout(self._timeout, loop=self.loop):
                        async with session.get(url) as resp:
                            body = await resp.read()
                            d = json.loads(body.decode('utf-8'))
                            for i in d:
                                a = i['address']
                                if a not in proxies:
                                    proxies.add(a)
                                    data.append(i)
            log.debug('Get %s proxies', len(data))
        except CancelledError:
            raise
        except Exception:
            log.error("Failed to get proxies", exc_info=True)

        if len(data) > 0:
            try:
                self._reconfigure_squid(data)
            except Exception:
                log.error("Failed to reconfigure squid", exc_info=True)

    def _reconfigure_squid(self, proxies):
        lines = [self._template, '\n# cache_peer configuration\n']
        for p in proxies:
            host, port = p['address'].split(':')
            name = host + '.' + port
            lines.append(PEER_CONF.format(host, port, name))
            dl = []
            if p['anonymity'] < self._min_anonymity:
                dl.append('!SSL_ports')
            if not p['https']:
                dl.append('SSL_ports')
            if not p['post']:
                dl.append('POST')
            if len(dl) > 0:
                lines.append(PEER_ACCESS_CONF.format(name, 'deny', ' '.join(dl)))

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
