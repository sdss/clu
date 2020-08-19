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
        self._config = None

    def __repr__(self):

        return f'<{str(self)} (name={self.name!r})>'

    def __str__(self):

        return self.__class__.__name__

    @abc.abstractmethod
    async def start(self):
        """Runs the client."""

        pass

    async def shutdown(self):
        """Shuts down all the remaining tasks."""

        self.log.info('cancelling all pending tasks and shutting down.')

        tasks = [task for task in asyncio.Task.all_tasks(loop=self.loop)
                 if task is not asyncio.tasks.Task.current_task(loop=self.loop)]
        list(map(lambda task: task.cancel(), tasks))

        await asyncio.gather(*tasks, return_exceptions=True)

        self.loop.stop()

    @staticmethod
    def _parse_config(config):

        if not isinstance(config, dict):

            config = pathlib.Path(config)
            assert config.exists(), 'configuration path does not exist.'

            config = read_yaml_file(str(config))

        if 'actor' in config:
            config = config['actor']

        return config

    @classmethod
    def from_config(cls, config, *args, **kwargs):
        """Parses a configuration file.

        Parameters
        ----------
        config : dict or str
            A configuration dictionary or the path to a YAML configuration
            file that must contain a section ``'actor'`` (if the section is
            not present, the whole file is assumed to be the actor
            configuration).

        """

        orig_config_dict = cls._parse_config(config)
        config_dict = orig_config_dict.copy()

        # Decide what to do with the rest of the keyword arguments:
        args_inspect = inspect.getfullargspec(cls)

        if args_inspect.varkw is not None:
            # If there is a catch-all kw variable, send everything and let the
            # subclass handle it.
            config_dict.update(kwargs)
        else:
            # Check the kw arguments in the subclass and pass only
            # values from config_dict that match them.
            kw_args = args_inspect.kwonlyargs
            if len(args_inspect.defaults) > 0:
                args_invert = args_inspect.args[::-1]
                kw_args += args_invert[:len(args_inspect.defaults)]
            for kw in kwargs:
                if kw in kw_args:
                    config_dict[kw] = kwargs[kw]

        # We also pass *args in case the actor has been subclassed
        # and the subclass' __init__ accepts different arguments.
        new_actor = cls(*args, **config_dict)

        # Store original config. This may not be complete since from_config
        # may have been super'd from somewhere else.
        new_actor._config = orig_config_dict
        new_actor._config.update(kwargs)

        return new_actor

    def setup_logger(self, log, log_dir, verbose=False):
        """Starts the file logger."""

        if not log:
            log = get_logger('actor:' + self.name)

        if log_dir:

            log_dir = pathlib.Path(log_dir).expanduser()

            if not log_dir.exists():
                log_dir.mkdir(parents=True)

            log.start_file_logger(log_dir / f'{self.name}.log')

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

    def send_command(self):
        """Sends a command to an actor."""

        raise NotImplementedError('Sending commands is not implemented '
                                  'for this client.')


class BaseActor(BaseClient):
    """An actor based on `asyncio`.

    This class expands `.BaseClient` with a parsing system for new commands
    and placeholders for methods for handling new commands and writing replies,
    which should be overridden by the specific actors.

    """

    @abc.abstractmethod
    async def start(self):
        """Starts the server. Must be overridden by the subclasses."""

        pass

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
