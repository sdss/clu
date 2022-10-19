#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-10
# @Filename: tron.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import logging
import re
import time
import warnings
from threading import Lock

from typing import Any, Callable, List, Optional

import clu.base
from clu.command import Command, CommandStatus
from clu.exceptions import CluWarning
from clu.model import BaseModel, Property
from clu.parsers.click import command_parser
from clu.protocol import ReconnectingTCPClientProtocol

from .types.keys import Key, KeysDictionary
from .types.messages import Keyword, Reply
from .types.parser import ParseError, ReplyParser


__all__ = ["TronConnection", "TronModel", "TronKey"]


@command_parser.command(name="tron-reconnect")
async def tron_reconnect(*args):
    """Pings the actor."""

    command = args[0]

    if command.actor.tron is None:
        return command.fail("Tron instance not set.")

    command.actor.tron.stop()
    await asyncio.sleep(0.5)

    await command.actor.tron.start()

    return command.finish()


class TronKey(Property):
    """A Tron model key with callbacks.

    Similar to `.Property` but stores the original key with the keyword
    datamodel.
    """

    def __init__(
        self,
        name: str,
        key: Key,
        keyword: Optional[Keyword] = None,
        model: Optional[TronModel] = None,
        callback: Optional[Callable[[TronKey], Any]] = None,
    ):

        initial_value = [None] * len(key.typedValues.vtypes)
        super().__init__(name, value=initial_value, model=model, callback=callback)

        self.key = key
        self.keyword = None

        self.update_keyword(keyword)

    def update_keyword(self, keyword: Optional[Keyword]):
        """Updates the keyword and value."""

        if keyword is None:
            return

        self.keyword = keyword
        self.value = [value.native for value in keyword.values]

    def __getitem__(self, sl):
        return self.value.__getitem__(sl)

    def __len__(self):
        return len(self.value)


class TronModel(BaseModel[TronKey]):
    """A JSON-compliant model for actor keywords.

    Parameters
    ----------
    keydict
        A dictionary of keys that define the datamodel.
    callback
        A function or coroutine to call when the datamodel changes. The
        function is called with the instance of `.TronModel` and the modified keyword.
        If the callback is a coroutine, it is scheduled as a task.

    """

    def __init__(
        self,
        keydict: KeysDictionary,
        callback: Optional[Callable[[TronModel], Any]] = None,
    ):

        super().__init__(keydict.name, callback=callback)

        self.keydict = keydict

        for key in self.keydict.keys:
            key = self.keydict.keys[key]
            self[key.name] = TronKey(key.name, key, model=self)

        self._lock = Lock()

    def reload(self):
        """Reloads the model. Clears callbacks."""

        model = self.keydict.name
        keydict = KeysDictionary.load(model)

        self.__init__(keydict)

    def parse_reply(self, reply):
        """Parses a reply and updates the datamodel."""

        parsed: dict[str, Any] = {}

        with self._lock:
            for reply_key in reply.keywords:

                self.last_seen = time.time()

                key_name = reply_key.name.lower()
                if key_name not in self.keydict:
                    warnings.warn(
                        f"Cannot parse unknown keyword {self.name}.{reply_key.name}.",
                        CluWarning,
                    )
                    continue

                # When parsed the values in reply_key are string. After consuming
                # it with the Key, the values become typed values.
                result = self.keydict.keys[key_name].consume(reply_key)

                if not result:
                    warnings.warn(
                        f"Failed parsing keyword {self.name}.{reply_key.name}.",
                        CluWarning,
                    )
                    continue

                self[key_name].update_keyword(reply_key)
                parsed[key_name] = self[key_name].value.copy()

                self.notify(self.flatten(), self[key_name].copy())

        return parsed


class TronLoggingFilter(logging.Filter):
    """Logs issues with the Tron parser only to the file logger."""

    def filter(self, record):
        return not record.getMessage().startswith("Failed parsing reply")


class TronClientProtocol(ReconnectingTCPClientProtocol):
    """A reconnecting protocol for the Tron connection."""

    def __init__(self, on_received, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_received = on_received
        self.transport: asyncio.Transport | None = None

    def data_received(self, data):
        asyncio.get_event_loop().call_soon(self._on_received, data)

    def connection_made(self, transport: asyncio.Transport):
        self.transport = transport


class TronConnection(clu.base.BaseClient):
    """Allows to send commands to Tron and manages the feed of replies.

    Parameters
    ----------
    commander
        The name of the commander that will send commands to Tron. Must be
        in the form ``program.user``, for example ``foo.bar``.
    host
        The host on which Tron is running.
    port
        The port on which Tron is running.
    models
        A list of strings with the actors whose models will be tracked.
    kwargs
        Arguments to be passed to `.BaseClient`.
    """

    def __init__(
        self,
        commander: str,
        host: str,
        port: int = 6093,
        name: str = "tron",
        models: List[str] = [],
        **kwargs,
    ):

        super().__init__(name, **kwargs)

        self.commander = commander
        if not re.match(r"[A-Za-z_]+\.[A-Za-z_]+", self.commander):
            raise ValueError("Invalid commander format.")

        self.host = host
        self.port = port

        self._mid = 1

        models = models or []

        #: dict: The `KeysDictionary` associated with each actor to track.
        self.keyword_dicts = {model: KeysDictionary.load(model) for model in models}

        #: dict: The model and values of each actor being tracked.
        self.models = {model: TronModel(self.keyword_dicts[model]) for model in models}

        self.rparser: Any = ReplyParser()

        self.protocol: TronClientProtocol | None = None

        self.running_commands = {}

        self.buffer = b""

        # We want to log problems with the Tron parser, but not to the console.
        if self.log.sh:
            self.log.sh.addFilter(TronLoggingFilter())

    async def start(self, get_keys=True):
        """Starts the connection to Tron.

        Parameters
        ----------
        get_keys : bool
            If `True`, gets all the keys in the models.
        """

        self.protocol = TronClientProtocol(
            self._handle_reply,
            self.host,
            self.port,
        )
        await self.protocol._connect()

        if not self.protocol.connected:
            self.log.error(f"Failed connecting to Tron on ({self.host}, {self.port})")
            return

        if get_keys:
            asyncio.create_task(self.get_keys())

        return self

    def stop(self):
        """Closes the connection."""

        if self.protocol:
            self.protocol.stop_trying()

        if self.protocol and self.protocol.transport:
            self.protocol.transport.close()

        self.protocol = None

    def connected(self):
        """Checks whether the client is connected."""

        if self.protocol and self.protocol.connected:
            return True

        return False

    async def run_forever(self):  # pragma: no cover

        assert self.protocol and self.connected()

        # Keep alive until the connection is closed.
        while True:
            await asyncio.sleep(1)
            if self.protocol is None:
                return

    def send_command(
        self,
        target,
        command_string,
        *args,
        commander=None,
        mid=None,
        callback: Optional[Callable[[Reply], None]] = None,
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
            The actor or client sending the command. The format for Tron is
            "commander message_id target command" where commander needs to
            start with a letter and have a program and a user joined by a dot.
            Otherwise the command will be accepted but the reply will fail
            to parse. If ``commander=None``, the instance ``commander`` value
            will be used.
        mid
            The message id. If `None`, a sequentially increasing value will
            be used. You should not specify a ``mid`` unless you really know
            what you're doing.
        callback
            A callback to invoke with each reply received from the actor.
        time_limit
            A delay after which the command is marked as timed out and done.

        Examples
        --------
        These two are equivalent ::

            >>> tron.send_command('my_actor', 'do_something --now')
            >>> tron.send_command('my_actor', 'do_something', '--now')

        """

        assert self.protocol and self.protocol.transport and self.connected()

        mid = mid or self._mid

        # The mid must be a 32-bit unsigned number.
        if mid >= 2**32:
            self._mid = mid = mid % 2**32

        if len(args) > 0:
            command_string += " " + " ".join(map(str, args))

        commander = commander or self.commander

        command_string = f"{commander} {mid} {target} {command_string}\n"

        command = Command(
            command_string=command_string,
            reply_callback=callback,
            time_limit=time_limit,
            commander_id=commander,
        )
        self.running_commands[mid] = command

        self.protocol.transport.write(command_string.encode())

        self._mid += 1

        return command

    async def get_keys(self):
        """Gets all the keys for the models being tracked."""

        # Number of keys to be requested at once
        n_keys = 10

        for model in self.models.values():

            actor = model.name
            keys = [key.lower() for key in model]

            for ii in range(0, len(keys), n_keys):

                keys_to_request = keys[ii : ii + n_keys]

                if len(keys_to_request) == 0:
                    break

                keys_joined = " ".join(keys_to_request)

                command_string = f"getFor={actor} {keys_joined}"

                self.send_command("keys", command_string)

    def _handle_reply(self, data: bytes):
        """Tracks new replies from Tron and updates the model."""

        self.buffer += data

        lines = self.buffer.splitlines()
        if not self.buffer.endswith(b"\n"):
            self.buffer = lines.pop()
        else:
            self.buffer = b""

        for line in lines:
            try:
                # Do not strip here or that will cause parsing problems.
                line = line.decode()
                reply: Reply = self.rparser.parse(line)
            except ParseError:
                self.log.warning(f"Failed parsing reply '{line.strip()}'.")
                continue

            reply_actor = reply.header.actor
            reply_commander_id = reply.header.cmdrName

            # The keys command returns keywords as if from the actor
            # keys_<actor> (e.g. keys_tcc).
            if reply_actor.startswith("keys_"):
                reply_actor = reply_actor.split("_")[1]

            parsed_data = {}
            if reply_actor in self.models:
                try:
                    parsed_data = self.models[reply_actor].parse_reply(reply)
                except ParseError as ee:
                    self.log.warning(
                        f"Failed parsing reply {reply!r} with error: {ee!s}"
                    )
            else:
                # Fallback in case the actor of the reply is not in the models.
                # In this case the values will be strings.
                parsed_data = {kw.name: kw.values for kw in reply.keywords}

            mid = reply.header.commandId
            status = CommandStatus.code_to_status(reply.header.code.lower())

            if mid in self.running_commands:
                # We may be receiving messages from a command with the same MID
                # that's not managed by this instance of the tron client, so we
                # also check the commander.
                if self.running_commands[mid].commander_id == reply_commander_id:
                    self.running_commands[mid].replies.append(
                        clu.base.Reply(
                            message={k: v for k, v in parsed_data.items()},
                            message_code=reply.header.code.lower(),
                            command=self.running_commands[mid],
                            validated=True,
                            keywords=reply.keywords,
                        )
                    )
                    self.running_commands[mid].set_status(status)
                    if self.running_commands[mid]._reply_callback is not None:
                        self.running_commands[mid]._reply_callback(reply)
                    if status.is_done:
                        self.running_commands.pop(mid)
