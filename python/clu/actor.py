#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-16
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import abc
import asyncio
import json
import time
from contextlib import suppress

import click

from .base import log_reply
from .client import AMQPClient, BaseClient
from .command import Command
from .exceptions import CommandError
from .model import ModelSet


try:
    import aio_pika as apika
except ImportError:
    apika = None


__all__ = ['BaseActor', 'Actor']


class BaseActor(BaseClient):
    """An actor based on `asyncio <https://docs.python.org/3/library/asyncio.html>`__.

    This class expands `.BaseClient` with a parsing system for new commands
    and placeholders for methods for handling new commands and writing replies,
    which should be overridden by the specific actors.

    """

    #: list: Arguments to be passed to each command in the parser.
    #: Note that the command is always passed first.
    parser_args = []

    @abc.abstractmethod
    async def start(self):
        """Starts the server. Must be overridden by the subclasses."""

        pass

    @abc.abstractmethod
    def new_command(self):
        """Handles a new command.

        Must be overridden by the subclass and call `.parse_command`
        with a `.Command` object.

        """

        pass

    def parse_command(self, command):
        """Parses an user command with the default, Click-based parser.

        This method can be overridden to use a custom parser.

        """

        # This will pass the command as the first argument for each command.
        # If self.parser_args is defined, those arguments will be passed next.
        parser_args = [command]
        parser_args += self.parser_args

        # Empty command. Just finish the command.
        if not command.body:
            command.done()
            return command

        command.set_status(command.status.RUNNING)

        # If the command contains the --help flag, redirects it to the help command.
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
        ctx = self.command_parser.make_context(
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
                self.command_parser.invoke(ctx)
            except Exception as exc:
                self._handle_command_exception(command, exc)

        return

    @staticmethod
    def _handle_command_exception(command, exception, log=None):
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

            lines = message.splitlines()
            for line in lines:
                command.write('w', text=line)

            msg = f'Command {command.body!r} failed.'

            if not command.status.is_done:
                command.failed(text=msg)
            else:
                command.write(text=msg)

        except click.exceptions.Exit:

            # This happens when using --help, although it should be handled
            # in parse_command.
            if command.status.is_done:
                command.write(text=f'Use help [CMD]')
            else:
                command.failed(text=f'Use help [CMD]')

        except click.exceptions.Abort:

            if not command.status.is_done:
                command.failed(text='Command was aborted.')

        except Exception:

            msg = (f'Command {command.command_id} failed because of an uncaught error. '
                   'See traceback in the log for more information.')

            if command.status.is_done:
                command.write(text=msg)
            else:
                command.failed(text=msg)

            log = log or getattr(command.ctx, 'log', None)
            if log:
                log.exception(f'Command {command.body!r} failed with error:')

    @abc.abstractmethod
    def send_command(self):
        """Sends a command to another actor. Must be overridden."""

        pass

    @abc.abstractmethod
    def write(self):
        """Writes a message to user(s). To be overridden by the subclasses."""

        pass


class Actor(AMQPClient, BaseActor):
    """An actor class that uses AMQP message brokering.

    This class differs from `~clu.legacy.actor.LegacyActor` in that it uses
    an AMQP messaging broker (typically RabbitMQ) to communicate with other
    actors in the system, instead of standard TCP sockets. Although the
    internals and protocols are different the entry points and behaviour for
    both classes should be almost identical.

    See the documentation for `.AMQPClient` for parameter information.

    """

    #: list: Arguments to be passed to each command in the parser.
    #: Note that the command is always passed first.
    parser_args = []

    def __init__(self, *args, model_path=None, model_names=None, **kwargs):

        AMQPClient.__init__(self, *args, **kwargs)

        self.commands_queue = None

        if model_path:

            model_names = model_names or []

            if self.name not in model_names:
                model_names.append(self.name)

            self.models = ModelSet(model_path, model_names=model_names,
                                   raise_exception=False, log=self.log)

        else:

            self.log.warning('no models loaded.')
            self.models = None

        self.timer_commands = TimerCommandList(self)

    async def start(self, **kwargs):
        """Starts the connection to the AMQP broker."""

        # This sets the replies queue but not a commands one.
        await AMQPClient.start(self, **kwargs)

        # Binds the commands queue.
        self.commands_queue = await self.connection.add_queue(
            f'{self.name}_commands', callback=self.new_command,
            bindings=[f'command.{self.name}.#'])

        self.log.info(f'commands queue {self.commands_queue.name!r} '
                      f'bound to {self.connection.connection.url!s}')

        self.timer_commands.start()

        return self

    @classmethod
    def from_config(cls, config, *args, **kwargs):
        """Starts a new actor from a configuration file.

        Refer to `.BaseClient.from_config`.

        """

        return super().from_config(config, *args, **kwargs)

    async def new_command(self, message):
        """Handles a new command received by the actor."""

        with message.process():

            headers = message.info()['headers']
            command_body = json.loads(message.body.decode())

        commander_id = headers['commander_id'].decode()
        command_id = headers['command_id'].decode()
        command_string = command_body['command_string']

        try:
            command = Command(command_string, command_id=command_id,
                              commander_id=commander_id,
                              consumer_id=self.name,
                              actor=self, loop=self.loop)
            command.actor = self  # Assign the actor
        except CommandError as ee:
            await self.write('f', {'text': f'Could not parse the following as a command: {ee!r}'})
            return

        return self.parse_command(command)

    async def handle_reply(self, message):
        """Handles a reply received by the message and updates the models.

        Parameters
        ----------
        message : aio_pika.IncomingMessage
            The message received.

        """

        reply = await AMQPClient.handle_reply(self, message)

        if self.models and reply.sender in self.models:
            self.models[reply.sender].update_model(reply.body)

        return

    async def write(self, message_code='i', message=None, command=None,
                    broadcast=False, **kwargs):
        """Writes a message to user(s).

        Parameters
        ----------
        message_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        message : dict
            The keywords to be output. Must be a dictionary of pairs
            ``{keyword: value}``.
        command : Command
            The command to which we are replying. If not set, it is assumed
            that this is a broadcast.
        broadcast : bool
            Whether to broadcast the message to all the actor or only to the
            commander.
        kwargs
            Keyword arguments that will be added to the message.

        """

        message = message or {}

        assert isinstance(message, dict), 'message must be a dictionary'

        message.update(kwargs)

        message_json = json.dumps(message)

        if command is None:
            broadcast = True

        commander_id = command.commander_id if command else None
        command_id = command.command_id if command else None

        headers = {'message_code': message_code,
                   'commander_id': commander_id,
                   'command_id': command_id,
                   'sender': self.name}

        if broadcast:
            routing_key = f'reply.broadcast'
        else:
            routing_key = f'reply.{command.commander_id}'

        await self.connection.exchange.publish(
            apika.Message(message_json.encode(),
                          content_type='text/json',
                          headers=headers,
                          correlation_id=command_id),
            routing_key=routing_key)

        log_reply(self.log, message_code, message_json)


class TimerCommandList(list):
    """A list of `.TimerCommand` objects that will be executed on a loop.

    Parameters
    ----------
    actor
        The actor in which the commands are to be run.
    resolution : float
        In seconds, how frequently to check if any of the `.TimerCommand` must
        be executed.

    """

    def __init__(self, actor, resolution=0.5, loop=None):

        self.resolution = resolution
        self.actor = actor
        self._task = None
        self.loop = loop or asyncio.get_event_loop()

        list.__init__(self, [])

    def add_command(self, command_string, **kwargs):
        """Adds a new `.TimerCommand`."""

        self.append(TimerCommand(command_string, **kwargs))

    async def poller(self):
        """The polling loop."""

        current_time = time.time()

        while True:

            for timer_command in self:
                elapsed = current_time - timer_command.last_run
                if elapsed > timer_command.delay:
                    timer_command_task = self.loop.create_task(timer_command.run(self.actor))
                    timer_command_task.add_done_callback(timer_command.done)

            self._sleep_task = self.loop.create_task(asyncio.sleep(self.resolution))

            await self._sleep_task
            current_time += self.resolution

    def start(self):
        """Starts the loop."""

        if self.running:
            raise RuntimeError('poller is already running.')

        self._task = self.loop.create_task(self.poller())

        return self

    async def stop(self):
        """Cancel the poller."""

        if not self.running:
            return

        self._task.cancel()

        with suppress(asyncio.CancelledError):
            await self._task

    @property
    def running(self):
        """Returns `True` if the poller is running."""

        if self._task and not self._task.cancelled():
            return True

        return False


class TimerCommand(object):
    """A command to be executed on a loop.

    Parameters
    ----------
    command_string : str
        The command string to run.
    delay : float
        How many seconds to wait between repeated calls.

    """

    def __init__(self, command_string, delay=1):

        self.command_string = command_string
        self.delay = delay

        self.last_run = 0.0

    async def run(self, actor):
        """Run the command."""

        await Command(self.command_string, actor=actor).parse()

    def done(self, task):
        """Marks the execution of a command."""

        self.last_run = time.time()
