# coding=utf-8

import sys
import argparse
import inspect

from freehp.errors import UsageError
from freehp.utils.project import walk_modules
from freehp.commands import Command


def _iter_command_classes():
    for module in walk_modules("freehp.commands"):
        for obj in vars(module).values():
            if inspect.isclass(obj) and issubclass(obj, Command) and obj.__module__ == module.__name__:
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
    parser = argparse.ArgumentParser()
    parser.usage = "freehp {} {}".format(cmdname, cmd.syntax)
    parser.description = cmd.long_desc
    cmd.add_arguments(parser)
    args = parser.parse_args(args=argv[1:])
    cmd.process_arguments(args)
    try:
        cmd.run(args)
    except UsageError as e:
        if str(e):
            parser.error(str(e))
        if e.print_help:
            parser.print_help()
        sys.exit(2)
    else:
        if cmd.exitcode:
            sys.exit(cmd.exitcode)
