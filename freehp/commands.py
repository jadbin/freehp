# coding=utf-8

import logging
from os.path import isfile

from freehp.errors import UsageError
from freehp import utils
from freehp.version import __version__
from freehp.manager import ProxyManager
from freehp import config
from freehp import squid

log = logging.getLogger(__name__)


class Command:
    def __init__(self):
        self.config = config.BaseConfig()
        self.exitcode = 0
        self.settings = self._import_settings()

    def _import_settings(self):
        return []

    @property
    def name(self):
        return ""

    @property
    def syntax(self):
        return ""

    @property
    def short_desc(self):
        return ""

    @property
    def long_desc(self):
        return self.short_desc

    def add_arguments(self, parser):
        for s in self.settings:
            s.add_argument(parser)

    def process_arguments(self, args):
        for s in self.settings:
            v = getattr(args, s.name)
            if v is not None:
                self.config.set(s.name, v)

    def run(self, args):
        raise NotImplementedError


class RunCommand(Command):
    @property
    def name(self):
        return "run"

    @property
    def syntax(self):
        return "[OPTIONS]"

    @property
    def short_desc(self):
        return "Run spider to scrap free HTTP proxies"

    def _import_settings(self):
        settings = (config.Bind, config.Daemon, config.PidFile,
                    config.LogLevel, config.LogFile,
                    config.MinAnonymity, config.CheckerTimeout)
        return [config.KNOWN_SETTINGS[i.name] for i in settings]

    def add_arguments(self, parser):
        parser.add_argument('-c', '--config', dest='config', metavar='FILE',
                            help='configuration file')
        super().add_arguments(parser)
        parser.add_argument("-s", "--set", dest="set", action="append", default=[], metavar="NAME=VALUE",
                            help="set/override setting (can be repeated)")

    def process_arguments(self, args):
        if args.config is not None:
            try:
                c = utils.load_config(args.config)
            except Exception:
                raise RuntimeError('Cannot read the configuration file {}'.format(args.config))
            for k, v in utils.iter_settings(c):
                self.config.set(k, v)
        super().process_arguments(args)
        try:
            self.config.update(dict(x.split("=", 1) for x in args.set))
        except ValueError:
            raise UsageError("Invalid -s value, use -s NAME=VALUE")

    def run(self, args):
        cfg = config.Config()
        cfg.update(self.config)
        if cfg.getbool('daemon'):
            utils.be_daemon()
        utils.configure_logging('freehp', cfg)
        try:
            agent = ProxyManager(cfg)
            agent.start()
        except Exception as e:
            log.error(e, exc_info=True)


class SquidCommand(Command):
    @property
    def name(self):
        return "squid"

    @property
    def syntax(self):
        return "[OPTIONS] <DEST_FILE>"

    @property
    def short_desc(self):
        return "Append proxies to the configuration of squid"

    def _import_settings(self):
        settings = (config.LogLevel, config.LogFile)
        return [config.KNOWN_SETTINGS[i.name] for i in settings]

    def add_arguments(self, parser):
        parser.add_argument('dest_file', metavar='DEST_FILE', nargs=1,
                            help='where the squid configuration file is')
        parser.add_argument('-a', '--address', dest='address', metavar='ADDRESS', default=squid.DEFAULT_FREEHP_ADDRESS,
                            help='the address of freehp')
        parser.add_argument('--template', dest='template', metavar='FILE',
                            help='the template of squid configuration, default is <DEST_FILE>')
        parser.add_argument('--squid', dest='squid', metavar='squid', default=squid.DEFAULT_SQUID,
                            help='the name of squid command')
        parser.add_argument('-d', '--daemon', dest='daemon', action='store_true', default=False,
                            help='run in daemon mode')
        parser.add_argument('--min-anonymity', dest='min_anonymity', type=int, metavar='ANONYMITY',
                            default=squid.DEFAULT_MIN_ANONYMITY,
                            help='minimum anonymity level, 0: transparent, 1: anonymous, 2: elite proxy')
        parser.add_argument('--max-num', dest='max_num', type=int, metavar='NUM', default=squid.DEFAULT_MAX_NUM,
                            help='maximal number of proxies to preserve the quality of proxies, 0 for unlimited')
        parser.add_argument('--https', dest='https', action='store_true', default=squid.DEFAULT_HTTPS,
                            help='configure a list of proxies which support for HTTPS')
        parser.add_argument('--post', dest='post', action='store_true', default=squid.DEFAULT_POST,
                            help='configure a list of proxies which support for POST')
        parser.add_argument('--update-interval', dest='update_interval', type=float, metavar='SECONDS',
                            default=squid.DEFAULT_UPDATE_INTERVAL, help='update interval in seconds')
        parser.add_argument('--timeout', dest='timeout', type=float, metavar='SECONDS', default=squid.DEFAULT_TIMEOUT,
                            help='timeout in seconds')
        parser.add_argument('--once', dest='once', action='store_true', default=False,
                            help='run only once')
        super().add_arguments(parser)

    def process_arguments(self, args):
        args.dest_file = args.dest_file[0]
        if not args.template:
            if not isfile(args.dest_file):
                raise UsageError('The template of squid configuration is not specified')
            args.template = args.dest_file

    def run(self, args):
        if config.getbool(args.daemon):
            utils.be_daemon()
        utils.configure_logging('freehp', self.config)
        try:
            s = squid.Squid(args.dest_file, args.template, address=args.address, max_num=args.max_num,
                            min_anonymity=args.min_anonymity, https=args.https, post=args.post,
                            update_interval=args.update_interval, timeout=args.timeout, once=args.once)
            s.start()
        except Exception as e:
            log.error(e, exc_info=True)


class VersionCommand(Command):
    @property
    def name(self):
        return "version"

    @property
    def short_desc(self):
        return "Print the version"

    def run(self, args):
        print("freehp version {0}".format(__version__))
