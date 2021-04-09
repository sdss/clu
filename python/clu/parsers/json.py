#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-04-08
# @Filename: json.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import json

from typing import Any, Callable, Coroutine, Dict, List, TypeVar

from ..command import Command


__all__ = ["JSONParser"]


T = TypeVar("T", bound=Command)


DEFAULT_CALLBACKS = {}


class JSONParser:
    """A parser that receives commands and arguments as a JSON string.

    See :ref:`json-parser` for details on implementation and use-cases.

    """

    #: list: Additional arguments to be passed to each command in the parser.
    #: Note that the command is always passed first.
    parser_args: List[Any] = []

    #: dict: Mapping of command verb to callback coroutine.
    callbacks: Dict[str, Callable[..., Coroutine]] = DEFAULT_CALLBACKS

    def parse_command(self, command: T) -> T:
        """Parses a user command.

        The command string must be a serialised JSON-like string that contains at
        least a keyword ``command`` with the name of the callback, and any number of
        additional arguments which will be passed to it.
        """

        # This will pass the command as the first argument for each command.
        # If self.parser_args is defined, those arguments will be passed next.
        parser_args = [command]
        parser_args += self.parser_args

        # Empty command. Just finish the command.
        if not command.body:
            command.done()
            return command

        command.set_status(command.status.RUNNING)

        try:
            payload = json.loads(command.body)
        except json.JSONDecodeError as err:
            return command.fail(
                error=f"Cannot deserialise command string {command.body!r}: {err}"
            )

        if "command" not in payload:
            return command.fail(
                error=f"Command {command.body!r} does not contain "
                "a 'command' parameter."
            )

        verb = payload.pop("command")
        if verb not in self.callbacks:
            return command.fail(error=f"Cannot find a callback for command {verb!r}.")
        elif not asyncio.iscoroutinefunction(self.callbacks[verb]):
            return command.fail(error=f"Callback {verb!r} is not a coroutine function.")

        try:
            asyncio.create_task(self.callbacks[verb](*parser_args, payload))
        except Exception as err:
            return command.fail(
                error="Errored scheduling callback coroutine for "
                f"command {verb!r}: {err}"
            )

        return command
