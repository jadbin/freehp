# coding=utf-8

import logging
from os.path import abspath, isfile

from freehp.errors import UsageError
from freehp import utils
from freehp.version import __version__
from freehp.manager import ProxyManager
from freehp import defaultconfig
from freehp import config
from freehp import squid

log = logging.getLogger(__name__)


class Command:
    def __init__(self):
        self.config = config.Config()
        self.exitcode = 0

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
        pass

    def process_arguments(self, args):
        pass

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

    def add_arguments(self, parser):
        parser.add_argument('-c', '--config', metavar='FILE', help='configuration file')
        parser.add_argument('-b', '--bind', dest='bind', metavar='ADDRESS', default=defaultconfig.bind,
                            help='the socket to bind')
        parser.add_argument('-d', '--daemon', dest='daemon', action='store_true', default=defaultconfig.daemon,
                            help='run in daemon mode')
        parser.add_argument("-l", "--log-level", dest="log_level", metavar="LEVEL", default=defaultconfig.log_level,
                            help="log level")
        parser.add_argument("--log-file", dest="log_file", metavar="FILE", default=defaultconfig.log_file,
                            help="log file")
        parser.add_argument("-s", "--set", dest="set", action="append", default=[], metavar="NAME=VALUE",
                            help="set/override setting (may be repeated)")

    def process_arguments(self, args):
        if args.config:
            if isfile(args.config):
                for k, v in utils.load_config(args.config).items():
                    self.config.set(k, v)
            else:
                self.exitcode = 1
                print("Error: Cannot find '{}'".format(abspath(args.config)))
                return
        if args.bind:
            self.config.set('bind', args.bind)
        if args.daemon:
            self.config.set('daemon', True)
        if args.log_level:
            self.config.set("log_level", args.log_level)
        if args.log_file:
            self.config.set('log_file', args.log_file)
        try:
            self.config.update(dict(x.split("=", 1) for x in args.set))
        except ValueError:
            raise UsageError("Invalid -s value, use -s NAME=VALUE", print_help=False)

    def run(self, args):
        if self.config.getbool('daemon'):
            utils.be_daemon()
        utils.configure_logging('freehp', self.config)
        agent = ProxyManager(self.config)
        agent.start()


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
        parser.add_argument('--max-num', dest='max_num', type=int, metavar='NUM', default=squid.DEFAULT_MAX_NUM,
                            help='max number of proxies, 0 for unlimited')
        parser.add_argument('--update-interval', dest='update_interval', type=int, metavar='SECONDS',
                            default=squid.DEFAULT_UPDATE_INTERVAL, help='update interval in seconds')
        parser.add_argument('--timeout', dest='timeout', type=int, metavar='SECONDS', default=squid.DEFAULT_TIMEOUT,
                            help='timeout in seconds')
        parser.add_argument('--once', dest='once', action='store_true', default=False,
                            help='run only once')
        parser.add_argument("-l", "--log-level", dest="log_level", metavar="LEVEL", default=defaultconfig.log_level,
                            help="log level")
        parser.add_argument("--log-file", dest="log_file", metavar="FILE", default=defaultconfig.log_file,
                            help="log file")

    def process_arguments(self, args):
        args.dest_file = args.dest_file[0]
        if not args.template:
            if not isfile(args.dest_file):
                raise UsageError('The template of squid configuration is not specified', print_help=False)
            args.template = args.dest_file
        if args.log_level:
            self.config.set("log_level", args.log_level)
        if args.log_file:
            self.config.set('log_file', args.log_file)

    def run(self, args):
        if config.getbool(args.daemon):
            utils.be_daemon()
        utils.configure_logging('freehp', self.config)
        s = squid.Squid(args.dest_file, args.template, freehp_address=args.address, max_num=args.max_num,
                        update_interval=args.update_interval, timeout=args.timeout, once=args.once)
        s.start()


class VersionCommand(Command):
    @property
    def name(self):
        return "version"

    @property
    def short_desc(self):
        return "Print the version"

    def run(self, args):
        print("freehp version {0}".format(__version__))
