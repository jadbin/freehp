# coding=utf-8

import logging
import asyncio
import signal
import json
from asyncio import CancelledError
import os
import inspect

import aiohttp
import async_timeout

from freehp.config import Setting, Config

log = logging.getLogger(__name__)


class Squid:
    PEER_CONF = 'cache_peer {} parent {} 0 no-query weighted-round-robin weight=1 connect-fail-limit=2 allow-miss max-conn=5 name={}\n'
    PEER_ACCESS_CONF = 'cache_peer_access {} {} {}\n'

    def __init__(self, dest_file, tpl_file, config=None):
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        self._dest_file = dest_file
        with open(tpl_file, 'rb') as f:
            self._template = f.read().decode()
        self._config = config or SquidConfig()
        self._request_urls = self._construct_request_urls()
        self._futures = None
        self._is_running = False

    def _construct_request_urls(self):
        address = self._config.get('address')
        max_num = self._config.getint('max_num')
        min_anonymity = self._config.getint('min_anonymity')
        https = self._config.getbool('https')
        post = self._config.getbool('post')

        if not address.startswith('http://') and not address.startswith('https://'):
            address = 'http://' + address
        if not address.endswith('/'):
            address += '/'
        address += 'proxies'

        urls = []
        url = '{}?count={}&min_anonymity={}&detail'.format(address, max_num, min_anonymity)
        urls.append(url)
        if https:
            url = '{}?count={}&https&detail'.format(address, max_num)
            urls.append(url)
        if post:
            url = '{}?count={}&min_anonymity={}&post&detail'.format(address, max_num, min_anonymity)
            urls.append(url)
        return urls

    def start(self):
        if not self._is_running:
            self._is_running = True
            if self._config.getbool('once'):
                log.info('Run only once')
                self.loop.run_until_complete(self._maintain_squid())
                self._is_running = False
                log.info('Task is done')
            else:
                self._futures = []
                f = asyncio.ensure_future(self._maintain_squid_task(), loop=self.loop)
                self._futures.append(f)
                self.loop.add_signal_handler(signal.SIGINT, lambda sig=signal.SIGINT: self.shutdown(sig=sig))
                self.loop.add_signal_handler(signal.SIGTERM, lambda sig=signal.SIGTERM: self.shutdown(sig=sig))
                log.info('Run forever')
                try:
                    self.loop.run_forever()
                except Exception:
                    log.error("Unexpected error occurred when run loop", exc_info=True)
                    raise

    def shutdown(self, sig=None):
        if sig is not None:
            log.info('Received shutdown signal: %s', sig)
        if not self._is_running:
            return
        self._is_running = False
        asyncio.ensure_future(self._shutdown(), loop=self.loop)

    async def _shutdown(self):
        log.info("Shutdown now")
        if self._futures:
            for f in self._futures:
                f.cancel()
            self._futures = None
        await asyncio.sleep(0.001, loop=self.loop)
        self.loop.remove_signal_handler(signal.SIGINT)
        self.loop.remove_signal_handler(signal.SIGTERM)
        self.loop.stop()
        self._recover_configuration()

    async def _maintain_squid_task(self):
        update_interval = self._config.getfloat('update_interval')
        while True:
            await self._maintain_squid()
            await asyncio.sleep(update_interval, loop=self.loop)

    async def _maintain_squid(self):
        data = []
        proxies = set()
        timeout = self._config.getfloat('timeout')
        try:
            for url in self._request_urls:
                async with aiohttp.ClientSession(loop=self.loop) as session:
                    with async_timeout.timeout(timeout, loop=self.loop):
                        log.debug('Request url: %s', url)
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
        min_anonymity = self._config.getint('min_anonymity')
        squid = self._config.get('squid')
        lines = [self._template, '\n# cache_peer configuration\n']
        for p in proxies:
            host, port = p['address'].split(':')
            name = host + '.' + port
            lines.append(self.PEER_CONF.format(host, port, name))
            dl = []
            if p['anonymity'] < min_anonymity:
                dl.append('!SSL_ports')
            if not p['https']:
                dl.append('SSL_ports')
            if not p['post']:
                dl.append('POST')
            if len(dl) > 0:
                lines.append(self.PEER_ACCESS_CONF.format(name, 'deny', ' '.join(dl)))

        with open(self._dest_file, 'w') as f:
            f.writelines(lines)
        log.info('Reconfigure squid with %s proxies, conf=%s', len(proxies), self._dest_file)
        try:
            if os.system('{} -k reconfigure'.format(squid)) != 0:
                raise RuntimeError
        except RuntimeError:
            self._recover_configuration()
            raise

    def _recover_configuration(self):
        with open(self._dest_file, 'w') as f:
            f.write(self._template)


class AddressSetting(Setting):
    name = 'address'
    cli = ['-a', '--address']
    metavar = 'ADDRESS'
    default = 'localhost:6256'
    short_desc = 'the address of freehp'


class SquidSetting(Setting):
    name = 'squid'
    cli = ['--squid']
    metavar = 'NAME'
    default = 'squid3'
    short_desc = 'the name of squid command'


class MaxNumSetting(Setting):
    name = 'max_num'
    cli = ['--max-num']
    metavar = 'INT'
    default = 0
    short_desc = 'maximal number of proxies to preserve the quality of proxies, 0 for unlimited'


class HttpsSetting(Setting):
    name = 'https'
    cli = ['--https']
    action = 'store_true'
    default = False
    short_desc = 'configure a list of proxies which support for HTTPS'


class PostSetting(Setting):
    name = 'post'
    cli = ['--post']
    action = 'store_true'
    default = False
    short_desc = 'configure a list of proxies which support for POST'


class UpdateIntervalSetting(Setting):
    name = 'update_interval'
    cli = ['--update-interval']
    metavar = 'SECONDS'
    type = float
    default = 60
    short_desc = 'update interval in seconds'


class TimeoutSetting(Setting):
    name = 'timeout'
    cli = ['--timeout']
    metavar = 'SECONDS'
    type = float
    default = 30
    short_desc = 'timeout in seconds'


class OnceSetting(Setting):
    name = 'once'
    cli = ['--once']
    action = 'store_true'
    default = False
    short_desc = 'run only once'


KNOWN_SETTINGS = {}

for _v in list(vars().values()):
    if inspect.isclass(_v) and issubclass(_v, Setting) and _v.name is not None:
        KNOWN_SETTINGS[_v.name] = _v()


class SquidConfig(Config):
    def __init__(self, values=None):
        super().__init__()
        for v in KNOWN_SETTINGS.values():
            self.set(v.name, v.value)
        self.update(values)
