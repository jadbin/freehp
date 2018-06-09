# coding=utf-8

import logging
from os.path import abspath, isfile

from freehp.config import Config
from freehp.errors import UsageError
from freehp.utils import load_config, configure_logging
from freehp.version import __version__
from freehp.manager import ProxyManager

log = logging.getLogger(__name__)


class Command:
    def __init__(self):
        self.config = Config()
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
        parser.add_argument("-s", "--set", dest="set", action="append", default=[], metavar="NAME=VALUE",
                            help="set/override setting (may be repeated)")
        parser.add_argument("-l", "--log-level", dest="log_level", metavar="LEVEL",
                            help="log level")

    def process_arguments(self, args):
        # setting
        try:
            self.config.update(dict(x.split("=", 1) for x in args.set), priority="cmdline")
        except ValueError:
            raise UsageError("Invalid -s value, use -s NAME=VALUE", print_help=False)

        # logger
        if args.log_level:
            self.config.set("log_level", args.log_level, priority="cmdline")

    def run(self, args):
        raise NotImplementedError


class RunCommand(Command):
    @property
    def syntax(self):
        return "[config]"

    @property
    def name(self):
        return "run"

    @property
    def short_desc(self):
        return "Run spider to scrap free HTTP proxies"

    def add_arguments(self, parser):
        Command.add_arguments(self, parser)

        parser.add_argument("config", metavar="config", nargs="?", help="configuration file")

    def process_arguments(self, args):
        Command.process_arguments(self, args)

    def run(self, args):
        if args.config:
            if isfile(args.config):
                for k, v in load_config(args.config).items():
                    self.config.set(k, v, priority="project")
            else:
                self.exitcode = 1
                print("Error: Cannot find '{}'".format(abspath(args.config)))
                return
        configure_logging('freehp', self.config)
        agent = ProxyManager(self.config)
        agent.start()


class VersionCommand(Command):
    @property
    def name(self):
        return "version"

    @property
    def short_desc(self):
        return "Print the version"

    def add_arguments(self, parser):
        Command.add_arguments(self, parser)

    def run(self, args):
        print("freehp version {0}".format(__version__))
