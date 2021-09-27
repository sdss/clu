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
import time
import warnings

from typing import Any, Callable, List, Optional

from clu.base import BaseClient
from clu.command import Command, CommandStatus
from clu.exceptions import CluWarning
from clu.model import BaseModel, Property
from clu.protocol import ReconnectingTCPClientProtocol

from .types.keys import Key, KeysDictionary
from .types.messages import Keyword, Reply
from .types.parser import ParseError, ReplyParser


__all__ = ["TronConnection", "TronModel", "TronKey"]


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
        callback: Callable[[TronModel], Any] = None,
    ):

        super().__init__(keydict.name, callback=callback)

        self.keydict = keydict

        for key in self.keydict.keys:
            key = self.keydict.keys[key]
            self[key.name] = TronKey(key.name, key, model=self)

    def reload(self):
        """Reloads the model. Clears callbacks."""

        model = self.keydict.name
        keydict = KeysDictionary.load(model)

        self.__init__(keydict)

    def parse_reply(self, reply):
        """Parses a reply and updates the datamodel."""

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

            self[key_name].update_keyword(reply_key)

            self.notify(self, self[key_name].copy())


class TronLoggingFilter(logging.Filter):
    """Logs issues with the Tron parser only to the file logger."""

    def filter(self, record):
        return not record.getMessage().startswith("Failed parsing reply")


class TronClientProtocol(ReconnectingTCPClientProtocol):
    """A reconnecting protocol for the Tron connection."""

    def __init__(self, on_received, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_received = on_received

    def data_received(self, data):
        self._loop.call_soon(self._on_received, data)


class TronConnection(BaseClient):
    """Allows to send commands to Tron and manages the feed of replies.

    Parameters
    ----------
    name
        The name of the client.
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
        host: str,
        port: int = 6093,
        name: str = "tron",
        models: List[str] = [],
        **kwargs,
    ):

        super().__init__(name, **kwargs)

        self.host = host
        self.port = port

        self._mid = 1

        models = models or []

        #: dict: The `KeysDictionary` associated with each actor to track.
        self.keyword_dicts = {model: KeysDictionary.load(model) for model in models}

        #: dict: The model and values of each actor being tracked.
        self.models = {model: TronModel(self.keyword_dicts[model]) for model in models}

        self.rparser: Any = ReplyParser()

        self.transport: asyncio.Transport | None = None
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

        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await loop.create_connection(  # type: ignore
            lambda: TronClientProtocol(self._handle_reply),
            self.host,
            self.port,
        )

        if get_keys:
            asyncio.create_task(self.get_keys())

        return self

    def stop(self):
        """Closes the connection."""

        assert self.transport

        self.transport.close()

    def connected(self):
        """Checks whether the client is connected."""

        if self.transport is None:
            return False

        return not self.transport.is_closing()

    async def run_forever(self):  # pragma: no cover

        assert self.transport

        # Keep alive until the connection is closed.
        while True:
            await asyncio.sleep(1)
            if self.transport.is_closing():
                return

    def send_command(
        self,
        target,
        command_string,
        *args,
        commander=".client",
        mid=None,
        callback: Optional[Callable[[Reply], None]] = None,
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
            to parse.
        mid
            The message id. If `None`, a sequentially increasing value will
            be used. You should not specify a ``mid`` unless you really know
            what you're doing.
        callback
            A callback to invoke with each reply received from the actor.

        Examples
        --------
        These two are equivalent ::

            >>> tron.send_command('my_actor', 'do_something --now')
            >>> tron.send_command('my_actor', 'do_something', '--now')

        """

        assert self.transport

        mid = mid or self._mid

        # The mid must be a 32-bit unsigned number.
        if mid >= 2 ** 32:
            self._mid = mid = mid % 2 ** 32

        if len(args) > 0:
            command_string += " " + " ".join(map(str, args))

        command_string = f"{commander} {mid} {target} {command_string}\n"

        command = Command(command_string=command_string, reply_callback=callback)
        self.running_commands[mid] = command

        self.transport.write(command_string.encode())

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
                reply = self.rparser.parse(line)
            except ParseError:
                self.log.warning(f"Failed parsing reply '{line.strip()}'.")
                continue

            actor = reply.header.actor

            # The keys command returns keywords as if from the actor
            # keys_<actor> (e.g. keys_tcc).
            if actor.startswith("keys_"):
                actor = actor.split("_")[1]

            if actor in self.models:
                try:
                    self.models[actor].parse_reply(reply)
                except ParseError as ee:
                    self.log.warning(
                        f"Failed parsing reply {reply!r} with error: {ee!s}"
                    )

            mid = reply.header.commandId
            status = CommandStatus.code_to_status(reply.header.code.lower())

            if mid in self.running_commands:
                self.running_commands[mid].replies.append(reply)
                self.running_commands[mid].set_status(status)
                if self.running_commands[mid]._reply_callback is not None:
                    self.running_commands[mid]._reply_callback(reply)
                if status.is_done:
                    self.running_commands.pop(mid)
