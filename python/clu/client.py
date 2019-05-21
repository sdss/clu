#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-20
# @Filename: client.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-20 19:16:55

import abc
import asyncio
import json
import logging
import pathlib
import uuid

import ruamel.yaml

from .base import CommandStatus
from .command import Command
from .misc.logger import get_logger
from .protocol import TopicListener


try:
    import aio_pika as apika
except ImportError:
    apika = None


__all__ = ['BaseClient', 'AMQPClient']


class BaseClient(metaclass=abc.ABCMeta):
    """A base client that can be used for listening or for an actor.

    This class defines a new client. Clients differ from actors in that
    they do not receive commands or issue replies, but do send commands to
    other actors and listen to the keyword-value flow. All actors are also
    clients and any actor should subclass from `.BaseClient`.

    Normally a new instance of a client or actor is created by passing a
    configuration file path to `.from_config` which defines how the
    client must be started.

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
        ``/data/logs/actors/<name>`` where ``<name>`` is the name of the actor.
        If ``log_dir=False`` or ``log=False``, a logger with a
        `~logging.NullHandler` will be created.
    log : ~logging.Logger
        A `~logging.Logger` instance to be used for logging instead of creating
        a new one.

    """

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
        """Runs the client."""

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

        version = config_dict.pop('version', '?')
        log_dir = config_dict.pop('log_dir', None)

        config_dict.update(kwargs)

        # We also pass *args and **kwargs in case the actor has been subclassed
        # and the subclass' __init__ accepts different arguments.
        new_actor = cls(*args, version=version, log_dir=log_dir, **config_dict)

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
    def send_command(self):
        """Sends a command to an actor. Must be overridden."""

        pass


class AMQPClient(BaseClient):
    """Defines a new client based on the AMQP standard.

    To start a new client first instantiate the class and then run `.run` as
    a coroutine. Note that `.run` does not block so you will need to use
    asyncio's ``run_forever`` or a similar system ::

        >>> loop = asyncio.get_event_loop()
        >>> client = await Client('my_client', 'guest', 'localhost', loop=loop).run()
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
    log : ~logging.Logger
        A `~logging.Logger` instance to be used for logging instead of creating
        a new one.

    """

    __EXCHANGE_NAME__ = 'actor_exchange'

    def __init__(self, name, user, host, version=None,
                 loop=None, log_dir=None, log=None):

        if not apika:
            raise ImportError('to instantiate a new Client class '
                              'you need to have aio_pika installed.')

        super().__init__(name, version=version, loop=loop, log_dir=log_dir, log=log)

        self.user = user
        self.host = host

        self.replies_queue = None

        # Creates the connection to the AMQP broker
        self.connection = TopicListener(self.user, self.host)

        #: dict: External commands currently running.
        self.running_commands = {}

    def __repr__(self):

        if self.connection.connection is None:
            url = 'disconnected'
        else:
            url = str(self.connection.connection.url)

        return f'<{str(self)} (name={self.name}, {url}>'

    async def run(self, exchange_name=__EXCHANGE_NAME__):
        """Starts the connection to the AMQP broker."""

        # Starts the connection and creates the exchange
        await self.connection.connect(exchange_name, loop=self.loop)

        # Binds the replies queue.
        self.replies_queue = await self.connection.add_queue(
            f'{self.name}_replies', callback=self.handle_reply,
            bindings=[f'reply.#'])

        self.log.info(f'replies queue {self.replies_queue.name!r} bound '
                      f'to {self.connection.connection.url!s}')

        return self

    @classmethod
    def from_config(cls, config, *args, **kwargs):
        """Starts a new client from a configuration file.

        Refer to `.BaseClient.from_config`.

        """

        config_dict = cls._parse_config(config)

        args = list(args) + [config_dict.pop('user'),
                             config_dict.pop('host')]

        return super().from_config(config_dict, *args, **kwargs)

    async def handle_reply(self, message):
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

        sender = headers.get('sender', None)
        if sender:
            sender = sender.decode()

        command_id = message.correlation_id

        # Ignores message from self.
        if sender and self.name == sender:
            return None

        # If the command is running we check if the message code indicates
        # the command is done and, if so, sets the result in the Future.
        if command_id in self.running_commands:
            is_done = CommandStatus.get_inverse_dict()[message_code].is_done
            if is_done:
                command = self.running_commands.pop(command_id)
                command.set_result(None)

        return message

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

        # The routing key has the topic command and the name of the commanded actor.
        routing_key = f'command.{consumer}'

        message_body = {'command_string': command_string}

        await self.connection.exchange.publish(
            apika.Message(json.dumps(message_body).encode(),
                          content_type='text/json',
                          headers=headers,
                          correlation_id=command_id,
                          reply_to=self.replies_queue.name),
            routing_key=routing_key)

        return command