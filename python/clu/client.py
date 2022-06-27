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

from typing import Any, Callable, Dict, List, Optional, Union

import aio_pika as apika

from sdsstools.logger import SDSSLogger

from .base import BaseClient, Reply
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

        self.command_id: str | None = None
        self.sender: str | None = None
        self.body = {}

        self.message = message
        self._log = log

        self.is_valid = True

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
            if self._log:
                self._log.warning(f"received message without message_code: {message}")
            return

        self.sender = self.headers.get("sender", None)
        if self.sender is None and self._log:
            self._log.warning(f"received message without sender: {message}")

        self.command_id = message.correlation_id

        command_id_header = self.headers.get("command_id", None)
        if command_id_header and command_id_header != self.command_id:
            if self._log:
                self._log.error(
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
        >>> client = await AMQPClient('my_client', host='localhost').start()
        >>> loop.run_forever()

    Parameters
    ----------
    name
        The name of the client.
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
        The version of the client.
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
        **kwargs,
    ):

        super().__init__(
            name,
            version=version,
            loop=loop,
            log_dir=log_dir,
            log=log,
            **kwargs,
        )

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
        self.running_commands: Dict[str, Command] = {}

        self.models = ModelSet(self, actors=models, raise_exception=False)

    def __repr__(self):

        if not self.connection or self.connection.connection is None:
            url = "disconnected"
        else:
            url = str(self.connection.connection.url)

        return f"<{str(self)} (name={self.name!r}, {url}>"

    async def start(self, exchange_name: str = __EXCHANGE_NAME__):
        """Starts the connection to the AMQP broker."""

        assert self.connection

        # Starts the connection and creates the exchange
        await self.connection.connect(exchange_name)

        # Binds the replies queue.
        self.replies_queue = await self.connection.add_queue(
            f"{self.name}_replies",
            callback=self.handle_reply,
            bindings=["reply.#"],
        )

        url = self.connection.connection.url if self.connection.connection else "???"

        self.log.info(f"replies queue {self.replies_queue.name!r} bound to {url!s}")

        # Initialises the models.
        await self.models.load_schemas()

        return self

    async def stop(self):
        """Cancels queues and closes the connection."""

        assert self.connection

        await self.connection.stop()

    async def run_forever(self):
        """Runs the event loop forever."""

        assert self.connection and self.connection.connection

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

        # Update the models
        if self.models and reply.sender in self.models:
            self.models[reply.sender].update_model(reply.body)

        # If the command is running we check if the message code indicates
        # the command is done and, if so, sets the result in the Future.
        # Also, add the reply to the command list of replies.
        if reply.command_id and reply.command_id in self.running_commands:
            command = self.running_commands[reply.command_id]
            command.replies.append(
                Reply(
                    message=reply.body,
                    message_code=reply.message_code,
                    command=command,
                    validated=True,
                )
            )
            if command._reply_callback is not None:
                command._reply_callback(reply)
            status = CommandStatus.code_to_status(reply.message_code)
            if command.status != status:
                command.set_status(status)
            if status.is_done:
                if not command.done():
                    command.set_result(command)
                    del self.running_commands[reply.command_id]

        return reply

    async def send_command(
        self,
        consumer: str,
        command_string: str,
        *args,
        command_id: str | None = None,
        callback: Optional[Callable[[AMQPReply], None]] = None,
        command: Optional[Command] = None,
        time_limit: Optional[float] = None,
    ):
        """Commands another actor over its RCP queue.

        Parameters
        ----------
        consumer
            The actor we are commanding.
        command_string
            The command string that will be parsed by the remote actor.
        args
            Arguments to concatenate to the command string.
        command_id
            The command ID associated with this command. If empty, an unique
            identifier will be attached.
        callback
            A callback to invoke with each reply received from the actor.
        command
            The `.Command` that initiated the new command. Only relevant for
            actors.
        time_limit
            A delay after which the command is marked as timed out and done.

        Examples
        --------
        These two are equivalent ::

            >>> client.send_command('my_actor', 'do_something --now')
            >>> client.send_command('my_actor', 'do_something', '--now')

        """

        assert self.connection and self.replies_queue

        if command and command.command_id:
            command_id = str(command.command_id)
        else:
            command_id = command_id or str(uuid.uuid4())

        if len(args) > 0:
            command_string += " " + " ".join(map(str, args))

        if command and isinstance(command.commander_id, str):
            commander_id = command.commander_id + f".{consumer}"
        else:
            commander_id = f"{self.name}.{consumer}"

        # Creates and registers a command.
        command = Command(
            command_string=command_string,
            command_id=command_id,
            commander_id=commander_id,
            consumer_id=consumer,
            actor=None,
            loop=self.loop,
            reply_callback=callback,
            time_limit=time_limit,
        )

        self.running_commands[command_id] = command

        headers = {"command_id": command_id, "commander_id": commander_id}

        # The routing key has the topic command and the name of
        # the commanded actor.
        routing_key = f"command.{consumer}"

        message_body = {"command_string": command_string}

        try:
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
        except (apika.exceptions.DeliveryError, apika.exceptions.PublishError):
            # The consumer (actor) did not reply. This usually means that the actor
            # is not connected. We fake a reply from that actor saying so. That will
            # be received by handle_reply which will fail the current command.
            error_msg = dict(error=f"Failed routing message to consumer {consumer!r}.")
            headers.update({"message_code": "f", "sender": consumer})
            await self.connection.exchange.publish(
                apika.Message(
                    json.dumps(error_msg).encode(),
                    content_type="text/json",
                    headers=headers,
                    correlation_id=command_id,
                ),
                routing_key=f"reply.{self.name}",
            )

        return command
