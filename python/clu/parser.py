#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-06
# @Filename: parser.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-23 12:37:47

import asyncio
import functools
import re

import click


class CluCommand(click.Command):
    """Override `click.Command` to pass the actor and command as arguments."""

    def done_callback(self, task, exception_handler=None):
        """Checks if the command task has been successfully done."""

        log = getattr(task, 'log', None)
        ctx = task.ctx

        command = ctx.obj['parser_args'][0]

        if exception_handler and task.exception():
            exception_handler(command, task.exception(), log=log)

    async def _schedule_callback(self, ctx, timeout=None):
        """Schedules the callback as a task with a timeout."""

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

                loop = asyncio.get_event_loop()

                # Makes sure the callback is a coroutine
                if not asyncio.iscoroutinefunction(self.callback):
                    self.callback = asyncio.coroutine(self.callback)

                # Check to see if there is a timeout value in the callback.
                # If so, schedules a task to be cancelled after timeout.
                timeout = getattr(self.callback, 'timeout', None)

                log = ctx.obj.pop('log', None)

                # Defines the done callback function.
                exception_handler = ctx.obj.pop('exception_handler', None)
                done_callback = functools.partial(self.done_callback,
                                                  exception_handler=exception_handler)

                # Launches callback scheduler and adds the done callback
                ctx.task = loop.create_task(self._schedule_callback(ctx, timeout=timeout))
                ctx.task.add_done_callback(done_callback)

                # Add some attributes to the task because it's
                # what will be passed to done_callback
                ctx.task.ctx = ctx
                ctx.task.log = log

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
@click.argument('PARSER-COMMAND', type=str, required=False)
@click.pass_context
def help(ctx, *args, parser_command):
    """Shows the help."""

    command = args[0]

    # Gets the help lines for the command group or for a specific command.
    if parser_command and parser_command.lower() != 'help':
        help_lines = ctx.command.commands[parser_command.lower()].get_help(ctx)
    else:
        help_lines = ctx.get_help()

    for line in help_lines.splitlines():
        # Remove the parser name.
        match = re.match(r'^Usage:([A-Za-z-\ ]+? \[OPTIONS\]) .*', line)
        if match:
            line = line.replace(match.groups()[0], '')

        command.write('w', {'text': line})

    return
