#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-07-30
# @Filename: client.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import json
import uuid

import aio_pika as apika

from .base import BaseClient
from .command import Command
from .model import ModelSet, Reply
from .protocol import TopicListener
from .tools import CommandStatus


__all__ = ['AMQPClient']


class AMQPClient(BaseClient):
    """Defines a new client based on the AMQP standard.

    To start a new client first instantiate the class and then run `.start` as
    a coroutine. Note that `.start` does not block so you will need to use
    asyncio's ``run_forever`` or a similar system ::

        >>> loop = asyncio.get_event_loop()
        >>> client = await Client('my_client', 'guest', 'localhost').start()
        >>> loop.run_forever()

    Parameters
    ----------
    name : str
        The name of the actor.
    user : str
        The user to connect to the AMQP broker. Defaults to ``guest``.
    host : str
        The host where the AMQP message broker runs. Defaults to ``localhost``.
    port : int
        The port on which the AMQP broker is running. Defaults to 5672.
    version : str
        The version of the actor.
    loop
        The event loop. If `None`, the current event loop will be used.
    log_dir : str
        The directory where to store the logs. Defaults to
        ``$HOME/logs/<name>`` where ``<name>`` is the name of the actor.
    log : ~logging.Logger
        A `~logging.Logger` instance to be used for logging instead of
        creating a new one.
    parser : ~clu.parser.CluGroup
        A click command parser that is a subclass of `~clu.parser.CluGroup`.
        If `None`, the active parser will be used.
    model_path : str or pathlib.Path
        The path to the directory containing the schema files. Each schema
        file must be named as the model and have extension ``.json``
        (e.g., ``sop.json``).
    model_names : list
        A list of models whose schemas will be loaded.

    """

    __EXCHANGE_NAME__ = 'clu_exchange'

    connection = None

    def __init__(self, name, user=None, host=None, port=None, version=None,
                 loop=None, log_dir=None, log=None, model_path=None,
                 model_names=None):

        super().__init__(name, version=version, loop=loop,
                         log_dir=log_dir, log=log)

        self.user = user or 'guest'
        self.host = host or 'localhost'
        self.port = port or 5672

        self.replies_queue = None

        # Creates the connection to the AMQP broker
        self.connection = TopicListener(self.user, self.host, port=self.port)

        #: dict: External commands currently running.
        self.running_commands = {}

        if model_path:

            model_names = model_names or []
            self.models = ModelSet(model_path, model_names=model_names,
                                   raise_exception=False, log=self.log)

        else:

            self.log.warning('no models loaded.')
            self.models = None

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

    async def shutdown(self):
        """Cancels queues and closes the connection."""

        await self.connection.stop()

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
            status = CommandStatus.get_inverse_dict()[reply.message_code]
            if status.is_done:
                command = self.running_commands.pop(reply.command_id)
                if not command.done():
                    command.set_result(command)

        # Update the models
        if self.models and reply.sender in self.models:
            self.models[reply.sender].update_model(reply.body)

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

        # The routing key has the topic command and the name of
        # the commanded actor.
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
