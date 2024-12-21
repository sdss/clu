#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-16
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import json
import pathlib
import re
import uuid
import warnings
from datetime import datetime, timezone

from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar, Union, cast

import aio_pika as apika
import click

from .base import BaseActor, MessageCode, Reply
from .client import AMQPClient
from .command import Command, TimedCommandList
from .exceptions import CluWarning, CommandError
from .parsers import ClickParser, CluCommand
from .protocol import TCPStreamServer
from .tools import log_reply


__all__ = ["AMQPActor", "JSONActor", "AMQPBaseActor", "TCPBaseActor"]


T = TypeVar("T")
PathLike = Union[str, pathlib.Path]
SchemaType = Union[Dict[str, Any], PathLike]
TaskCallbackType = Callable[[dict], Awaitable[Union[Command, None]]]


class CustomTransportType(asyncio.Transport):
    user_id: Union[str, int]
    multiline: bool


class AMQPBaseActor(AMQPClient, BaseActor):
    """An actor class that uses AMQP message brokering.

    This class differs from `~clu.legacy.actor.LegacyActor` in that it uses
    an AMQP messaging broker (typically RabbitMQ) to communicate with other
    actors in the system, instead of standard TCP sockets. Although the
    internals and protocols are different the entry points and behaviour for
    both classes should be almost identical.

    This class needs to be subclassed with a command parser.

    See the documentation for `.AMQPActor` and `.AMQPClient` for additional
    parameter information.

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.commands_queue = None
        self.timed_commands = TimedCommandList(self)

    async def start(self, **kwargs):
        """Starts the connection to the AMQP broker."""

        self.set_loop_exception_handler()

        # This sets the replies queue but not a commands one.
        await AMQPClient.start(self, **kwargs)

        assert self.connection.connection
        assert isinstance(self.connection.connection, apika.Connection)

        # Binds the commands queue.
        self.commands_queue = await self.connection.add_queue(
            f"{self.name}_commands",
            callback=self.new_command,
            bindings=[f"command.{self.name}.#"],
        )

        self.log.debug(
            f"Commands queue {self.commands_queue.name!r} "
            f"bound to {self.connection.connection.url!s}"
        )

        self.timed_commands.start()

        return self

    async def new_command(self, message: apika.abc.AbstractIncomingMessage, ack=True):
        """Handles a new command received by the actor."""

        if ack:
            async with message.process():
                headers = message.info().get("headers", {})
                command_body = json.loads(message.body.decode())
        else:
            headers = message.info().get("headers", {})
            command_body = json.loads(message.body.decode())

        commander_id = headers.get("commander_id", None)
        command_id = headers.get("command_id", None)
        internal = headers.get("internal", False)

        command_string = command_body.get("command_string", "")
        full_command_string = f"{self.name} {command_string}"

        try:
            command = Command(
                command_string,
                command_id=command_id,
                commander_id=commander_id,
                consumer_id=self.name,
                actor=self,
                internal=internal,
            )
            command.actor = self  # Assign the actor
        except CommandError as ee:
            self.write(
                "f",
                {
                    "error": "Could not parse the following as a command: "
                    f"{full_command_string!r}: {ee}"
                },
            )
            return

        self.log.info(
            f"New command received: {full_command_string!r} "
            f"(commander_id={commander_id!r}, command_id={command_id!r})"
        )

        return self.parse_command(command)

    async def _write_internal(self, reply: Reply, write_to_log: bool = True):
        """Writes a message to user(s).

        Parameters
        ----------
        reply
            The reply object to output to users.
        write_to_log
            Whether to write the reply to the log. Defaults to yes but
            it may be useful to prevent large repetitive replies cluttering
            the log.

        """

        assert self.connection

        message = reply.message
        message_json = json.dumps(message)

        command = reply.command

        if command is None or reply.broadcast:
            routing_key = "reply.broadcast"
        else:
            routing_key = f"reply.{command.commander_id}"

        commander_id = command.commander_id if command else None
        command_id = command.command_id if command else None

        headers = {
            "message_code": reply.message_code.value,
            "commander_id": commander_id,
            "command_id": command_id,
            "sender": self.name,
            "internal": reply.internal,
        }

        if self.log and write_to_log:
            log_dict = {"headers": headers, "message": message}
            log_reply(self.log, reply.message_code, json.dumps(log_dict))

        if hasattr(self.connection, "exchange"):
            await self.connection.exchange.publish(
                apika.Message(
                    message_json.encode(),
                    content_type="text/json",
                    headers=headers,
                    correlation_id=str(command_id) if command_id is not None else None,
                    timestamp=datetime.now(timezone.utc),
                ),
                routing_key=routing_key,
            )
        else:
            warnings.warn(
                f"Exchange is not ready to output message: {message}",
                CluWarning,
            )


class AMQPActor(ClickParser, AMQPBaseActor):
    """An `AMQP actor <.AMQPBaseActor>` that uses a `click parser <.ClickParser>`."""

    def __init__(self, *args, **kwargs):
        AMQPBaseActor.__init__(self, *args, **kwargs)

        self.task_handlers: dict[str, TaskCallbackType] = {}

    def add_task_handler(self, name: str, callback: TaskCallbackType):
        """Adds a task handler.

        Parameters
        ----------
        name
            The name of the task handler.
        callback
            A coroutine to call with the task payload as the only argument.

        """

        self.task_handlers[name] = callback

    async def new_command(self, message: apika.abc.AbstractIncomingMessage, ack=True):
        """Handles a new command received by the actor."""

        headers = message.info().get("headers", {})

        is_task = headers.get("task", False)
        if not is_task:
            return await AMQPBaseActor.new_command(self, message, ack=ack)

        body = json.loads(message.body.decode())
        task_name = body.pop("task", None)

        if task_name not in self.task_handlers:
            self.write(MessageCode.ERROR, {"error": f"Unknown task {task_name!r}"})
            return

        # Add actor to payload.
        body["__actor__"] = self

        asyncio.gather(self.task_handlers[task_name](body))


TCPBaseActor_co = TypeVar("TCPBaseActor_co", bound="TCPBaseActor")


class TCPBaseActor(BaseActor):
    """A TCP base actor that replies using JSON.

    This implementation of `.BaseActor` uses TCP as command/reply channel and
    replies to the user by sending a JSON-valid string. This makes it useful
    as a "device" actor that is not connected to the central message parsing
    system but that we still want to accept commands and reply with easily
    parseable messages.

    Commands received by this actor must be in the format
    ``[<uid>] <command string>``, where ``<uid>`` is any integer unique
    identifier that will be used as ``command_id`` and appended to any reply.

    This is a base actor that does not include a parser. It must be subclassed with
    a concrete parser that overrides ``parse_command``.

    Parameters
    ----------
    name
        The actor name.
    host
        The host where the TCP server will run.
    port
        The port of the TCP server.
    args,kwargs
        Arguments to be passed to `.BaseActor`.

    """

    def __init__(
        self,
        name: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        *args,
        **kwargs,
    ):
        super().__init__(name, *args, **kwargs)

        self.host = host or "localhost"
        self.port = port

        if self.port is None:
            raise ValueError("port needs to be specified.")

        #: Mapping of commander_id to transport
        self.transports = dict()

        #: TCPStreamServer: The server to talk to this actor.
        self.server = TCPStreamServer(
            self.host,
            self.port,
            connection_callback=self.new_user,
            data_received_callback=self.new_command,
        )

        self.timed_commands = TimedCommandList(self)

    async def start(self: TCPBaseActor_co) -> TCPBaseActor_co:
        """Starts the TCP server."""

        if self.log:
            # Set the loop exception handler to be handled by the logger.
            loop = asyncio.get_running_loop()
            loop.set_exception_handler(self.log.asyncio_exception_handler)

        await self.server.start()
        self.log.info(f"running TCP server on {self.host}:{self.port}")

        self.timed_commands.start()

        return self

    async def stop(self):
        """Stops the client connection and running tasks."""

        if self.server.is_serving():
            self.server.stop()

        await self.timed_commands.stop()

    async def run_forever(self):
        """Runs the actor forever, keeping the loop alive."""

        await self.server.serve_forever()

    def new_user(self, transport: CustomTransportType):
        """Assigns userID to new client connection."""

        if transport.is_closing():
            if hasattr(transport, "user_id"):
                self.log.debug(f"user {transport.user_id} disconnected.")
                return self.transports.pop(transport.user_id)

        user_id = str(uuid.uuid4())
        transport.user_id = user_id
        transport.multiline = False
        self.transports[user_id] = transport

        sock = transport.get_extra_info("socket")
        if sock is not None:
            peername = sock.getpeername()[0]
            self.log.debug(f"user {user_id} connected from {peername}.")

    def new_command(self, transport: CustomTransportType, command_str: bytes):
        """Handles a new command received by the actor."""
        print("hellow")
        commander_id: Optional[int] = getattr(transport, "user_id", None)
        message: str = command_str.decode().strip()

        if not message:
            return

        match = re.match(r"([0-9]*)\s*(.+)", message)
        if match is None:
            self.write("f", {"error": "Cannot match command string text."})
            return

        command_id, command_string = match.groups()

        if command_id == "":
            command_id = 0
        else:
            command_id = int(command_id)

        command_string = command_string.strip()
        full_command_string = f"{self.name} {command_string}"

        if not command_string:
            return
        try:
            command = Command(
                command_string=command_string,
                commander_id=commander_id,
                command_id=command_id,
                consumer_id=self.name,
                actor=self,
                transport=transport,
            )
        except CommandError as ee:
            self.write(
                "f",
                {
                    "error": "Could not parse the following as a command: "
                    f"{full_command_string!r}: {ee}"
                },
            )
            return

        self.log.info(
            f"New command received: {full_command_string!r} "
            f"(commander_id={commander_id!r}, command_id={command_id!r})"
        )

        return self.parse_command(command)

    def write(self, *args, **kwargs):
        """Writes a message to user(s) as a JSON.

        A ``header`` keyword with the ``commander_id`` (i.e., the user id of
        the transport that sent the command), ``command_id``, ``message_code``,
        and ``sender`` is added to each message. The payload of the message
        is written to ``data``. An example of a valid message is

        .. code-block:: yaml

            {
                "header": {
                    "command_id": 0,
                    "commander_id": 1,
                    "message_code": "i",
                    "sender": "test_camera"
                },
                "message": {
                    "camera": {
                        "name": "test_camera",
                        "uid": "DEV_12345"
                    },
                    "status": {
                        "temperature": 25.0,
                        "cooler": 10.0
                    }
                }
            }

        Although the messsage is displayed here in multiple lines, it is
        written as a single line to the TCP clients to facilitate parsing.
        For a multiline output, which is more human-readable, use the
        ``multiline`` command.

        See `~.BaseActor.write` for details on the allowed parameters.
        """

        BaseActor.write(self, *args, **kwargs)

    def _write_internal(self, reply: Reply, write_to_log: bool = True):
        """Write a reply to the users.

        Parameters
        ----------
        reply
            The reply object to output to users.
        write_to_log
            Whether to write the reply to the log. Defaults to yes but
            it may be useful to prevent large repetitive replies cluttering
            the log.

        """

        def send_to_transport(transport, message):
            if getattr(transport, "multiline", False):
                message_json = json.dumps(message, sort_keys=False, indent=4) + "\n"
            else:
                message_json = json.dumps(message, sort_keys=False) + "\n"
            transport.write(message_json.encode())

        message = reply.message
        command = cast(Command, reply.command)

        commander_id = command.commander_id if command else None
        command_id = command.command_id if command else None
        transport = command.transport if command else None

        message_full = {}
        header = {
            "header": {
                "command_id": command_id,
                "commander_id": commander_id,
                "message_code": reply.message_code.value,
                "internal": reply.internal,
                "sender": self.name,
            }
        }

        message_full.update(header)
        message_full.update({"data": message})

        if reply.broadcast or commander_id is None or transport is None:
            for transport in self.transports.values():
                send_to_transport(transport, message_full)
        else:
            send_to_transport(transport, message_full)

        message_json = json.dumps(message_full, sort_keys=False) + "\n"

        if self.log and write_to_log:
            log_reply(self.log, reply.message_code, message_json.strip())


class JSONActor(ClickParser, TCPBaseActor):
    """An implementation of `.TCPBaseActor` that uses a Click command parser."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add the multiline command
        self.parser.add_command(multiline)

    def send_command(self, *args, **kwargs):
        """Not implemented for `.JSONActor`."""

        raise NotImplementedError("JSONActor cannot send commands to other actors.")


@click.command(cls=CluCommand)
@click.option("--on/--off", default=True, help="Turn multiline on/off.")
async def multiline(command: Command, on: bool):
    """Set multiline mode for the transport."""

    transport = getattr(command, "transport", None)
    if not transport:
        return command.fail("The command has no transport.")

    transport.multiline = on

    return command.finish("Multiline mode is {}".format("on" if on else "off"))
