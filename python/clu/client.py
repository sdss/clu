#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-07-30
# @Filename: client.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import json
import uuid

from .base import BaseClient
from .command import Command
from .model import Reply
from .protocol import TopicListener
from .tools import CommandStatus


try:
    import aio_pika as apika
except ImportError:
    apika = None


__all__ = ['AMQPClient']


class AMQPClient(BaseClient):
    """Defines a new client based on the AMQP standard.

    To start a new client first instantiate the class and then run `.start` as
    a coroutine. Note that `.start` does not block so you will need to use
    asyncio's ``run_forever`` or a similar system ::

        >>> loop = asyncio.get_event_loop()
        >>> client = await Client('my_client', 'guest', 'localhost', loop=loop).start()
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
    parser : ~clu.parser.CluGroup
        A click command parser that is a subclass of `~clu.parser.CluGroup`.
        If `None`, the active parser will be used.

    """

    __EXCHANGE_NAME__ = 'actor_exchange'

    connection = None

    def __init__(self, name, user, host, version=None,
                 loop=None, log_dir=None, log=None, parser=None):

        if not apika:
            raise ImportError('to instantiate a new Client class '
                              'you need to have aio_pika installed.')

        super().__init__(name, version=version, loop=loop,
                         log_dir=log_dir, log=log, parser=parser)

        self.user = user
        self.host = host

        self.replies_queue = None

        # Creates the connection to the AMQP broker
        self.connection = TopicListener(self.user, self.host)

        #: dict: External commands currently running.
        self.running_commands = {}

    def __repr__(self):

        if not self.connection or self.connection.connection is None:
            url = 'disconnected'
        else:
            url = str(self.connection.connection.url)

        return f'<{str(self)} (name={self.name!r}, {url}>'

    async def start(self, exchange_name=__EXCHANGE_NAME__):
        """Starts the connection to the AMQP broker."""

        # Starts the connection and creates the exchange
        await self.connection.connect(exchange_name, loop=self.loop)

        # Binds the replies queue.
        self.replies_queue = await self.connection.add_queue(
            f'{self.name}_replies', callback=self.handle_reply,
            bindings=['reply.#'])

        self.log.info(f'replies queue {self.replies_queue.name!r} '
                      f'bound to {self.connection.connection.url!s}')

        return self

    @classmethod
    def from_config(cls, config, *args, **kwargs):
        """Starts a new client from a configuration file.

        Refer to `.BaseClient.from_config`.

        """

        config_dict = cls._parse_config(config)

        args = list(args) + [config_dict.pop('name'),
                             config_dict.pop('user'),
                             config_dict.pop('host')]

        return super().from_config(config_dict, *args, **kwargs)

    async def handle_reply(self, message):
        """Handles a reply received from the exchange.

        Creates a new instance of `.Reply` from the ``message``. If the
        reply is valid it updates any running command.

        Parameters
        ----------
        message : aio_pika.IncomingMessage
            The message received.

        Returns
        -------
        reply : `.Reply`
            The `.Reply` object created from the message.

        """

        reply = Reply(message, ack=True)
        if not reply.is_valid:
            self.log.error('invalid message.')
            return reply

        # Ignores message from self.
        if reply.sender and self.name == reply.sender:
            return reply

        # If the command is running we check if the message code indicates
        # the command is done and, if so, sets the result in the Future.
        if reply.command_id in self.running_commands:
            is_done = CommandStatus.get_inverse_dict()[reply.message_code].is_done
            if is_done:
                command = self.running_commands.pop(reply.command_id)
                if not command.done():
                    command.set_result(command)

        return reply

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
