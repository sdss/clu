#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-16
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-18 17:42:46

import abc
import asyncio
import json
import logging
import pathlib
import uuid

import click
import ruamel.yaml

import clu

from .base import CommandStatus
from .command import Command
from .misc import get_logger
from .parser import command_parser
from .protocol import TopicListener


try:
    import aio_pika as apika
except ImportError:
    apika = None


__all__ = ['BaseActor', 'Actor', 'command_parser']


__COMMANDER_EXCHANGE__ = 'commands'
__REPLIES_EXCHANGE__ = 'replies'


class BaseActor(metaclass=abc.ABCMeta):
    """An actor based on `asyncio <https://docs.python.org/3/library/asyncio.html>`__.

    This class defines a new actor. Normally a new instance is created by
    passing a configuration file path to `.from_config` which defines how the
    actor must be started.

    Parameters
    ----------
    name : str
        The name of the actor.
    version : str
        The version of the actor.
    loop
        The event loop. If `None`, the current event loop will be used.
    log_dir : str
        The directory where to store the logs. Defaults to
        ``$HOME/logs/<name>`` where ``<name>`` is the name of the actor.
        If ``log_dir=False`` or ``log=False``, a logger with a
        `~logging.NullHandler` will be created.
    log : logging.Logger
        A `logging.Logger` instance to be used for logging instead of creating
        a new one.

    """

    #: list: Arguments to be passed to each command in the parser.
    #: Note that the command is always passed first.
    parser_args = []

    def __init__(self, name, version=None, loop=None, log_dir=None, log=None):

        self.name = name
        assert self.name, 'name cannot be empty.'

        if log_dir is False or log is False:
            # Create a null logger.
            self.log = logging.getLogger(f'actor:{self.name}')
            self.log.addHandler(logging.NullHandler())
        else:
            self.log = log or self.setup_logger(log_dir)

        self.loop = loop or asyncio.get_event_loop()

        self.version = version or '?'

    def __repr__(self):

        return f'<{str(self)} (name={self.name})>'

    def __str__(self):

        return self.__class__.__name__

    @abc.abstractmethod
    async def run(self):
        """Starts the server. Must be overridden by the subclasses."""

        pass

    async def shutdown(self):
        """Shuts down all the remaining tasks."""

        self.log.info('cancelling all pending tasks and shutting down.')

        tasks = [task for task in asyncio.Task.all_tasks(loop=self.loop)
                 if task is not asyncio.tasks.Task.current_task(loop=self.loop)]
        list(map(lambda task: task.cancel(), tasks))

        await asyncio.gather(*tasks, return_exceptions=True)

        self.loop.stop()

    @staticmethod
    def _parse_config(config):

        if not isinstance(config, dict):

            config = pathlib.Path(config)
            assert config.exists(), 'configuration path does not exist.'

            yaml = ruamel.yaml.YAML(typ='safe')
            config = yaml.load(open(str(config)))

        if 'actor' in config:
            config = config['actor']

        return config

    @classmethod
    def from_config(cls, config, *args, **kwargs):
        """Parses a configuration file.

        Parameters
        ----------
        config : dict or str
            A configuration dictionary or the path to a YAML configuration
            file that must contain a section ``'actor'`` (if the section is
            not present, the whole file is assumed to be the actor
            configuration).

        """

        config_dict = cls._parse_config(config)

        # If we subclass and override from_config we need to super() it and
        # send all the arguments already unpacked. Otherwise we get the name
        # from the config.
        if len(args) == 0:
            args = [config_dict['name']]

        version = config_dict.get('version', '?')
        log_dir = config_dict.get('log_dir', None)

        # We also pass *args and **kwargs in case the actor has been subclassed
        # and the subclass' __init__ accepts different arguments.
        new_actor = cls(*args, version=version, log_dir=log_dir, **kwargs)

        return new_actor

    def setup_logger(self, log_dir, file_level=10, shell_level=20):
        """Starts the file logger."""

        log = get_logger('actor:' + self.name)

        if log_dir is None:
            log_dir = pathlib.Path(f'/data/logs/actors/{self.name}/').expanduser()
        else:
            log_dir = pathlib.Path(log_dir).expanduser()

        if not log_dir.exists():
            log_dir.mkdir(parents=True)

        log.start_file_logger(log_dir / f'{self.name}.log')

        log.sh.setLevel(shell_level)
        log.fh.setLevel(file_level)

        log.info(f'{self.name}: logging system initiated.')

        return log

    @abc.abstractmethod
    def new_command(self):
        """Handles a new command.

        Must be overridden by the subclass and call ``_new_command_internal``
        with a `.Command` object.

        """

        pass

    def _new_command_internal(self, command):
        """Handles a new command received by the actor."""

        try:

            self.parse(command)
            return command

        except clu.CommandParserError as ee:

            lines = ee.args[0].splitlines()
            for line in lines:
                command.write('w', text=line)

        except Exception:

            self.log.exception('command failed with error:')

        command.set_status(command.status.FAILED, message=f'Command {command.body!r} failed.')

    def parse(self, command):
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

        try:
            # We call the command with a custom context to get around
            # the default handling of exceptions in Click. This will force
            # exceptions to be raised instead of redirected to the stdout.
            # See http://click.palletsprojects.com/en/7.x/exceptions/
            ctx = command_parser.make_context('command-parser',
                                              command.body.split(),
                                              obj={'parser_args': parser_args})
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


class Actor(BaseActor):
    """An actor class that uses AMQP message brokering.

    This class differs from `~clu.legacy.actor.LegacyActor` in that it uses
    an AMQP messaging broker (typically RabbitMQ) to communicate with other
    actors in the system, instead of standard TCP sockets. Although the
    internals and protocols are different the entry points and behaviour for
    both classes should be almost identical.

    To start a new actor first instantiate the class and then run `.run` as
    a coroutine. Note that `.run` does not block so you will need to use
    asyncio's ``run_forever`` or a similar system ::

        >>> loop = asyncio.get_event_loop()
        >>> actor = await Actor('my_actor', 'guest', 'localhost', loop=loop).run()
        >>> loop.run_forever()

    Parameters
    ----------
    name : str
        The name of the actor.
    user : str
        The user to connect to the AMQP broker.
    host : str
        The host where the AMQP message broker lives.
    version : str
        The version of the actor.
    loop
        The event loop. If `None`, the current event loop will be used.
    log_dir : str
        The directory where to store the logs. Defaults to
        ``$HOME/logs/<name>`` where ``<name>`` is the name of the actor.
    log : logging.Logger
        A `logging.Logger` instance to be used for logging instead of creating
        a new one.

    """

    #: list: Arguments to be passed to each command in the parser.
    #: Note that the command is always passed first.
    parser_args = []

    def __init__(self, name, user, host, version=None,
                 loop=None, log_dir=None, log=None):

        if not apika:
            raise ImportError('to instantiate a new Actor class '
                              'you need to have aio_pika installed.')

        super().__init__(name, version=version, loop=loop, log_dir=log_dir, log=log)

        self.user = user
        self.host = host

        # Binds a queue to the command exchange
        self.commander = TopicListener(self.new_command, bindings=[self.name])

        # Binds a queue to the replies exchange
        self.listener = TopicListener(self.handle_reply, bindings=[self.name, 'broadcast.#'])

        #: dict: External commands currently running.
        self.running_commands = {}

    def __repr__(self):

        if self.commander.connection is None:
            url = 'disconnected'
        else:
            url = str(self.commander.connection.url)

        return f'<{str(self)} (name={self.name}, {url}>'

    async def run(self):
        """Starts the server."""

        await self.commander.connect(user=self.user, host=self.host,
                                     queue_name=f'{self.name}_commands',
                                     exchange_name=__COMMANDER_EXCHANGE__,
                                     loop=self.loop)
        self.log.info(f'commands queue bound to {self.commander.connection.url!s}')

        await self.listener.connect(channel=self.commander.channel,
                                    queue_name=f'{self.name}_replies',
                                    exchange_name=__REPLIES_EXCHANGE__,
                                    loop=self.loop)
        self.log.info(f'replies queue bound to {self.listener.connection.url!s}')

        return self

    @classmethod
    def from_config(cls, config, *args, **kwargs):
        """Starts a new actor from a configuration file.

        Refer to `.BaseActor.from_config`.

        """

        config_dict = cls._parse_config(config)

        args = list(args) + [config_dict.get('user'),
                             config_dict.get('host')]

        return super().from_config(config_dict, *args, **kwargs)

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

        self._new_command_internal(command)

    def handle_reply(self, message):
        """Handles a reply received by the message and updates the models.

        Parameters
        ----------
        message : aio_pika.IncomingMessage
            The message received.

        """

        # Acknowledges receipt of message
        message.ack()

        message_info = message.info()
        headers = message_info['headers']

        if 'message_code' in headers:
            message_code = headers['message_code'].decode()
        else:
            message_code = None
            self.log.warning(f'received message without message_code: {message}')

        command_id = message.correlation_id
        routing_key = message.routing_key

        # Ignores broadcast that come from this actor.
        if 'broadcast' in routing_key and self.name in routing_key:
            return

        # If the command is running we check if the message code indicates
        # the command is done and, if so, sets the result in the Future.
        if command_id in self.running_commands:
            is_done = CommandStatus.get_inverse_dict()[message_code].is_done
            if is_done:
                command = self.running_commands.pop(command_id)
                command.set_result(None)

    async def send_command(self, consumer, command_string, command_id=None):
        """Commands another actor over its RCP queue.

        Parameters
        ----------
        consumer : str
            The actor we are commanding.
        command_string : str
            The command string that will be parsed by the remote actor.
        command_id
            The command ID associated with this command. If empty, an unique
            identifier will be attached.

        """

        command_id = command_id or str(uuid.uuid4())

        # Creates and registers a command.
        command = Command(command_string=command_string,
                          command_id=command_id,
                          commander_id=self.name,
                          consumer_id=consumer,
                          actor=self, loop=self.loop)

        self.running_commands[command_id] = command

        headers = {'command_id': command_id,
                   'commander_id': self.name}

        message_body = {'command_string': command_string}

        await self.commander.exchange.publish(
            apika.Message(json.dumps(message_body).encode(),
                          content_type='text/json',
                          headers=headers,
                          correlation_id=command_id,
                          reply_to=self.listener.queue.name),
            routing_key=consumer)

        return command

    async def write(self, message_code, message=None, command=None,
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
                   'command_id': command_id}

        routing_key = f'broadcast.{self.name}' if broadcast else command.commander_id

        await self.listener.exchange.publish(
            apika.Message(message_json,
                          content_type='text/json',
                          headers=headers,
                          correlation_id=command_id),
            routing_key=routing_key)
