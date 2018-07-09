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
        self.settings = self._make_settings()

    def _import_settings(self):
        pass

    def _make_settings(self):
        settings = []
        classes = self._import_settings()
        if classes is not None:
            for cls in classes:
                if issubclass(cls, config.Setting):
                    settings.append(cls())
        return settings

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
        return (config.Bind, config.Daemon, config.PidFile,
                config.LogLevel, config.LogFile,
                config.MinAnonymity, config.CheckerTimeout)

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
        return (squid.AddressSetting, squid.SquidSetting,
                config.Daemon, config.MinAnonymity,
                squid.MaxNumSetting, squid.HttpsSetting, squid.PostSetting,
                squid.UpdateIntervalSetting, squid.TimeoutSetting, squid.OnceSetting,
                config.LogLevel, config.LogFile)

    def add_arguments(self, parser):
        parser.add_argument('dest_file', metavar='FILE', nargs=1,
                            help='where the squid configuration file is')
        parser.add_argument('-t', '--template', dest='template', metavar='FILE',
                            help='the template of squid configuration, default is the configuration file')
        super().add_arguments(parser)

    def process_arguments(self, args):
        args.dest_file = args.dest_file[0]
        if not args.template:
            if not isfile(args.dest_file):
                raise UsageError('The template of squid configuration is not specified')
            args.template = args.dest_file
        super().process_arguments(args)

    def run(self, args):
        cfg = squid.SquidConfig()
        cfg.update(self.config)
        if cfg.getbool('daemon'):
            utils.be_daemon()
        utils.configure_logging('freehp', cfg)
        try:
            s = squid.Squid(args.dest_file, args.template, config=cfg)
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
