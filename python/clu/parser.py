#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-06
# @Filename: parser.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-20 14:58:45

import asyncio
import functools
import re

import click


class CluCommand(click.Command):
    """Override `click.Command` to pass the actor and command as arguments."""

    async def _schedule_callback(self, ctx, timeout=None):
        """Schedules the callback as a task."""

        if not hasattr(ctx, 'obj') or 'parser_args' not in ctx.obj:
            parser_args = []
            command = None
        else:
            parser_args = ctx.obj['parser_args']
            command = parser_args[0]

        callback_task = asyncio.create_task(
            ctx.invoke(self.callback, *parser_args, **ctx.params))

        try:
            await asyncio.wait_for(callback_task, timeout=timeout)
        except asyncio.TimeoutError:
            if command:
                command.set_status(command.status.TIMEDOUT,
                                   f'command timed out after {timeout} seconds.')
            return False

        return True

    def invoke(self, ctx):
        """Same as `click.Command.invoke` but passes the actor and command."""

        click.core._maybe_show_deprecated_notice(self)

        if self.callback is not None:
            with ctx:
                # Makes sure the callback is a coroutine
                if not asyncio.iscoroutinefunction(self.callback):
                    self.callback = asyncio.coroutine(self.callback)

                # Check to see if there is a timeout value in the callback.
                # If so, schedules a task to be cancelled after timeout.
                timeout = getattr(self.callback, 'timeout', None)

                loop = asyncio.get_event_loop()
                ctx.task = loop.create_task(self._schedule_callback(ctx, timeout=timeout))

            return ctx


class CluGroup(click.Group):
    """Override `click.Group` to make all child commands instances of `.ClickCommand`."""

    def command(self, *args, **kwargs):
        """Override `click.Group` to use `Command` as class by default."""

        if 'cls' in kwargs:
            pass
        else:
            kwargs['cls'] = CluCommand

        def decorator(f):
            cmd = click.decorators.command(*args, **kwargs)(f)
            self.add_command(cmd)
            return cmd

        return decorator


def timeout(seconds):
    """A decorator to timeout the command after a number of ``seconds``."""

    def decorator(f):

        # This is a bit of a hack but we cannot access the context here so
        # we add the timeout directly to the callback function.
        f.timeout = seconds

        @functools.wraps(f)
        def new_func(*args, **kwargs):
            return f(*args, **kwargs)
        return functools.update_wrapper(new_func, f)

    return decorator


@click.group(cls=CluGroup)
def command_parser():
    pass


@command_parser.command()
def ping(*args):
    """Pings the actor."""

    command = args[0]
    command.set_status(command.status.DONE, 'Pong.')

    return


@command_parser.command()
@click.pass_context
def help(ctx, *args):
    """Shows the help."""

    command = args[0]

    for line in ctx.get_help().splitlines():
        # Remove the parser name.
        match = re.match(r'^Usage:([A-Za-z-\ ]+? \[OPTIONS\]) .*', line)
        if match:
            line = line.replace(match.groups()[0], '')

        command.write('w', {'text': line})

    return
