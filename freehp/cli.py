# coding=utf-8

import sys
import argparse

from freehp.errors import UsageError
from freehp import commands
from freehp.commands import Command


def _iter_command_classes():
    for obj in vars(commands).values():
        if isinstance(obj, type) and issubclass(obj, Command) and obj is not Command:
            yield obj


def _get_commands_from_module():
    d = {}
    for cmd in _iter_command_classes():
        o = cmd()
        if o.name:
            d[o.name] = o
    return d


def _print_commands():
    print("usage: freehp <command> [options] [args]\n")
    print("available commands:")
    cmds = _get_commands_from_module()
    for cmdname, cmdclass in sorted(cmds.items()):
        print("  {:<10} {}".format(cmdname, cmdclass.short_desc))
    print()
    print('Use "freehp <command> -h" to see more info about a command')


def _print_unknown_command(cmdname):
    print("Unknown command: %s\n" % cmdname)
    print('Use "freehp" to see available commands')


def main(argv=None):
    if argv is None:
        argv = sys.argv
    cmds = _get_commands_from_module()
    cmdname = argv[1] if len(argv) > 1 else None
    if not cmdname:
        _print_commands()
        sys.exit(0)
    elif cmdname not in cmds:
        _print_unknown_command(cmdname)
        sys.exit(2)
    del argv[1]
    cmd = cmds[cmdname]
    parser = argparse.ArgumentParser(usage="freehp {} {}".format(cmdname, cmd.syntax),
                                     description=cmd.long_desc)
    cmd.add_arguments(parser)
    try:
        args = parser.parse_args(args=argv[1:])
        cmd.process_arguments(args)
        cmd.run(args)
    except UsageError as e:
        parser.error(str(e))
    else:
        if cmd.exitcode:
            sys.exit(cmd.exitcode)
