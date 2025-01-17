#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-13
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import logging
import pathlib
import warnings

from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union, cast

import click

import clu
from clu.parsers.click import CluCommand

from ..actor import CustomTransportType
from ..base import BaseActor, MessageCode, Reply
from ..command import Command, TimedCommandList, parse_legacy_command
from ..parsers import ClickParser
from ..protocol import TCPStreamServer
from ..tools import log_reply
from .tron import TronConnection
from .types.messages import Reply as OpsReply


__all__ = ["LegacyActor", "BaseLegacyActor"]


T = TypeVar("T", bound="BaseLegacyActor")
PathLike = Union[str, pathlib.Path]


@click.command(cls=CluCommand)
async def tron_reconnect(*args):
    """Reconnects to tron/hub."""

    command = args[0]

    if command.actor.tron is None:
        return command.fail("Tron instance not set.")

    command.actor.tron.stop()
    await asyncio.sleep(0.5)

    await command.actor.tron.start()

    return command.finish()


class BaseLegacyActor(BaseActor):
    """An actor that provides compatibility with the SDSS opscore protocol.

    The TCP servers need to be started by awaiting the coroutine `.start`.
    Note that `.start` does not block so you will need to use asyncio's
    `.run_forever` or a similar system ::

        >>> loop = asyncio.get_event_loop()
        >>> my_actor = await LegacyActor('my_actor', '127.0.0.1', 9999, loop=loop)
        >>> my_actor.start()
        >>> loop.run_forever()

    Parameters
    ----------
    name
        The name of the actor.
    host
        The host where the TCP server will run.
    port
        The port of the TCP server.
    tron_host
        The host on which Tron is running.
    tron_port
        The port on which Tron is running.
    models
        A list of strings with the actors whose models will be tracked.
    version
        The version of the actor.
    loop
        The event loop. If `None`, the current event loop will be used.
    log_dir
        The directory where to store the logs. Defaults to
        ``$HOME/logs/<name>`` where ``<name>`` is the name of the actor.
    log
        A `~logging.Logger` instance to be used for logging instead of creating
        a new one.
    schema
        The path to the datamodel schema for the actor, in JSON Schema format.
        If the schema is provided all replies will be validated against it.
        An invalid reply will fail and not be emitted. The schema can also be
        set when subclassing by setting the class ``schema`` attribute.
    store
        Whether to store the output keywords in a `.KeywordStore`. `False`
        (the default), disables the feature. `True` will store a record
        of all the output keywords. A list of keyword names to store can
        also be passed.
    config
        A dictionary of configuration parameters that will be accessible to the actor.
    """

    def __init__(
        self,
        name: str,
        host: str,
        port: int,
        tron_host: Optional[str] = None,
        tron_port: Optional[int] = None,
        models: List[str] = [],
        version: Optional[str] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        log_dir: Optional[PathLike] = None,
        log: Optional[logging.Logger] = None,
        verbose: bool = False,
        schema: Optional[PathLike] = None,
        store: bool | list[str] = False,
        additional_properties: bool = False,
        config: Dict[str, Any] = {},
    ):
        super().__init__(
            name,
            version=version,
            log_dir=log_dir,
            log=log,
            verbose=verbose,
            schema=schema,
            additional_properties=additional_properties,
            config=config,
            store=store,
        )

        #: Mapping of user_id to transport
        self.transports = dict()

        self.host = host
        self.port = port

        # TCPStreamServer: The server to talk to this actor.
        self._server = TCPStreamServer(
            host,
            port,
            connection_callback=self.new_user,
            data_received_callback=self.new_command,
        )

        if tron_host and tron_port:
            #: TronConnection: The client connection to Tron.
            self.tron = TronConnection(
                f"{self.name}.{self.name}",
                host=tron_host,
                port=tron_port,
                models=models,
                log=self.log,
            )
        else:
            self.tron = None

        #: dict: Actor models.
        self.models = self.tron.models if self.tron else {}

        self.timed_commands = TimedCommandList(self)

    def __repr__(self):
        return (
            f"<{str(self)} (name={self.name!r}, host={self.host!r}, port={self.port})>"
        )

    async def start(self: T, get_keys: bool = True, start_nubs: bool = True) -> T:
        """Starts the server and the Tron client connection.

        Parameters
        ----------
        get_keys
            Whether to issue ``keys getFor`` commands against the hub to retrieve
            the current values for the model keys.
        start_nubs
            If `True`, and a `.TronConnection` has been created, sends a
            ``hub startNubs <name>`` where ``<name>`` is the name of the
            actor to attempt to automatically connect it to the hub.

        """

        self.set_loop_exception_handler()

        await self._server.start()
        self.log.info(f"running TCP server on {self.host}:{self.port}")

        # Start tron connection
        try:
            if self.tron:
                await self.tron.start(get_keys=get_keys)
                self.log.info(
                    f"started tron connection at {self.tron.host}:{self.tron.port}"
                )
                if start_nubs:
                    self.log.debug("Asking Tron to connect back.")
                    await self.send_command("hub", f"startNubs {self.name}")
            else:
                warnings.warn(
                    "starting LegacyActor without Tron connection.",
                    clu.CluWarning,
                )
        except (ConnectionRefusedError, OSError) as ee:
            warnings.warn(
                f"connection to tron was refused: {ee}. "
                "Some functionality will be limited.",
                clu.CluWarning,
            )

        self.timed_commands.start()

        return self

    async def stop(self):
        """Stops the client connection and running tasks."""

        if self._server.is_serving():
            self._server.stop()

        await self.timed_commands.stop()

        if self.tron:
            self.tron.stop()

    async def run_forever(self):
        """Runs the actor forever, keeping the loop alive."""

        await self._server.serve_forever()

    def new_user(self, transport: CustomTransportType):
        """Assigns userID to new client connection."""

        if transport.is_closing():
            if hasattr(transport, "user_id"):
                self.log.debug(f"user {transport.user_id} disconnected.")
                return self.transports.pop(transport.user_id)

        curr_ids: set[int] = set(self.transports.keys())
        user_id = 1 if len(curr_ids) == 0 else max(curr_ids) + 1

        transport.user_id = user_id

        self.transports[user_id] = transport

        # report user information and additional info
        self.show_new_user_info(user_id)

        return

    def new_command(self, transport: CustomTransportType, command_str: bytes):
        """Handles a new command received by the actor."""

        user_id = getattr(transport, "user_id", 0)
        command_str_s = command_str.decode().strip()

        if not command_str_s:
            return
        try:
            commander_id, command_id, command_body = parse_legacy_command(command_str_s)

            command = Command(
                command_string=command_body,
                commander_id=commander_id or user_id,
                command_id=command_id,
                consumer_id=self.name,
                actor=self,
                transport=transport,
            )
        except clu.CommandError:
            self.write(
                "f",
                {"error": f"Could not parse command {command_str_s!r}"},
            )
            return

        self.log.info(
            f"New command received: {command_body   !r} "
            f"(commander_id={commander_id!r}, command_id={command_id!r})"
        )

        return self.parse_command(command)

    @staticmethod
    def format_user_output(
        user_id: int,
        command_id: int,
        message_code: MessageCode,
        msg_str: Optional[str] = None,
    ) -> str:
        """Formats a string to send to users."""

        msg_str = "" if msg_str is None else " " + msg_str

        return f"{user_id} {command_id:d} {message_code.value:s}{msg_str:s}"

    def show_new_user_info(self, user_id: int):
        """Shows information for new users. Called when a new user connects."""

        self.show_user_info(user_id)
        self.show_version(user_id=user_id)

        transport = self.transports[user_id]
        peername = transport.get_extra_info("peername")[0]
        self.log.debug(f"user {user_id} connected from {peername!r}.")

    def show_user_info(self, user_id: int):
        """Shows user information including your user_id."""

        num_users = len(self.transports)
        if num_users == 0:
            return

        msg = {"yourUserID": user_id, "num_users": num_users}

        self.write("i", msg, user_id=user_id)
        self.show_user_list()

    def show_user_list(self):
        """Shows a list of connected users. Broadcast to all users."""

        user_id_list = sorted(self.transports.keys())
        for user_id in user_id_list:
            transport = self.transports[user_id]
            peername = transport.get_extra_info("peername")[0]
            msg = {"UserInfo": [user_id, peername]}
            self.write("i", msg)

    @staticmethod
    def get_user_command_id(
        command: Optional[Command] = None,
        user_id: int = 0,
        command_id: int = 0,
    ) -> Tuple[int, int]:
        """Returns commander_id, command_id based on user-supplied information.

        Parameters
        ----------
        command
            User command; used as a default for ``user_id`` and
            ``command_id``.
        user_id
            If `None` then use ``command.user_id``.
        command_id
            If `None` then use ``command.command_id``.

        Returns
        -------
        user_id, command_id
            The commander ID and the command ID, parsed from the inputs. If
            they cannot be determined, returns zeros.
        """

        cid = cast(int, command.command_id) if command else 0
        user_id = user_id or cid
        command_id = command_id or cid
        return (user_id, command_id)

    def show_version(self, user_id: int = 0):
        """Shows actor version."""

        msg = {"version": repr(self.version)}

        self.write("i", msg, user_id=user_id)

    def send_command(
        self,
        target: str,
        command_string: str,
        *args,
        commander: Optional[str] = None,
        command_id: Optional[int] = None,
        command: Optional[Command] = None,
        callback: Optional[Callable[[OpsReply], None]] = None,
        time_limit: Optional[float] = None,
    ):
        """Sends a command through the hub.

        Parameters
        ----------
        target
            The actor to command.
        command_string
            The command to send.
        args
            Arguments to concatenate to the command string.
        commander
            The commander string to send to Tron. If not provided, a valid
            string is built using the name of the actor and the target.
        command_id
            The command id. If `None`, a sequentially increasing value will
            be used. You should not specify a ``command_id`` unless you really
            know what you're doing.
        callback
            A callback to invoke with each reply received from the actor.
        time_limit
            A delay after which the command is marked as timed out and done.

        Examples
        --------
        These two are equivalent ::

            >>> actor.send_command('my_actor', 'do_something --now')
            >>> actor.send_command('my_actor', 'do_something', '--now')

        """

        if command and isinstance(command.commander_id, str):
            commander = command.commander_id
        else:
            commander = None

        if self.tron and self.tron.connected():
            command = self.tron.send_command(
                target,
                command_string,
                *args,
                commander=commander,
                mid=command_id,
                callback=callback,
                time_limit=time_limit,
            )
            return command

        else:
            raise clu.CluError("cannot connect to tron.")

    def write(
        self,
        message_code: MessageCode | str = "i",
        message: Optional[Dict[str, Any]] = None,
        command: Optional[Command] = None,
        user_id: int = 0,
        command_id: int = 0,
        concatenate: bool = True,
        broadcast: bool = False,
        validate: bool = True,
        write_to_log: bool = True,
        **kwargs,
    ):
        """Writes a message to user(s).

        Parameters
        ----------
        message_code
            The message code (e.g., ``'i'`` or ``':'``).
        message
            The keywords to be output. Must be a dictionary of pairs
            ``{keyword: value}``. If ``value`` is a list it will be converted
            into a comma-separated string. To prevent unexpected casting,
            it is recommended for ``value`` to always be a string.
        command
            User command; used as a default for ``user_id`` and
            ``command_id``. If the command is done, it is ignored.
        user_id
            The user (transport) to which to write. `None` defaults to 0.
        command_id
            If `None` then use ``command.command_id``.
        concatenate
            Concatenates all the keywords to be output in a single
            reply with the keyword-values joined with semicolons. Otherwise
            each keyword will be output as a different message.
        broadcast
            Whether to broadcast the reply. Equivalent to ``user_id=0``.
        validate
            Validate the reply against the actor model. This is ignored if the actor
            was not started with knowledge of its own schema.
        write_to_log
            Whether to write the reply to the log. Defaults to yes but
            it may be useful to prevent large repetitive replies cluttering
            the log.
        kwargs
            Keyword arguments that will be added to the message. If a keyword
            is both in ``message`` and in ``kwargs``, the value in ``kwargs``
            supersedes ``message``.
        """

        message_code = MessageCode(message_code)

        reply = BaseActor.write(
            self,
            message_code=message_code,
            message=message,
            command=command,
            broadcast=broadcast,
            validate=validate,
            emit=False,
            expand_exceptions=False,
            **kwargs,
        )

        if kwargs.get("silent", False) is False:
            self._write_internal(
                reply,
                user_id=user_id,
                command_id=command_id,
                concatenate=concatenate,
                write_to_log=write_to_log,
            )

    def _write_internal(
        self,
        reply: Reply,
        user_id=0,
        command_id=0,
        concatenate=True,
        write_to_log: bool = True,
    ):
        """Writes reply to users.

        Parameters
        ----------
        reply
            The reply object to output to users.
        user_id
            The user to which we are replying.
        command_id
            The command emitting this message.
        write_to_log
            Whether to write the reply to the log. Defaults to yes but
            it may be useful to prevent large repetitive replies cluttering
            the log.

        """

        command = cast(Command, reply.command)
        message = reply.message

        # For a reply, the commander ID is the user assigned to the transport
        # that issues this command.
        transport = command.transport if command else None
        user_id = (transport.user_id if transport else None) or user_id

        if reply.broadcast:
            user_id = 0
            command_id = 0

        user_id, command_id = self.get_user_command_id(
            command=command,
            user_id=user_id,
            command_id=command_id,
        )

        lines = []
        for keyword in message:
            try:
                value = clu.format_value(message[keyword])
            except BaseException as err:
                raise TypeError(f"Cannot format keyword {keyword!r} " + str(err))

            if value.strip() == "":
                lines.append(f"{keyword}")
            else:
                lines.append(f"{keyword}={value}")

        if concatenate:
            lines = ["; ".join(lines)]

        for line in lines:
            full_msg_str = self.format_user_output(
                user_id,
                command_id,
                reply.message_code,
                line,
            )
            msg = (full_msg_str + "\n").encode()

            if user_id is None or user_id == 0 or transport is None:
                for transport in self.transports.values():
                    transport.write(msg)
            else:
                global_transport = self.transports.get(transport.user_id, None)
                if global_transport is not None and global_transport == transport:
                    transport.write(msg)

            if self.log and write_to_log:
                log_reply(self.log, reply.message_code, full_msg_str)


class LegacyActor(ClickParser, BaseLegacyActor):
    """A legacy actor that uses the `.ClickParser`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.tron:
            self.parser.add_command(tron_reconnect)
