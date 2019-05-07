#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-16
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-06 23:19:17

import asyncio
import collections
import logging
import pathlib
import sys
import traceback

import click
import ruamel.yaml

import asyncioActor
from asyncioActor.command import Command
from asyncioActor.core import exceptions
from asyncioActor.misc import logger
from asyncioActor.parser import command_parser
from asyncioActor.protocol import TCPStreamPeriodicServer, TCPStreamServer


#: The default status delay.
DEFAULT_STATUS_DELAY = 1


class Actor(object):
    """An actor based in asyncio.

    This class defines a new actor. Normally a new instance is created by
    passing a configuration file path which defines how the actor must
    be started.

    The TCP servers need to be started by awaiting the coroutine `.run`. The
    following is an example of a basic actor instantiation: ::

        loop = asyncio.get_event_loop()
        my_actor = Actor('my_actor', '127.0.0.1', 9999)
        loop.run_until_complete(my_actor.run())

    Parameters
    ----------
    name : str
        The name of the actor.
    host : str
        The host where the TCP server will run.
    port : int
        The port of the TCP server.
    version : str
        The version of the actor.
    loop
        The event loop. If `None`, the current event loop will be used.
    config : dict or str
        A configuration dictionary or the path to a YAML configuration
        file that must contain a section ``'actor'`` (if the section is
        not present, the whole file is assumed to be the actor
        configuration).
    status_port : int
        If defined, the port on which the status server will run.
    status_callback : function
        The function to be called by the status server.
    status_delay : float
        The delay, in seconds, between successive calls to ``status_callback``.
        Defaults to `.DEFAULT_STATUS_DELAY`.
    log_dir : str
        The directory where to store the logs. Defaults to ``$HOME/.<name>``
        where ``<name>`` is the name of the actor.

    """

    def __init__(self, name=None, host=None, port=None, version=None,
                 loop=None, config=None, status_port=None, status_callback=None,
                 status_delay=None, log_dir=None):

        self.config = self._parse_config(config)

        self.name = name or self.config['name']
        assert self.name, 'name cannot be empty.'

        self.log = self._setup_logger(log_dir)

        self.loop = loop or asyncio.get_event_loop()

        self.user_dict = dict()

        self.version = version or self.config['version'] or '?'

        host = host or self.config['host']
        port = port or self.config['port']

        self.server = TCPStreamServer(host, port, loop=self.loop,
                                      connection_callback=self.new_user,
                                      data_received_callback=self.new_command)

        self.status_server = None

        status_port = status_port or self.config['status_port']
        sleep_time = status_delay or self.config['status_delay'] or DEFAULT_STATUS_DELAY

        if status_port:
            self.status_server = TCPStreamPeriodicServer(
                host, status_port, loop=self.loop,
                periodic_callback=status_callback,
                sleep_time=sleep_time)

    def __repr__(self):

        if self.server and self.server.server:
            host, port = self.server.server.sockets[0].getsockname()
        else:
            host = port = None

        return f'<{str(self)} (name={self.name}, host={host!r}, port={port})>'

    def __str__(self):

        return self.__class__.__name__

    async def run(self):
        """Starts the servers."""

        await self.server.start_server()

        socket = self.server.server.sockets[0]
        host, port = socket.getsockname()
        self.log.info(f'starting TCP server on {host}:{port}')

        if self.status_server:

            await self.status_server.start_server()

            socket_status = self.status_server.server.sockets[0]
            host, port = socket_status.getsockname()
            self.log.info(f'starting status server on {host}:{port}')

        await self.server.server.serve_forever()

    async def shutdown(self):
        """Shuts down all the remaining tasks."""

        self.log.info('cancelling all pending tasks and shutting down.')

        tasks = [task for task in asyncio.Task.all_tasks(loop=self.loop)
                 if task is not asyncio.tasks.Task.current_task(loop=self.loop)]
        list(map(lambda task: task.cancel(), tasks))

        await asyncio.gather(*tasks, return_exceptions=True)

        self.loop.stop()

    def _parse_config(self, config):
        """Parses the configuration file."""

        if config is None:
            # Returns a defaultdict that returns None if the key is not present.
            return collections.defaultdict(lambda: None)

        if not isinstance(config, dict):

            assert config.exists(), 'configuration path does not exist.'

            yaml = ruamel.yaml.add_implicit_resolverYAML(typ='safe')
            config = yaml.load(open(str(config)))

        if 'actor' in config:
            config = config['actor']

        return config

    def _setup_logger(self, log_dir, file_level=10, shell_level=20):
        """Starts the file logger."""

        orig_logger = logging.getLoggerClass()
        logging.setLoggerClass(logger.MyLogger)
        log = logging.getLogger(self.name + '_actor')
        log._set_defaults()  # Inits sh handler
        logging.setLoggerClass(orig_logger)

        if log_dir is None:
            if 'logging' in self.config:
                log_dir = self.config['logging'].get('log_dir', None)

        if log_dir is None:
            log_dir = pathlib.Path(f'~/.{self.name}/').expanduser()
        else:
            log_dir = pathlib.Path(log_dir)

        if not log_dir.exists():
            log_dir.mkdir(parents=True)

        log.start_file_logger(log_dir / f'{self.name}.log')

        if 'logging' in self.config:
            file_level = self.config['logging'].get('file_level', None) or file_level
            shell_level = self.config['logging'].get('shell_level', None) or shell_level

        log.sh.setLevel(shell_level)
        log.fh.setLevel(file_level)

        log.info('logging system initiated.')

        return log

    def new_user(self, transport):
        """Assigns userID to new client connection."""

        curr_ids = set(self.user_dict.keys())
        user_id = 1 if len(curr_ids) == 0 else max(curr_ids) + 1

        transport.user_id = user_id

        self.user_dict[user_id] = transport

        # report user information and additional info
        self.show_new_user_info(user_id)

        return

    def new_command(self, transport, command_str):
        """Handles a new command received by the actor."""

        command_str = command_str.decode().strip()

        if not command_str:
            return

        user_id = transport.user_id

        try:
            command = Command(command_str, user_id=user_id, actor=self, loop=self.loop)
        except exceptions.CommandError as ee:
            self.write('f', {'text': f'Could not parse the following as a command: {ee!r}'})
            return

        try:
            self.parse(command)
        except exceptions.CommandError as ee:
            command.set_status(command.status.FAILED,
                               message=f'Command {command.body!r} failed: {ee}')

        return command

    def parse(self, command):
        """Parses an user command with the default parser.

        This method can be overridden to use a custom parser.

        """

        # Empty command. Just finish the command.
        if not command.body:
            self.write(':', '', command=command)
            return

        command.set_status(command.status.RUNNING)

        try:
            # We call the command with a custom context to get around
            # the default handling of exceptions in Click. This will force
            # exceptions to be raised instead of redirected to the stdout.
            # See http://click.palletsprojects.com/en/7.x/exceptions/
            ctx = command_parser.make_context('command-parser',
                                              command.body.split(),
                                              obj=dict(actor=self, command=command))
            with ctx:
                command_parser.invoke(ctx)
        except click.UsageError as ee:
            # If this is a command that cannot be parsed.
            raise exceptions.CommandError(ee)
        except Exception as ee:
            # If this is a general exception, outputs the traceback to stderr
            # and replies with the error message.
            sys.stderr.write(f'command {command.raw_command_string!r} failed\n')
            traceback.print_exc(file=sys.stderr)
            raise exceptions.CommandError(ee)

    def show_new_user_info(self, user_id):
        """Shows information for new users. Called when a new user connects."""

        self.show_user_info(user_id)
        self.show_version(user_id=user_id)

    def show_user_info(self, user_id):
        """Shows user information including your user_id."""

        num_users = len(self.user_dict)
        if num_users == 0:
            return

        msg_data = [f'yourUserID={user_id}', f'num_users={num_users}']
        msg_str = '; '.join(msg_data)

        self.write('i', msg_str, user_id=user_id)
        self.show_user_list()

    def show_user_list(self):
        """Shows a list of connected users. Broadcast to all users."""

        user_id_list = sorted(self.user_dict.keys())
        for user_id in user_id_list:
            transport = self.user_dict[user_id]
            peername = transport.get_extra_info('peername')[0]
            msg_str = f'UserInfo={user_id}, {peername}'
            self.write('i', msg_str)

    def show_version(self, user_id=None):
        """Shows actor version."""

        msg_str = f'version={self.version!r}'

        self.write('i', msg_str, user_id=user_id)

    @staticmethod
    def get_user_command_id(command=None, user_id=None, command_id=None):
        """Returns user_id, command_id based on user-supplied information.

        Parameters
        ----------
        command : Command
            User command; used as a default for ``user_id`` and ``command_id``.
            If the command is done, it is ignored.
        user_id : int
            If `None` then use ``command.user_id``.
        command_id : int
            If `None` then use ``command.command_id``.

        """

        if command is not None and command.status.is_done:
            command = None

        user_id = user_id or (command.user_id if command else 0)
        command_id = command_id or (command.command_id if command else 0)

        return (user_id, command_id)

    @staticmethod
    def format_user_output(msg_code, msg_str=None, user_id=None, command_id=None):
        """Formats a string to send to users."""

        msg_str = '' if msg_str is None else ' ' + msg_str

        return f'{command_id:d} {user_id:d} {msg_code:s}{msg_str:s}'

    def write(self, msg_code, message=None, command=None, user_id=None,
              command_id=None, escape=True, concatenate=False):
        """Writes a message to user(s).

        Parameters
        ----------
        msg_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        message : str or dict
            The text to be output. It can be either a string with the keywords
            to output or a dictionary of pairs ``{keyword: value}`` where
            ``value`` must be a string.
        command : Command
            User command; used as a default for ``user_id`` and ``command_id``.
            If the command is done, it is ignored.
        user_id : int
            If `None` then use ``command.user_id``.
        command_id : int
            If `None` then use ``command.command_id``.
        escape : bool
            Whether to use `json.dumps` to escape the text of the message.
            This option is ignored unless ``message`` is a dictionary.
        concatenate : bool
            If ``message`` is a dictionary with multiple keywords and
            ``concatenate=True``, all the keywords will be output in a single
            reply with the keywords joined with semicolons. Otherwise each
            keyword will be output in multiple lines.

        """

        user_id, command_id = self.get_user_command_id(command=command,
                                                       user_id=user_id,
                                                       command_id=command_id)

        if message is None:
            lines = ['']
        elif isinstance(message, str):
            lines = [message]
        elif isinstance(message, dict):
            lines = []
            for keyword in message:
                value = message[keyword]
                if escape:
                    value = asyncioActor.escape(value)
                lines.append(f'{keyword}={value}')
            if concatenate:
                lines = ['; '.join(lines)]
        else:
            raise TypeError('invalid message type ' + type(message))

        for line in lines:

            full_msg_str = self.format_user_output(msg_code, line,
                                                   user_id=user_id,
                                                   command_id=command_id)

            msg = (full_msg_str + '\n').encode()

            if user_id is None or user_id == 0:
                for transport in self.user_dict.values():
                    transport.write(msg)
            else:
                transport = self.user_dict[user_id]
                transport.write(msg)
