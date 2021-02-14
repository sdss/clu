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

from typing import Any, Callable, List, Optional

from clu.base import BaseClient
from clu.command import Command, CommandStatus
from clu.model import BaseModel, Property
from clu.protocol import open_connection

from .types.keys import KeysDictionary
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
        value: List[Any] = [],
        key: Optional[str] = None,
        model: Optional[TronModel] = None,
        callback: Optional[Callable[[TronKey], Any]] = None,
    ):

        super().__init__(name, value=value, model=model, callback=callback)

        self.key = key

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
        function is called with the instance of `.TronModel` and the
        `.TronKey` that has changed. If the callback is a coroutine,
        it is scheduled as a task.
    log
        Where to log messages.
    """

    def __init__(
        self,
        keydict: KeysDictionary,
        callback: Callable[[TronModel], Any] = None,
        log: Optional[logging.Logger] = None,
    ):

        super().__init__(keydict.name, callback=callback, log=log)

        self.keydict = keydict

        for key in self.keydict.keys:
            key = self.keydict.keys[key]
            self[key.name] = TronKey(key.name, key=key, model=self)

    def parse_reply(self, reply):
        """Parses a reply and updates the datamodel."""

        for reply_key in reply.keywords:

            key_name = reply_key.name.lower()
            if key_name not in self.keydict:
                raise ParseError(
                    "Cannot parse unknown keyword " f"{self.name}.{reply_key.name}."
                )

            # When parsed the values in reply_key are string. After consuming
            # it with the Key, the values become typed values.
            result = self.keydict.keys[key_name].consume(reply_key)

            if not result:
                raise ParseError(
                    "Failed parsing keyword " f"{self.name}.{reply_key.name}."
                )

            self[key_name].value = [value.native for value in reply_key.values]
            self[key_name].key = reply_key

            self.notify(self)


class TronLoggingFilter(logging.Filter):
    """Logs issues with the Tron parser only to the file logger."""

    def filter(self, record):
        return not record.getMessage().startswith("Failed parsing reply")


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

        self._parser = None
        self.rparser: Any = ReplyParser()

        self._client = None
        self.running_commands = {}

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

        self._client = await open_connection(self.host, self.port)

        self._parser = asyncio.create_task(self._handle_reply())

        if get_keys:
            asyncio.create_task(self.get_keys())

        return self

    def stop(self):
        """Closes the connection."""

        self._client.close()
        self._parser.cancel()

    async def run_forever(self):

        # Keep alive until the connection is closed.
        await self._client.writer.wait_closed()

    def send_command(self, target, command_string, commander="tron.tron", mid=None):
        """Sends a command through the hub.

        Parameters
        ----------
        target
            The actor to command.
        command_string
            The command to send.
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
        """

        mid = mid or self._mid

        # The mid must be a 32-bit unsigned number.
        if mid >= 2 ** 32:
            self._mid = mid = mid % 2 ** 32

        command_string = f"{commander} {mid} {target} {command_string}\n"

        command = Command(command_string=command_string)
        command.set_status("RUNNING")
        self.running_commands[mid] = command

        self._client.writer.write(command_string.encode())

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

    async def _handle_reply(self):
        """Tracks new replies from Tron and updates the model."""

        while True:

            line = await self._client.reader.readline()

            if self._client.reader.at_eof():
                self.log.error(
                    "Client received EOF. This usually means that "
                    "Tron is not responding. Closing the connection."
                )
                self.stop()
                return

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
                if status.is_done:
                    self.running_commands[mid].replies.append(reply)
                    command = self.running_commands.pop(mid)
                    command.set_status(status)
