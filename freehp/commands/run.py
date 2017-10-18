# coding=utf-8

from os.path import isfile, abspath
import logging.config

from freehp.commands import Command
from freehp.utils.log import configure_logging
from freehp.utils.config import load_config_file
from freehp.agent import ProxyAgent

log = logging.getLogger(__name__)


class RunCommand(Command):
    @property
    def syntax(self):
        return "[config_file]"

    @property
    def name(self):
        return "run"

    @property
    def short_desc(self):
        return "Run spider to scrap free HTTP proxies"

    def add_arguments(self, parser):
        Command.add_arguments(self, parser)

        parser.add_argument("config_file", metavar="config_file", nargs="?", help="configuration file")

    def process_arguments(self, args):
        Command.process_arguments(self, args)

    def run(self, args):
        if args.config_file:
            if isfile(args.config_file):
                for k, v in load_config_file(args.config_file).items():
                    self.config.set(k, v, priority="project")
            else:
                self.exitcode = 1
                print("Error: Connot find '{}'".format(abspath(args.config_file)))
                return

        configure_logging(self.config)

        agent = ProxyAgent(self.config)
        agent.start()
