#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-20
# @Filename: base.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import abc
import asyncio
import inspect
import logging
import pathlib
import time

from sdsstools import get_logger, read_yaml_file

from .model import Model
from .tools import REPLY


__all__ = ['BaseClient', 'BaseActor']


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
    name : str
        The name of the actor.
    version : str
        The version of the actor.
    loop
        The event loop. If `None`, the current event loop will be used.
    log_dir : str
        The directory where to store the file logs.
    log : ~logging.Logger
        A `~logging.Logger` instance to be used for logging instead of creating
        a new one.
    verbose : bool or int
        Whether to log to stdout. Can be an integer logging level.

    """

    name = None

    def __init__(self, name, version=None, loop=None,
                 log_dir=None, log=None, verbose=False):

        self.loop = loop or asyncio.get_event_loop()

        self.name = name
        assert self.name, 'name cannot be empty.'

        self.log = None
        self.setup_logger(log, log_dir, verbose=verbose)

        self.version = version or '?'

        # Internally store the original configuration used to start the client.
        self.config = None

    def __repr__(self):

        return f'<{str(self)} (name={self.name!r})>'

    def __str__(self):

        return self.__class__.__name__

    @abc.abstractmethod
    async def start(self):
        """Runs the client."""

        pass

    async def stop(self):
        """Shuts down all the remaining tasks."""

        self.log.info('cancelling all pending tasks and shutting down.')

        tasks = [task for task in asyncio.all_tasks(loop=self.loop)
                 if task is not asyncio.current_task(loop=self.loop)]
        list(map(lambda task: task.cancel(), tasks))

        await asyncio.gather(*tasks, return_exceptions=True)

        self.loop.stop()

    @staticmethod
    def _parse_config(config):

        if not isinstance(config, dict):

            config = pathlib.Path(config)
            assert config.exists(), 'configuration path does not exist.'

            config = read_yaml_file(str(config))

        return config

    @classmethod
    def from_config(cls, config, *args, **kwargs):
        """Parses a configuration file.

        Parameters
        ----------
        config : dict or str
            A configuration dictionary or the path to a YAML configuration
            file. If the file contains a section called ``'actor'`` or
            ``'client'``, that section will be used instead of the whole
            file.

        """

        orig_config_dict = cls._parse_config(config)

        config_dict = orig_config_dict.copy()

        if 'actor' in config_dict:
            config_dict = config_dict['actor']
        elif 'client' in config_dict:
            config_dict = config_dict['client']

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
            class_kwargs.remove('self')

            # Remove keys that are not in the signature.
            config_dict = {key: value for key, value in config_dict.items()
                           if key in class_kwargs}

        # We also pass *args in case the actor has been subclassed
        # and the subclass' __init__ accepts different arguments.
        new_client = cls(*args, **config_dict)

        # Store original config. This may not be complete since from_config
        # may have been super'd from somewhere else.
        new_client.config = orig_config_dict

        return new_client

    def setup_logger(self, log, log_dir, verbose=False):
        """Starts the file logger."""

        if not log:
            log = get_logger('clu:' + self.name)

        log.setLevel(REPLY)

        if log is not False and log_dir:

            log_dir = pathlib.Path(log_dir).expanduser()

            log.start_file_logger(log_dir / f'{self.name}.log')

            if log.fh:  # In case starting the file logger fails.
                log.fh.formatter.converter = time.gmtime
                log.fh.setLevel(REPLY)

        log.sh.setLevel(logging.INFO)
        if verbose:
            log.sh.setLevel(int(verbose))
        else:
            log.sh.setLevel(logging.WARNING)

        self.log = log
        self.log.debug(f'{self.name}: logging system initiated.')

        # Set the loop exception handler to be handled by the logger.
        self.loop.set_exception_handler(self.log.asyncio_exception_handler)

        return log

    def send_command(self):  # pragma: no cover
        """Sends a command to an actor and returns a `.Command` instance."""

        raise NotImplementedError('Sending commands is not implemented '
                                  'for this client.')


class BaseActor(BaseClient):
    """An actor based on `asyncio`.

    This class expands `.BaseClient` with a parsing system for new commands
    and placeholders for methods for handling new commands and writing replies,
    which should be overridden by the specific actors.

    """

    schema = None

    def __init__(self, *args, schema=None, **kwargs):

        super().__init__(*args, **kwargs)

        self.validate_schema(schema)

    def validate_schema(self, schema):
        """Loads and validates the actor schema."""

        schema = schema or self.schema

        if schema is None:
            return None

        self.schema = Model(self.name, schema, is_file=True, log=self.log)

        return self.schema

    @abc.abstractmethod
    def new_command(self):
        """Handles a new command.

        Must be overridden by the subclass and call `.parse_command`
        with a `.Command` object.

        """

        pass

    @abc.abstractmethod
    def parse_command(self, command):
        """Parses and executes a `.Command`. Must be overridden."""

        pass

    def send_command(self):
        """Sends a command to another actor."""

        raise NotImplementedError('Sending commands is not implemented '
                                  'for this actor.')

    @abc.abstractmethod
    def write(self):
        """Writes a message to user(s). To be overridden by the subclasses."""

        pass
