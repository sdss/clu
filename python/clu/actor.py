#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-16
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-22 09:14:56

import abc
import asyncio
import json

import click

import clu

from .client import AMQPClient, BaseClient
from .command import Command
from .model import ModelSet
from .parser import command_parser


try:
    import aio_pika as apika
except ImportError:
    apika = None


__all__ = ['BaseActor', 'Actor', 'command_parser']


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
    async def run(self):
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
        """Handles a new command received by the actor."""

        try:

            self._parse(command)
            return command

        except clu.CommandParserError as ee:

            lines = ee.args[0].splitlines()
            for line in lines:
                command.write('w', text=line)

        except click.exceptions.Exit:

            return command.set_status(command.status.FAILED, {'text': f'Use help [CMD]'})

        except Exception:

            self.log.exception('command failed with error:')

        command.set_status(command.status.FAILED, message=f'Command {command.body!r} failed.')

    def _parse(self, command):
        """Parses an user command with the default parser.

        This method can be overridden to use a custom parser.

        """

        # This will pass the command as the first argument for each command.
        # If self.parser_args is defined, those arguments will be passed next.
        parser_args = [command]
        parser_args += self.parser_args

        # Empty command. Just finish the command.
        if not command.body:
            result = self.write(':', '', command=command)
            if asyncio.iscoroutine(result):
                self.loop.create_task(result)
            return

        command.set_status(command.status.RUNNING)

        # If the command contains the --help flag, redirects it to the help command.
        if '--help' in command.body:
            command.body = 'help ' + command.body
            command.body = command.body.replace(' --help', '')

        try:

            # We call the command with a custom context to get around
            # the default handling of exceptions in Click. This will force
            # exceptions to be raised instead of redirected to the stdout.
            # See http://click.palletsprojects.com/en/7.x/exceptions/
            ctx = command_parser.make_context(f'{self.name}-command-parser',
                                              command.body.split(),
                                              obj={'parser_args': parser_args})

            # Makes sure this is the global context. This solves problems when
            # the actor have been started from inside an existing context,
            # for example when it's called from a CLI click application.
            click.globals.push_context(ctx)

            with ctx:
                command_parser.invoke(ctx)

        except click.ClickException as ee:

            # If this is a command that cannot be parsed.
            if ee.message is None:
                ee.message = f'{ee.__class__.__name__}:\n{ctx.get_help()}'
            else:
                ee.message = f'{ee.__class__.__name__}: {ee.message}'

            raise clu.CommandParserError(ee.message)

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

    async def run(self, **kwargs):
        """Starts the connection to the AMQP broker."""

        # This sets the replies queue but not a commands one.
        await AMQPClient.run(self, **kwargs)

        # Binds the commands queue.
        self.commands_queue = await self.connection.add_queue(
            f'{self.name}_commands', callback=self.new_command,
            bindings=[f'command.{self.name}.#'])

        self.log.info(f'commands queue {self.commands_queue.name!r} '
                      f'bound to {self.connection.connection.url!s}')

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
        except clu.CommandError as ee:
            await self.write('f', {'text': f'Could not parse the following as a command: {ee!r}'})
            return

        self.parse_command(command)

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

        message_json = json.dumps(message).encode()

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
            apika.Message(message_json,
                          content_type='text/json',
                          headers=headers,
                          correlation_id=command_id),
            routing_key=routing_key)
