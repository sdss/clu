#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-06
# @Filename: parser.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-06 23:27:42

import click


class Command(click.Command):
    """Override `click.Command` to pass the actor and command as arguments."""

    def invoke(self, ctx):
        """Same as `click.Command.invoke` but passes the actor and command."""

        click.core._maybe_show_deprecated_notice(self)

        if self.callback is not None:
            with ctx:
                ctx.invoke(self.callback, ctx.obj['command'], **ctx.params)
            return ctx


class Group(click.Group):
    """Override `click.Group` to make all child commands instances of `Command`."""

    def command(self, *args, **kwargs):
        """Override `click.Group` to use `Command` as class by default."""

        if 'cls' in kwargs:
            pass
        else:
            kwargs['cls'] = Command

        def decorator(f):
            cmd = click.decorators.command(*args, **kwargs)(f)
            self.add_command(cmd)
            return cmd

        return decorator


@click.group(cls=Group)
@click.pass_context
def command_parser(ctx):
    pass


@command_parser.command()
def ping(command):
    """Pings the actor."""

    command.set_status(command.status.DONE, 'Pong.')

    return


@command_parser.command()
@click.pass_context
def help(ctx, command):
    """Shows the help."""

    for line in ctx.parent.get_help().splitlines():
        # line = json.dumps(line).replace(';', '')
        command.write('w', {'text': line})

    return
