#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-16
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-12 19:17:40

import asyncio
import pathlib
import sys
import traceback

import click
import ruamel.yaml

import clu
from clu.command import Command
from clu.legacy import TronConnection
from clu.misc import get_logger
from clu.parser import command_parser
from clu.protocol import TCPStreamServer


__all__ = ['Actor', 'LegacyActor', 'command_parser']


class Actor(object):
    """An actor based on `asyncio <https://docs.python.org/3/library/asyncio.html>`__.

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
    log_dir : str
        The directory where to store the logs. Defaults to
        ``$HOME/logs/<name>`` where ``<name>`` is the name of the actor.
    log : logging.Logger
        A `logging.Logger` instance to be used for logging instead of creating
        a new one.

    """

    #: list: Arguments to be passed to each command in the parser.
    #: Note that the command is always passed first.
    parser_args = []

    def __init__(self, name, host, port, version=None, loop=None,
                 log_dir=None, log=None):

        self.name = name
        assert self.name, 'name cannot be empty.'

        self.log = log or self.setup_logger(log_dir)

        self.loop = loop or asyncio.get_event_loop()

        self.user_dict = dict()

        self.version = version or '?'

        self.host = host
        self.port = port

        #: TCPStreamServer: The server to talk to this actor.
        self.server = TCPStreamServer(host, port, loop=self.loop,
                                      connection_callback=self.new_user,
                                      data_received_callback=self.new_command)

    def __repr__(self):

        return f'<{str(self)} (name={self.name}, host={self.host!r}, port={self.port})>'

    def __str__(self):

        return self.__class__.__name__

    async def run(self, block=True):
        """Starts the server.

        Parameters
        ----------
        block : bool
            Whether to block the execution by serving forever.

        """

        await self.server.start_server()

        self.log.info(f'running TCP server on {self.host}:{self.port}')

        if block:
            await self.server.server.serve_forever()

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

            yaml = ruamel.yaml.YAML(typ='safe')
            config = yaml.load(open(str(config)))

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

        config_dict = cls._parse_config(config)

        version = config_dict.get('version', '?')
        log_dir = config_dict.get('log_dir', None)

        # We also pass *args and **kwargs in case the actor has been subclassed
        # and the subclass' __init__ accepts different arguments.
        new_actor = cls(*args, config_dict['name'], config_dict['host'],
                        config_dict['port'], version=version, log_dir=log_dir, **kwargs)

        return new_actor

    def setup_logger(self, log_dir, file_level=10, shell_level=20):
        """Starts the file logger."""

        log = get_logger('actor:' + self.name)

        if log_dir is None:
            log_dir = pathlib.Path(f'/data/logs/actors/{self.name}/').expanduser()
        else:
            log_dir = pathlib.Path(log_dir).expanduser()

        if not log_dir.exists():
            log_dir.mkdir(parents=True)

        log.start_file_logger(log_dir / f'{self.name}.log')

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
            command.actor = self  # Assign the actor
        except clu.CommandError as ee:
            self.write('f', {'text': f'Could not parse the following as a command: {ee!r}'})
            return

        try:
            self.parse(command)
        except clu.CommandError as ee:
            command.set_status(command.status.FAILED,
                               message=f'Command {command.body!r} failed: {ee}')

        return command

    def parse(self, command):
        """Parses an user command with the default parser.

        This method can be overridden to use a custom parser.

        """

        # This will pass the command as the first argument for each command.
        # If self.parser_args is defined, those arguments will be passed next.
        parser_args = [command]
        parser_args += self.parser_args

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
                                              obj={'parser_args': parser_args})
            with ctx:
                command_parser.invoke(ctx)
        except click.UsageError as ee:
            # If this is a command that cannot be parsed.
            raise clu.CommandError(ee)
        except Exception as ee:
            # If this is a general exception, outputs the traceback to stderr
            # and replies with the error message.
            sys.stderr.write(f'command {command.raw_command_string!r} failed\n')
            traceback.print_exc(file=sys.stderr)
            raise clu.CommandError(ee)

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
                    value = clu.escape(value)
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


class LegacyActor(Actor):
    """An actor that provides compatibility with the SDSS opscore protocol.

    Parameters
    ----------
    args, kwargs
        Arguments to be passed to `Actor`.
    tron_host : str
        The host on which Tron is running.
    tron_port : int
        The port on which Tron is running.
    tron_models : list
        A list of strings with the actors whose models will be tracked.

    """

    def __init__(self, *args, tron_host=None, tron_port=None, tron_models=None, **kwargs):

        super().__init__(*args, **kwargs)

        if tron_host and tron_port:
            self.tron = TronConnection(self.name, tron_host, tron_port, tron_models=tron_models)
        else:
            self.tron = False

    async def run(self, **kwargs):
        """Starts the server and the Tron client connection."""

        # Start tron connection
        try:
            if self.tron:
                await self.tron.start()
                self.log.info(f'started tron connection at {self.tron.host}:{self.tron.port}')
            else:
                warnings.warn('starting LegacyActor without Tron connection.', clu.CluWarning)
        except ConnectionRefusedError as ee:
            raise clu.CluError(f'failed trying to create a connection to tron: {ee}')

        self.log.info(f'started tron connection at {self.tron.host}:{self.tron.port}')

        await super().run(**kwargs)

    @classmethod
    def from_config(cls, config, *args, **kwargs):

        config_dict = cls._parse_config(config)
        if 'tron' in config_dict:
            kwargs.update({'tron_host': config_dict['tron'].get('host', None)})
            kwargs.update({'tron_port': config_dict['tron'].get('port', None)})
            kwargs.update({'tron_models': config_dict['tron'].get('models', None)})

        return super().from_config(config_dict, *args, **kwargs)
