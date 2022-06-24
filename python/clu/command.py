#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-17
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
import warnings
from contextlib import suppress

from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
    cast,
)

import clu
import clu.base
from clu.exceptions import CluWarning, CommandError
from clu.tools import CommandStatus, StatusMixIn


__all__ = [
    "BaseCommand",
    "Command",
    "parse_legacy_command",
    "TimedCommand",
    "TimedCommandList",
    "FakeCommand",
]


Actor_co = TypeVar("Actor_co", bound="clu.base.BaseActor")
Future_co = TypeVar("Future_co", bound="BaseCommand")
Reply_co = TypeVar("Reply_co", bound="clu.base.Reply")

if sys.version_info >= (3, 9, 0):
    Future = asyncio.Future
else:

    class Future(asyncio.Future, Generic[Future_co]):
        pass


class ReplyList(List[Reply_co]):
    """A list of replies to a command."""

    def get(self, keyword: str):
        """Return the value of the reply that matches the key."""

        for reply in self:
            if keyword in reply.message:
                return reply.message[keyword]

        raise KeyError(f"Keyword {keyword} not found.")


class BaseCommand(
    Future[Future_co],
    StatusMixIn[CommandStatus],
    Generic[Actor_co, Future_co],
):
    """Base class for commands of all types (user and device).

    A `BaseCommand` instance is a `~asyncio.Future` whose result gets set
    when the status is done (either successfully or not).

    Parameters
    ----------
    commander_id
        The ID of the commander issuing this command. Can be a string or an
        integer. Normally the former is used for new-style actor and the latter
        for legacy actors.
    command_id
        The ID associated to this command. As with the commander_id, it can be
        a string or an integer
    consumer_id
        The actor that is consuming this command. Normally this is our own
        actor but if we are commanding another actor ``consumer_id`` will
        be the destination actor.
    actor
        The actor instance associated to this command.
    parent
        Another `.BaseCommand` object that is issuing this subcommand.
        Messages emitted by the command will use the parent ``command_id``.
    reply_callback
        A callback that gets called when a client command receives a reply from the
        actor.
    status_callback
        A function to call when the status changes.
    call_now
        Whether to call ``status_callback`` when initialising the command.
    default_keyword
        The keyword to use when writing a message that does not specify a
        keyword.
    silent
        A silent command will call the actor ``write`` method with ``silent=True``,
        which will update the internal model and record all the output replies but
        will not write them to the users.
    time_limit
        Time out the command if it has been running for this long.
    loop
        The event loop.

    """

    def __init__(
        self,
        commander_id: Union[int, str, None] = None,
        command_id: Union[int, str] = 0,
        consumer_id: Union[int, str] = 0,
        actor: Optional[Actor_co] = None,
        parent: Optional[BaseCommand[Actor_co, Future_co]] = None,
        reply_callback: Optional[Callable[[Any], None]] = None,
        status_callback: Optional[Callable[[CommandStatus], Any]] = None,
        call_now: bool = False,
        default_keyword: str = "text",
        silent: bool = False,
        time_limit: float | None = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):

        self.commander_id = commander_id
        self.consumer_id = consumer_id
        self.command_id = command_id

        # Casting here so that we can type Command[SomeActor] and not have to
        # assert command.actor every time.
        self.actor = cast(Actor_co, actor)
        self.parent = parent

        self.silent = silent

        self._reply_callback = reply_callback

        self.default_keyword = default_keyword
        self.loop = loop or asyncio.get_event_loop()

        #: A list of replies this command has received. The type of
        #: reply object depends on the actor or client issuing the command.
        self.replies = ReplyList([])

        asyncio.Future.__init__(self)

        self._status: CommandStatus
        StatusMixIn.__init__(
            self,
            CommandStatus,
            initial_status=CommandStatus.READY,
            callback_func=status_callback,
            call_now=call_now,
        )

        self._timer_handler = None
        if time_limit:
            self._timer_handler = asyncio.get_running_loop().call_later(
                time_limit,
                self.set_status,
                CommandStatus.TIMEDOUT,
            )

    @property
    def status(self) -> CommandStatus:
        """Returns the status."""

        return self._status

    @status.setter
    def status(self, status: CommandStatus):
        """Sets the status. A message is output to the users.

        This setter calls `.set_status` with an empty message to the users.

        Parameters
        ----------
        status
            The status to set, either as a `CommandStatus` value or the
            integer associated with the maskbit. If ``value`` is a string,
            loops over the bits in `CommandStatus` and assigns the one whose
            name matches.
        """

        self.set_status(status)

    def set_status(
        self,
        status: Union[CommandStatus, str],
        message: Dict[str, Any] | str | None = None,
        silent: bool = False,
        **kwargs,
    ) -> BaseCommand:
        """Same as `.status` but allows to specify a message to the users."""

        assert self.status

        # Don't do anything if the command is done. This means the command
        # finished before the timeout happened.
        if status == CommandStatus.TIMEDOUT and self.done():
            return self

        if self.status.is_done:
            raw_command_string = getattr(self, "raw_command_string", "NA")
            warnings.warn(
                f"{raw_command_string}: cannot modify a "
                f"done command with status {status!r}.",
                CluWarning,
            )
            return self

        if isinstance(status, str):
            for bit in self.flags:
                assert bit.name
                if status.lower() == bit.name.lower():
                    status = bit
                    break

        status = self.flags(status)

        try:
            is_flag = status in self.flags
            if not is_flag:
                raise TypeError()
        except TypeError:
            raise TypeError(f"Status {status!r} is not a valid command status.")

        if status != self._status:

            status_code = status.code
            if status_code is None:
                raise ValueError(f"Invalid status code {status_code!r}.")

            if isinstance(message, str) and status_code in ["f", "e"]:
                message = {"error": message}

            if self.actor and not silent:
                self.write(status_code, message, **kwargs)

            self._status = status

            self.do_callbacks()

            # If the command is done, set the result of the future.
            if self._status.is_done and not self.done():
                self.set_result(self)  # type: ignore
                if self._timer_handler:
                    self._timer_handler.cancel()

            # Set the status watcher
            if self.watcher is not None:
                self.watcher.set()

        return self

    def finish(self, *args, **kwargs):
        """Convenience method to mark a command `~.CommandStatus.DONE`."""

        self.set_status(CommandStatus.DONE, *args, **kwargs)
        return self

    def fail(self, *args, **kwargs):
        """Convenience method to mark a command `~.CommandStatus.FAILED`."""

        self.set_status(CommandStatus.FAILED, *args, **kwargs)
        return self

    def debug(self, *args, **kwargs):
        """Writes a debug-level message."""

        self.write("d", *args, **kwargs)

    def info(self, *args, **kwargs):
        """Writes an info-level message."""

        self.write("i", *args, **kwargs)

    def warning(self, *args, **kwargs):
        """Writes a warning-level message."""

        self.write("w", *args, **kwargs)

    def error(self, *args, **kwargs):
        """Writes an error-level message (does not fail the command)."""

        self.write("e", *args, **kwargs)

    def write(
        self,
        message_code: str | int = "i",
        message: Optional[Union[Dict[str, Any], str]] = None,
        broadcast: bool = False,
        **kwargs,
    ):
        """Writes to the user(s).

        Parameters
        ----------
        message_code
            The message code (e.g., ``'i'`` or ``':'``).
        message
            The text to be output. If `None`, only the code will be written.
        """

        if message is None:
            message = {}
        elif isinstance(message, dict):
            pass
        elif isinstance(message, str):
            keyword = "error" if message_code in ["f", "e"] else self.default_keyword
            message = {keyword: message}
        elif isinstance(message, Exception):
            message = {"error": message}
        else:
            raise ValueError(f"invalid message {message!r}")

        if not self.actor:
            raise clu.CommandError(
                "An actor has not been defined for "
                "this command. Cannot write to users."
            )

        command = self if not self.parent else self.parent

        # If the message code is an integer, interpret that as if it's a logging
        # level and translate it to SDSS codes.
        if isinstance(message_code, int):
            if message_code == logging.DEBUG:
                message_code = "d"
            elif message_code == logging.INFO:
                message_code = "i"
            elif message_code == logging.WARNING:
                message_code = "w"
            elif message_code == logging.ERROR:
                message_code = "e"
            else:
                raise ValueError(f"Invalid message code {message_code}.")

        # If the parent has a command, do not output : or f since it would
        # confuse the stream and potentially Tron.
        if self.parent:
            if message_code == ">":
                # The parent is already running and > never includes a message.
                return
            if message_code == ":":
                message_code = "i"
                if kwargs == {} and (message == {} or not message):
                    return
            elif message_code == "f":
                message_code = "e"

        self.actor.write(
            message_code,
            message=message,
            command=command,
            broadcast=broadcast,
            silent=self.silent,
            **kwargs,
        )

    def send_command(
        self,
        target: str,
        command_string: str,
        new_command: bool = True,
        *args,
        **kwargs,
    ) -> BaseCommand[Actor_co, BaseCommand] | Awaitable[BaseCommand]:
        """Sends a command to an actor using the commander ID of this command."""

        if self.actor is None:
            raise CommandError("The actor need to be defined to send commands.")

        return self.actor.send_command(
            target,
            command_string,
            *args,
            command=self if new_command is False else None,
            **kwargs,
        )


class Command(BaseCommand[Actor_co, "Command"]):
    """A command from a user.

    Parameters
    ----------
    command_string
        The string that defines the body of the command.
    transport
        The TCP transport associated with this command (only relevant
        for `.LegacyActor` commands).
    """

    def __init__(
        self,
        command_string: str = "",
        transport: Optional[Any] = None,
        **kwargs,
    ):

        BaseCommand.__init__(self, **kwargs)

        #: The raw command string.
        self.raw_command_string = command_string

        #: The body of the command.
        self.body = command_string

        if not self.actor and self.parent:
            self.actor = self.parent.actor

        #: The `~click.Context` running this command. Only relevant if
        #: using the built-in click-based parser.
        self.ctx = None

        self.transport = transport

    def child_command(self, command_string):
        """Starts a sub-command on the actor currently running this command.

        The practical effect is to run another of the same actor's commands as
        if it were part of the current `.Command`.

        """

        return Command(
            command_string,
            actor=self.actor,
            commander_id=self.actor.name,
            parent=self,
        ).parse()

    def parse(self) -> Command:
        """Parses the command."""

        if not isinstance(self.actor, clu.base.BaseActor):
            raise clu.CluError("the actor is not defined. Cannot parse command.")

        self.actor.parse_command(self)

        return self

    def __str__(self):
        return (
            f"<Command (commander_id={self.commander_id!r}, "
            f"command_id={self.command_id!r}, body={self.body!r})>"
        )


def parse_legacy_command(command_string: str) -> Tuple[Union[str, None], int, str]:
    """Parses a command received by a legacy actor.

    Parameters
    ----------
    command_string
        The command to parse, including an optional header.

    Returns
    -------
    command_id, command_body
        The command ID, and the command body parsed from the command
        string.

    """

    _HEADER_BODY_RE = re.compile(
        r"(?:([a-z0-9]*\.[a-z0-9_\.]+)\s+)?"
        r"(?:(\d+)(?:\s+\d+)?\s+)?"
        r"(?:([a-z_].*|--help))?$",
        re.IGNORECASE,
    )

    command_match = _HEADER_BODY_RE.match(command_string)
    if not command_match:
        raise clu.CommandError(f"Could not parse command {command_string!r}")

    commander, command_id_str, command_body = command_match.groups()

    if command_id_str:
        command_id = int(command_id_str)
    else:
        command_id = 0

    command_body = command_body.strip()

    return commander, command_id, command_body


class TimedCommandList(list):
    """A list of `.TimedCommand` objects that will be executed on a loop.

    Parameters
    ----------
    actor
        The actor in which the commands are to be run.
    resolution
        In seconds, how frequently to check if any of the `.TimedCommand` must
        be executed.

    """

    def __init__(
        self,
        actor: clu.base.BaseActor,
        resolution=0.5,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):

        self.resolution = resolution
        self.actor = actor
        self.loop = loop or asyncio.get_event_loop()

        self._task: Optional[asyncio.Task] = None

        list.__init__(self, [])

    def add_command(self, command_string: str, **kwargs):
        """Adds a new `.TimedCommand`."""

        self.append(TimedCommand(command_string, **kwargs))

    async def poller(self):
        """The polling loop."""

        current_time = time.time()
        first_time = True

        while True:

            for timed_command in self:
                elapsed = current_time - timed_command.last_run
                if first_time or elapsed > timed_command.delay:
                    timed_command_task = self.loop.create_task(
                        timed_command.run(self.actor)
                    )
                    timed_command_task.add_done_callback(timed_command.done)

            first_time = False

            self._sleep_task = self.loop.create_task(asyncio.sleep(self.resolution))

            await self._sleep_task
            current_time += self.resolution

    def start(self) -> TimedCommandList:
        """Starts the loop."""

        if self.running:
            raise RuntimeError("poller is already running.")

        self._task = self.loop.create_task(self.poller())

        return self

    async def stop(self):
        """Cancel the poller."""

        if not self.running:
            return

        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    @property
    def running(self) -> bool:
        """Returns `True` if the poller is running."""

        if self._task and not self._task.cancelled():
            return True

        return False


class TimedCommand(object):
    """A command to be executed on a loop.

    Parameters
    ----------
    command_string
        The command string to run.
    delay
        How many seconds to wait between repeated calls.
    first_silent
        Runs the command in silent mode the first one (useful to internally update the
        model).

    """

    def __init__(self, command_string: str, delay: float = 1, first_silent=False):

        self.command_string = command_string
        self.delay = delay

        self.last_run = 0.0
        self.is_running = False

        self.first_silent = first_silent

    async def run(self, actor: clu.base.BaseActor):
        """Run the command."""

        if self.is_running:
            return

        silent = True if self.first_silent and self.last_run == 0.0 else False

        self.is_running = True

        await Command(
            self.command_string,
            actor=actor,
            commander_id=f".{actor.name}",
            silent=silent,
        ).parse()

    def done(self, task):
        """Marks the execution of a command."""

        self.last_run = time.time()
        self.is_running = False


class FakeCommand(BaseCommand):
    """A fake command that output to a logger."""

    def __init__(self, log: logging.Logger, actor=None):

        self.log = log

        super().__init__(actor=actor)

    def write(
        self,
        message_code: str = "i",
        message: Optional[Union[Dict[str, Any], str]] = None,
        **kwargs,
    ):

        if message_code == "d":
            level = logging.DEBUG
        elif message_code == "i":
            level = logging.INFO
        elif message_code == "w":
            level = logging.WARNING
        elif message_code in ["f", "e"]:
            level = logging.ERROR
        else:
            return

        if message is None:
            message = {}
        elif isinstance(message, dict):
            pass
        elif isinstance(message, str):
            keyword = "error" if message_code in ["f", "e"] else self.default_keyword
            message = {keyword: message}
        elif isinstance(message, Exception):
            message = {"error": message}
        else:
            raise ValueError(f"invalid message {message!r}")

        message.update(kwargs)

        self.log.log(level, str(message))
