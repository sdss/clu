#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-07-30
# @Filename: client.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import uuid

from typing import Any, Dict, List, Optional, Union

import aio_pika as apika

from sdsstools.logger import SDSSLogger

from .base import BaseClient
from .command import Command
from .model import ModelSet
from .protocol import TopicListener
from .tools import CommandStatus


__all__ = ["AMQPClient", "AMQPReply"]


PathLike = Union[str, pathlib.Path]


class AMQPReply(object):
    """Wrapper for an `~aio_pika.IncomingMessage` that expands and decodes it.

    Parameters
    ----------
    message
        The message that contains the reply.
    log
        A message logger.

    Attributes
    ----------
    is_valid
        Whether the message is valid and correctly parsed.
    body
        The body of the message, as a JSON dictionary.
    info
        The info dictionary.
    headers
        The headers of the message, decoded if they are bytes.
    message_code
        The message code.
    sender
        The name of the actor that sends the reply.
    command_id
        The command ID.
    """

    def __init__(
        self,
        message: apika.IncomingMessage,
        log: Optional[logging.Logger] = None,
    ):

        self.message = message
        self.log = log

        self.is_valid = True

        self.body = None

        # Acknowledges receipt of message
        message.ack()

        self.info: Dict[Any, Any] = message.info()

        self.headers = self.info["headers"]
        for key in self.headers:
            if isinstance(self.headers[key], bytes):
                self.headers[key] = self.headers[key].decode()

        self.message_code = self.headers.get("message_code", None)

        if self.message_code is None:
            self.is_valid = False
            if self.log:
                self.log.warning(
                    f"received message without " f"message_code: {message}"
                )
            return

        self.sender = self.headers.get("sender", None)
        if self.sender is None and self.log:
            self.log.warning(f"received message without sender: {message}")

        self.command_id = message.correlation_id

        command_id_header = self.headers.get("command_id", None)
        if command_id_header and command_id_header != self.command_id:
            if self.log:
                self.log.error(
                    f"mismatch between message "
                    f"correlation_id={self.command_id} "
                    f"and header command_id={command_id_header} "
                    f"in message {message}"
                )
            self.is_valid = False
            return

        self.body = json.loads(self.message.body.decode())


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
    name
        The name of the actor.
    url
        RFC3986 formatted broker address. When used, the other connection
        keyword arguments are ignored.
    user
        The user to connect to the AMQP broker. Defaults to ``guest``.
    password
        The password for the user. Defaults to ``guest``.
    host
        The host where the AMQP message broker runs. Defaults to ``localhost``.
    virtualhost
         Virtualhost parameter. ``'/'`` by default.
    port
        The port on which the AMQP broker is running. Defaults to 5672.
    ssl
        Whether to use TLS/SSL connection.
    version
        The version of the actor.
    loop
        The event loop. If `None`, the current event loop will be used.
    log_dir
        The directory where to store the logs. Defaults to
        ``$HOME/logs/<name>`` where ``<name>`` is the name of the actor.
    log
        A `~logging.Logger` instance to be used for logging instead of
        creating a new one.
    parser
        A click command parser that is a subclass of `~clu.parser.CluGroup`.
        If `None`, the active parser will be used.
    models
        A list of actor models whose schemas will be monitored.
    """

    __EXCHANGE_NAME__ = "sdss_exchange"

    connection = None

    def __init__(
        self,
        name: str,
        url: Optional[str] = None,
        user: str = "guest",
        password: str = "guest",
        host: str = "localhost",
        port: int = 5672,
        virtualhost: str = "/",
        ssl: bool = False,
        version: Optional[str] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        log_dir: Optional[PathLike] = None,
        log: Optional[SDSSLogger] = None,
        models: List[str] = [],
    ):

        super().__init__(name, version=version, loop=loop, log_dir=log_dir, log=log)

        self.replies_queue = None

        # Creates the connection to the AMQP broker
        self.connection = TopicListener(
            url=url,
            user=user,
            password=password,
            host=host,
            port=port,
            ssl=ssl,
            virtualhost=virtualhost,
        )

        #: dict: External commands currently running.
        self.running_commands = {}

        self.models = ModelSet(self, actors=models, raise_exception=False, log=self.log)

    def __repr__(self):

        if not self.connection or self.connection.connection is None:
            url = "disconnected"
        else:
            url = str(self.connection.connection.url)

        return f"<{str(self)} (name={self.name!r}, {url}>"

    async def start(self, exchange_name: str = __EXCHANGE_NAME__):
        """Starts the connection to the AMQP broker."""

        # Starts the connection and creates the exchange
        await self.connection.connect(exchange_name)

        # Binds the replies queue.
        self.replies_queue = await self.connection.add_queue(
            f"{self.name}_replies",
            callback=self.handle_reply,
            bindings=["reply.#"],
        )

        self.log.info(
            f"replies queue {self.replies_queue.name!r} "
            f"bound to {self.connection.connection.url!s}"
        )

        # Initialises the models.
        await self.models.load_schemas()

        return self

    async def stop(self):
        """Cancels queues and closes the connection."""

        await self.connection.stop()

    async def run_forever(self):
        """Runs the event loop forever."""

        while not self.connection.connection.is_closed:
            await asyncio.sleep(1)

    async def handle_reply(self, message: apika.IncomingMessage) -> AMQPReply:
        """Handles a reply received from the exchange.

        Creates a new instance of `.AMQPReply` from the ``message``. If the
        reply is valid it updates any running command.

        Parameters
        ----------
        message
            The message received.

        Returns
        -------
        reply
            The `.AMQPReply` object created from the message.
        """

        reply = AMQPReply(message, log=self.log)

        if not reply.is_valid:
            self.log.error("Invalid message received.")
            return reply

        # Ignores message from self, because actors are also clients and they
        # receive their own messages.
        if reply.sender and self.name == reply.sender:
            return reply

        # Update the models
        if self.models and reply.sender in self.models:
            self.models[reply.sender].update_model(reply.body)

        # If the command is running we check if the message code indicates
        # the command is done and, if so, sets the result in the Future.
        # Also, add the reply to the command list of replies.
        if reply.command_id in self.running_commands:
            self.running_commands[reply.command_id].replies.append(reply)
            status = CommandStatus.code_to_status(reply.message_code)
            if status.is_done:
                command = self.running_commands.pop(reply.command_id)
                command.set_status(status)
                if not command.done():
                    command.set_result(command)

        return reply

    async def send_command(
        self,
        consumer: str,
        command_string: str,
        command_id: Optional[str] = None,
    ):
        """Commands another actor over its RCP queue.

        Parameters
        ----------
        consumer
            The actor we are commanding.
        command_string
            The command string that will be parsed by the remote actor.
        command_id
            The command ID associated with this command. If empty, an unique
            identifier will be attached.
        """

        command_id = command_id or str(uuid.uuid4())

        # Creates and registers a command.
        command = Command(
            command_string=command_string,
            command_id=command_id,
            commander_id=self.name,
            consumer_id=consumer,
            actor=None,
            loop=self.loop,
        )

        self.running_commands[command_id] = command

        headers = {"command_id": command_id, "commander_id": self.name}

        # The routing key has the topic command and the name of
        # the commanded actor.
        routing_key = f"command.{consumer}"

        message_body = {"command_string": command_string}

        await self.connection.exchange.publish(
            apika.Message(
                json.dumps(message_body).encode(),
                content_type="text/json",
                headers=headers,
                correlation_id=command_id,
                reply_to=self.replies_queue.name,
            ),
            routing_key=routing_key,
        )

        return command
