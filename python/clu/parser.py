#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-06
# @Filename: parser.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import functools
import inspect
import json
import re

import click
from click.decorators import group, pass_obj

from . import actor


__all__ = ['CluCommand', 'CluGroup', 'command_parser', 'ClickParser', 'timeout']


def coroutine(fn):
    """Create a coroutine. Avoids deprecation of asyncio.coroutine in 3.10."""

    if inspect.iscoroutinefunction(fn):
        return fn

    @functools.wraps(fn)
    async def _wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return _wrapper


class CluCommand(click.Command):
    """Override :py:class:`click.Command` to pass the actor and command."""

    def __init__(self, *args, context_settings=None, **kwargs):

        # Unless told otherwise, set ignore_unknown_options=True to prevent
        # negative numbers to be considered as options. See #40.
        if (context_settings is None or
                'ignore_unknown_options' not in context_settings):
            context_settings = context_settings or {}
            context_settings['ignore_unknown_options'] = True

        super().__init__(*args, context_settings=context_settings, **kwargs)

    def done_callback(self, task, exception_handler=None):
        """Checks if the command task has been successfully done."""

        ctx = task.ctx

        command = ctx.obj['parser_args'][0]

        if exception_handler and task.exception():
            exception_handler(command, task.exception())

    async def _schedule_callback(self, ctx, timeout=None):
        """Schedules the callback as a task with a timeout."""

        parser_args = ctx.obj.get('parser_args', [])
        command = parser_args[0] if len(parser_args) > 0 else None

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
        """As :py:class:`click.Command.invoke` but passes the actor and command."""

        click.core._maybe_show_deprecated_notice(self)

        if self.callback is not None:

            with ctx:

                loop = asyncio.get_event_loop()

                # Makes sure the callback is a coroutine
                if not asyncio.iscoroutinefunction(self.callback):
                    self.callback = coroutine(self.callback)

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
    """Override :py:class:`click.Group`.

    Makes all child commands instances of `.CluCommand`.

    """

    def command(self, *args, **kwargs):
        """Override :py:class:`click.Group` to use `.CluCommand` by default."""

        if 'cls' in kwargs:
            pass
        else:
            kwargs['cls'] = CluCommand

        def decorator(f):
            cmd = click.decorators.command(*args, **kwargs)(f)
            self.add_command(cmd)
            return cmd

        return decorator

    def parse_args(self, ctx, args):  # pragma: no cover

        # Copy this method so that we can turn off the printing of the
        # usage before ctx.exit()
        if not args and self.no_args_is_help and not ctx.resilient_parsing:
            ctx.exit()

        rest = click.Command.parse_args(self, ctx, args)
        if self.chain:
            ctx.protected_args = rest
            ctx.args = []
        elif rest:
            ctx.protected_args, ctx.args = rest[:1], rest[1:]

        return ctx.args

    def group(self, *args, **kwargs):
        """Creates a new group inheriting from this class."""

        if 'cls' not in kwargs:
            kwargs['cls'] = self.__class__

        def decorator(f):
            assert not asyncio.iscoroutinefunction(f), 'groups cannot be coroutines.'
            cmd = group(*args, **kwargs)(f)
            self.add_command(cmd)
            return cmd

        return decorator


def timeout(seconds):
    """A decorator to timeout the command after a number of ``seconds``."""

    def decorator(f):

        # This is a bit of a hack but we cannot access the context here so
        # we add the timeout directly to the callback function.
        f.timeout = seconds

        async def helper(f, *args, **kwargs):
            if asyncio.iscoroutinefunction(f):
                return await f(*args, **kwargs)
            else:
                return f(*args, **kwargs)

        @functools.wraps(f)
        async def wrapper(*args, **kwargs):
            return await helper(f, *args, **kwargs)

        return functools.update_wrapper(wrapper, f)

    return decorator


def pass_args():
    """Thing wrapper around pass_obj to pass the command and parser_args."""

    def decorator(f):
        @functools.wraps(f)
        @pass_obj
        def new_func(obj, *args, **kwargs):
            return f(*obj['parser_args'], *args, **kwargs)
        return functools.update_wrapper(new_func, f)

    return decorator


@click.group(cls=CluGroup)
def command_parser(*args):
    pass


@command_parser.command()
def ping(*args):
    """Pings the actor."""

    command = args[0]
    command.set_status(command.status.DONE, 'Pong.')

    return


@command_parser.command()
def version(*args):
    """Reports the version."""

    command = args[0]
    command.set_status(command.status.DONE,
                       version=command.actor.version)

    return


@command_parser.command(cls=CluCommand, name='get_schema')
def get_schema(*args):
    """Returns the schema of the actor as a JSON schema."""

    command = args[0]

    if command.actor.schema is None:
        return command.fail(text='The actor does not know its own schema.')

    return command.finish(schema=json.dumps(command.actor.schema.schema))


@command_parser.command(name='help')
@click.argument('PARSER-COMMAND', type=str, required=False)
@click.pass_context
def help_(ctx, *args, parser_command):
    """Shows the help."""

    command = args[0]

    # The parser_command arrives wrapped in quotes to make sure is a single
    # value. Strip it and unpack it in as many groups and commands as needed.
    parser_command = parser_command.strip('"').split()

    help_lines = ''
    command_name = args[0].actor.name  # Actor name

    # Gets the help lines for the command group or for a specific command.
    if len(parser_command) > 0:

        ctx_commands = ctx.command.commands

        for ii in range(len(parser_command)):
            ctx_command_name = parser_command[ii].lower()
            command_name += f' {ctx_command_name}'
            if ctx_command_name not in ctx_commands:
                return command.fail(text=f'command {ctx_command_name} not found.')
            ctx_command = ctx_commands[ctx_command_name]
            if ii == len(parser_command) - 1:
                # This is the last element in the command list
                # so we want to actually output this help lines.
                help_lines = ctx_command.get_help(ctx)
            else:
                ctx_commands = ctx_command.commands

    else:

        help_lines = ctx.get_help()

    message = []
    for line in help_lines.splitlines():
        # Remove the parser name.
        match = re.match(r'^Usage: ([A-Za-z-_]+)', line)
        if match:
            line = line.replace(match.groups()[0], command_name)

        message.append(line)

    if isinstance(command.actor, (actor.AMQPActor, actor.JSONActor)):
        return command.finish(help=message)
    else:
        for line in message:
            command.warning(help=line)
        return command.finish()


class ClickParser:
    """A command parser that uses Click at its base."""

    #: list: Arguments to be passed to each command in the parser.
    #: Note that the command is always passed first.
    parser_args = []

    parser = command_parser

    def parse_command(self, command):
        """Parses an user command using the Click internals."""

        # This will pass the command as the first argument for each command.
        # If self.parser_args is defined, those arguments will be passed next.
        parser_args = [command]
        parser_args += self.parser_args

        # Empty command. Just finish the command.
        if not command.body:
            command.done()
            return command

        command.set_status(command.status.RUNNING)

        # If the command contains the --help flag,
        # redirects it to the help command.
        if '--help' in command.body:
            command.body = 'help ' + command.body
            command.body = command.body.replace(' --help', '')

        if not command.body.startswith('help'):
            command_args = command.body.split()
        else:
            command_args = ['help', '"{}"'.format(command.body[5:])]

        # We call the command with a custom context to get around
        # the default handling of exceptions in Click. This will force
        # exceptions to be raised instead of redirected to the stdout.
        # See http://click.palletsprojects.com/en/7.x/exceptions/
        ctx = self.parser.make_context(
            f'{self.name}-command-parser', command_args,
            obj={'parser_args': parser_args,
                 'log': self.log,
                 'exception_handler': self._handle_command_exception})

        # Makes sure this is the global context. This solves problems when
        # the actor have been started from inside an existing context,
        # for example when it's called from a CLI click application.
        click.globals.push_context(ctx)

        # Sets the context in the command.
        command.ctx = ctx

        with ctx:
            try:
                self.parser.invoke(ctx)
            except Exception as exc:
                self._handle_command_exception(command, exc)

        return command

    def _handle_command_exception(self, command, exception):
        """Handles an exception during parsing or execution of a command."""

        try:

            raise exception

        except (click.ClickException, click.exceptions.Exit) as ee:

            if not hasattr(ee, 'message'):
                ee.message = None

            ctx = command.ctx
            message = ''

            # If this is a command that cannot be parsed.
            if ee.message is None and ctx:
                message = f'{ee.__class__.__name__}:\n{ctx.get_help()}'
            else:
                message = f'{ee.__class__.__name__}: {ee.message}'

            if isinstance(command.actor, (actor.AMQPActor, actor.JSONActor)):
                command.warning(help=message.splitlines())
            else:
                lines = message.splitlines()
                for line in lines:
                    command.warning(help=line)

            msg = f'Command {command.body!r} failed.'

            if not command.status.is_done:
                command.fail(text=msg)
            else:
                command.write('e', text=msg)

        except click.exceptions.Abort:

            if not command.status.is_done:
                command.fail(text=f'Command {command.body!r} was aborted.')

        except Exception as err:

            msg = (f'Command {command.body!r} failed because of an uncaught '
                   f'error \'{err.__class__.__name__}: {str(err)}\'. See '
                   f'traceback in the log for more information.')

            if command.status.is_done:
                command.write(text=msg)
            else:
                command.fail(text=msg)

            log = self.log or command.ctx.obj.get('log', None)
            if log:
                log.exception(f'Command {command.body!r} failed with error:')
