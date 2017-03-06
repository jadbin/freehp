# coding=utf-8


import freehp
from freehp.commands import Command


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
        print("freehp version {0}".format(freehp.__version__))
