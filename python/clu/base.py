#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-20
# @Filename: base.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import abc
import asyncio
import inspect
import logging
import pathlib
import time
from datetime import datetime

from typing import Any, Dict, Optional, TypeVar, Union, cast

from sdsstools import get_logger, read_yaml_file
from sdsstools.logger import SDSSLogger

from clu.command import BaseCommand

from .model import Model
from .tools import REPLY


__all__ = ["BaseClient", "BaseActor", "Reply"]


SchemaType = Union[Dict[str, Any], pathlib.Path, str]
T = TypeVar("T", bound="BaseClient")


class BaseClient(metaclass=abc.ABCMeta):
    """A base client that can be used for listening or for an actor.

    This class defines a new client. Clients differ from actors in that
    they do not receive commands or issue replies, but do send commands to
    other actors and listen to the keyword-value flow. All actors are also
    clients and any actor should subclass from `.BaseClient`.

    Normally a new instance of a client or actor is created by passing a
    configuration file path to `.from_config` which defines how the
    client must be started.

    Parameters
    ----------
    name
        The name of the client.
    version
        The version of the client.
    loop
        The event loop. If `None`, the current event loop will be used.
    log_dir
        The directory where to store the file logs.
    log
        A `~logging.Logger` instance to be used for logging instead of creating
        a new one.
    verbose
        Whether to log to stdout. Can be an integer logging level.
    validate
        Whether to actor should validate its own messages against its model (if it
        has one). This is a global parameter that can be overridden when calling
        `~.BaseClient.write`.
    config
        A dictionary of configuration parameters that will be accessible to the client.
    """

    name: str

    def __init__(
        self,
        name: str,
        version: Optional[str] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        log_dir: Optional[Union[pathlib.Path, str]] = None,
        log: Optional[SDSSLogger] = None,
        verbose: Union[bool, int] = False,
        validate: bool = True,
        config: dict = {},
    ):

        self.loop = loop or asyncio.get_event_loop()

        self.name = name
        assert self.name, "name cannot be empty."

        self.log: SDSSLogger
        self.setup_logger(log, log_dir, verbose=verbose)

        self.version = version or "?"

        # Internally store the original configuration used to start the client.
        self.config: Dict[str, Any] = {}

        self.validate = validate
        self.config = config

    def __repr__(self):
        return f"<{str(self)} (name={self.name!r})>"

    def __str__(self):
        return self.__class__.__name__

    @abc.abstractmethod
    async def start(self: T) -> T:
        """Runs the client."""

        pass

    async def stop(self):
        """Shuts down all the remaining tasks."""

        self.log.info("cancelling all pending tasks and shutting down.")

        tasks = [
            task
            for task in asyncio.all_tasks(loop=self.loop)
            if task is not asyncio.current_task(loop=self.loop)
        ]
        list(map(lambda task: task.cancel(), tasks))

        await asyncio.gather(*tasks, return_exceptions=True)

        self.loop.stop()

    @staticmethod
    def _parse_config(
        input: Union[Dict[str, Any], pathlib.Path, str]
    ) -> Dict[str, Any]:

        if not isinstance(input, dict):
            input = pathlib.Path(input)
            assert input.exists(), "configuration path does not exist."
            config = read_yaml_file(str(input))
        else:
            config = input

        return cast("Dict[str, Any]", config)

    @classmethod
    def from_config(
        cls,
        config: Union[Dict[str, Any], pathlib.Path, str],
        *args,
        **kwargs,
    ):
        """Parses a configuration file.

        Parameters
        ----------
        config
            A configuration dictionary or the path to a YAML configuration
            file. If the file contains a section called ``'actor'`` or
            ``'client'``, that section will be used instead of the whole
            file.
        """

        orig_config_dict = cls._parse_config(config)

        config_dict = orig_config_dict.copy()

        if "actor" in config_dict:
            config_dict = config_dict["actor"]
        elif "client" in config_dict:
            config_dict = config_dict["client"]

        config_dict.update(kwargs)

        # Decide what to do with the rest of the keyword arguments:
        args_inspect = inspect.getfullargspec(cls)

        if args_inspect.varkw is not None:
            # If there is a catch-all kw variable, send everything and let the
            # subclass handle it.
            config_dict.update(kwargs)
        else:
            # Check the kw arguments in the subclass and pass only
            # values from config_dict that match them.
            class_kwargs = args_inspect.args
            class_kwargs.remove("self")

            # Remove keys that are not in the signature.
            config_dict = {
                key: value for key, value in config_dict.items() if key in class_kwargs
            }

        # We also pass *args in case the actor has been subclassed
        # and the subclass' __init__ accepts different arguments.
        new_client = cls(*args, config=orig_config_dict, **config_dict)

        return new_client

    def setup_logger(
        self,
        log: Any,
        log_dir: Optional[Union[pathlib.Path, str]],
        verbose: Union[bool, int] = False,
    ):
        """Starts the file logger."""

        if not log:
            log = get_logger("clu:" + self.name)
        else:
            assert isinstance(log, SDSSLogger), "Logger must be sdsstools.SDSSLogger"
            self.log = log
            return log

        log.setLevel(REPLY)

        if log is not False and log_dir:

            log_dir = pathlib.Path(log_dir).expanduser()

            log.start_file_logger(
                str(log_dir / f"{self.name}.log"),
                rotating=True,
                rollover=True,
            )

            if log.fh:  # In case starting the file logger fails.
                log.fh.formatter.converter = time.gmtime
                log.fh.setLevel(REPLY)

        log.sh.setLevel(logging.WARNING)
        if verbose is True:
            log.sh.setLevel(logging.DEBUG)
        elif verbose is not False and isinstance(verbose, int):
            log.sh.setLevel(verbose)

        self.log = log
        self.log.debug(f"{self.name}: logging system initiated.")

        # Set the loop exception handler to be handled by the logger.
        self.loop.set_exception_handler(self.log.asyncio_exception_handler)

        return log

    def send_command(self, actor: str, *args, **kwargs):  # pragma: no cover
        """Sends a command to an actor and returns a `.Command` instance."""

        raise NotImplementedError(
            "Sending commands is not implemented for this client."
        )


class BaseActor(BaseClient):
    """An actor based on `asyncio`.

    This class expands `.BaseClient` with a parsing system for new commands
    and placeholders for methods for handling new commands and writing replies,
    which should be overridden by the specific actors.
    """

    model: Union[Model, None] = None

    def __init__(self, *args, schema: SchemaType = None, **kwargs):

        super().__init__(*args, **kwargs)

        self.load_schema(schema)

    def load_schema(
        self,
        schema: Union[SchemaType, None],
        is_file=True,
    ) -> Union[Model, None]:
        """Loads and validates the actor schema."""

        if schema is None:
            schema = {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            }
            is_file = False

        self.model = Model(self.name, schema, is_file=is_file, log=self.log)

        return self.model

    @abc.abstractmethod
    def new_command(self):
        """Handles a new command.

        Must be overridden by the subclass and call `.parse_command`
        with a `.Command` object.
        """
        pass

    @abc.abstractmethod
    def parse_command(self, command: BaseCommand):
        """Parses and executes a `.Command`. Must be overridden."""
        pass

    @abc.abstractmethod
    def _write_internal(self, reply: Reply):
        """Internally handle the reply and output it to the users.

        Must handle converting the general `.Reply` to the specific format of the
        actor transport. Must also handle logging the reply.
        """
        pass

    def write(
        self,
        message_code: str = "i",
        message: Optional[Dict[str, Any] | str] = None,
        command: Optional[BaseCommand] = None,
        broadcast: bool = False,
        validate: bool | None = None,
        silent: bool = False,
        call_internal: bool = True,
        **kwargs,
    ) -> Reply:
        """Writes a message to user(s).

        The reply to the users will be formatted by the actor class into message
        specific to the communication channel. Additional keywords passed to this
        method will be used to complete the message (as long as they don't overlap
        with named parameters). For example ::

            actor.write('i', message={'text': 'Hi!', 'value1': 1})

        and ::

            actor.write('i', text='Hi!', value1=1)

        are equivalent and ::

            actor.write('i', message={'text': 'Hi!'}, value1=1)

        is equivalent to ::

            actor.write('i', message={'text': 'Hi!', 'value1': 1})

        This method generates a `.Reply` object that is passed to the
        ``_write_internal`` method in the class, which processes it and outputs the
        message to the users using the appropriate transport. If ``command`` is passed,
        the reply is added to ``command.replies``.

        Parameters
        ----------
        message_code
            The message code (e.g., ``'i'`` or ``':'``).
        message
            The keywords to be output. Must be a dictionary of pairs
            ``{keyword: value}``.
        command
            The command to which we are replying. If not set, it is assumed
            that this is a broadcast.
        broadcast
            Whether to broadcast the message to all the users or only to the
            commander.
        validate
            Validate the reply against the actor schema. This is ignored if the actor
            was not started with knowledge of its own schema. If `None`, defaults to
            the actor global behaviour.
        silent
            When `True` does not output the message to the users. This can be used to
            issue internal commands that update the internal model but that don't
            clutter the output.
        call_internal
            Whether to call the actor internal write method. Should be `True` but
            it's sometimes useful to call `.write` with ``call_internal=False`` when
            one is overriding the method and wants to control when to call the internal
            method.
        kwargs
            Keyword arguments that will used to update the message.
        """

        if isinstance(message, str):
            message = {"text": message}
        else:
            message = message or {}
            if not isinstance(message, dict):
                raise TypeError("message must be a dictionary")

        message.update(kwargs)

        reply = Reply(message_code, message, command=command, broadcast=broadcast)

        do_validate = validate if validate is not None else self.validate
        if do_validate and self.model is not None:
            reply.use_validation = True
            result, err = self.model.update_model(message)
            if result is False:
                message = {"error": f"Failed validating the reply: {err}"}
                reply.message_code = "e"
                reply.message = message
                reply.validated = False
            else:
                reply.validated = True

        if command:
            command.replies.append(reply)

        if call_internal and silent is False:
            if asyncio.iscoroutinefunction(self._write_internal):
                asyncio.create_task(self._write_internal(reply))  # type: ignore
            else:
                self._write_internal(reply)

        return reply


class Reply:
    """A reply from a command or actor to be sent to the users."""

    def __init__(
        self,
        message_code: str,
        message: Dict[str, Any],
        command: Optional[BaseCommand] = None,
        broadcast: bool = False,
        use_validation: bool = False,
        validated: bool = False,
    ):
        self.date = datetime.utcnow()
        self.message_code = message_code
        self.message = message
        self.command = command
        self.broadcast = broadcast
        self.use_validation = use_validation
        self.validated = validated
