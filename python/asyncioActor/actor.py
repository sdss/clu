#!/usr/bin/env python
# encoding: utf-8
#
# @Author: José Sánchez-Gallego
# @Date: Jan 16, 2018
# @Filename: actor.py
# @License: BSD 3-Clause
# @Copyright: José Sánchez-Gallego


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import asyncio
import functools
import pathlib
import yaml

from . import log
from .core import exceptions
from .command import UserCommand


class TCPServerClientProtocol(asyncio.Protocol):

    def __init__(self, conn_cb=None, read_cb=None):

        self.conn_cb = conn_cb
        self.transport = None

        self._read_callback = read_cb

    def connection_made(self, transport):
        """Receives a connection and sends the transport to ``conn_cb``."""

        self.transport = transport
        self.transport._user_id = 0

        if self.conn_cb:
            self.conn_cb(transport)

    def data_received(self, data):

        if self._read_callback:
            self._read_callback(self.transport, data.decode())

    def set_read_callback(self, cb):
        """Sets the callback for `data_received`."""

        self._read_callback = cb


class Actor(object):

    def __init__(self, name, port=None, config_path=None, version='?'):

        self.name = name
        self.version = version

        self.config = self._get_config(config_path)
        self.loop = asyncio.get_event_loop()

        self.log = None
        self._setup_logger()

        self.user_dict = dict()

        partial_server = functools.partial(TCPServerClientProtocol,
                                           conn_cb=self.new_user,
                                           read_cb=self.new_command)
        factory = self.loop.create_server(partial_server, '127.0.0.1',
                                          port=self.config['port'])
        self.server = self.loop.run_until_complete(factory)

        self.log.info('TCP server running on {}'.format(self.server.sockets[0].getsockname()))

    def __str__(self):

        return self.__class__.__name__

    def _get_config(self, config_path=None):
        """Returns a dictionary with the configuration options."""

        if config_path is None:
            config_path = pathlib.Path(__file__).parent / f'etc/{self.name}.yml'

        return yaml.load(open(str(config_path)))

    def _setup_logger(self):
        """Starts file logging."""

        self.log = log

        if 'logging' not in self.config:
            raise exceptions.AsyncioActorError('logging section missing from configuration file.')

        config_log = self.config['logging']

        file_level = 10 if 'fileLevel' not in config_log else config_log['fileLevel']
        sh_level = 20 if 'shellLevel' not in config_log else config_log['shellLevel']

        self.log.start_file_logger(config_log['logDir'] + '/' + f'{self.name}.log', file_level)

        self.log.sh.setLevel(sh_level)

        self.log.debug('Starting file logging.')

    def new_user(self, transport):
        """Assigns userID to new client connection."""

        curr_ids = set(self.user_dict.keys())
        user_id = 1 if len(curr_ids) == 0 else max(curr_ids) + 1

        transport._user_id = user_id

        self.user_dict[user_id] = transport

        # report user information and additional info
        fake_cmd = UserCommand(user_id=user_id)
        self.show_new_user_info(fake_cmd)
        return fake_cmd

    def new_command(self, cmd):
        """Handles a new command received by the actor."""

        pass

    def show_new_user_info(self, cmd):
        """Shows information for new users. Called when a new user connects."""

        self.show_user_info(cmd)
        self.show_version(cmd, only_one_user=True)

    def show_user_info(self, cmd):
        """Shows user information including your user_id."""

        num_users = len(self.user_dict)
        if num_users == 0:
            return

        msg_data = [f'yourUserID={cmd.user_id}', f'num_users={num_users}']
        msg_str = '; '.join(msg_data)

        self.write_to_one_user('i', msg_str, cmd=cmd)
        self.show_user_list(cmd)

    def show_user_list(self, cmd=None):
        """Shows a list of connected users."""

        user_id_list = sorted(self.user_dict.keys())
        for user_id in user_id_list:
            transport = self.user_dict[user_id]
            msg_str = 'UserInfo={}, {}'.format(user_id, transport.get_extra_info('peername')[0])
            self.write_to_users('i', msg_str, cmd=cmd)

    def show_version(self, cmd, only_one_user=False):
        """Shows actor version."""

        msg_str = f'version={self.version!r}'

        if only_one_user:
            self.write_to_one_user('i', msg_str, cmd=cmd)
        else:
            self.write_to_users('i', msg_str, cmd=cmd)

    @staticmethod
    def get_user_cmd_id(msg_code=None, cmd=None, user_id=None, cmd_id=None):
        """Returns user_id, cmd_id based on user-supplied information.

        Parameters:
            msg_code (str):
                Used to determine if ``cmd`` is a valid default. If ``cmd`` is
                provided and ``cmd.is_done`` and ``msg_code`` is not a done
                code, then ``cmd`` is ignored (treated as None). This allows
                you to continue to use a completed command to send
                informational messages, which can simplify code. Note that it
                is also possible to send multiple done messages for a command,
                but that indicates a serious bug in your code.
            cmd (`Command` object):
                User command; used as a default for ``user_id`` and ``cmd_id``,
                but see ``msg_code``.
            user_id (int):
                If None then use ``cmd.user_id``, but see ``msg_code``.
            cmd_id (int):
                If None then use ``cmd.cmd_id``, but see ``msg_code``.
        """

        if cmd is not None and msg_code is not None and cmd.is_done:
            state = cmd.state_from_msg_code(msg_code)
            if state not in cmd.DONE_STATES:
                # ignore command
                cmd = None

        return (user_id if user_id is not None else (cmd.user_id if cmd else 0),
                cmd_id if cmd_id is not None else (cmd.cmd_id if cmd else 0))

    @staticmethod
    def format_user_output(msg_code, msg_str, user_id=None, cmd_id=None):
        """Formats a string to send to users."""

        return f'{cmd_id:d} {user_id:d} {msg_code:s} {msg_str:s}'

    def write_to_users(self, msg_code, msg_str, cmd=None, user_id=None, cmd_id=None):
        """Writes a message to all users."""

        user_id, cmd_id = self.get_user_cmd_id(msg_code=msg_code,
                                               cmd=cmd,
                                               user_id=user_id,
                                               cmd_id=cmd_id)

        full_msg_str = self.format_user_output(msg_code,
                                               msg_str,
                                               user_id=user_id,
                                               cmd_id=cmd_id)

        self.log.info(f'{self}.write_to_users({full_msg_str!r})')

        for transport in self.user_dict.values():
            transport.write((full_msg_str + '\n').encode())

    def write_to_one_user(self, msg_code, msg_str, cmd=None, user_id=None, cmd_id=None):
        """Writes a message to one user."""

        user_id, cmd_id = self.get_user_cmd_id(msg_code=msg_code,
                                               cmd=cmd,
                                               user_id=user_id,
                                               cmd_id=cmd_id)

        if user_id == 0:
            raise RuntimeError(
                f'write_to_one_user(msg_code={msg_code!r}; msg_str={msg_str!r}; '
                'cmd={cmd!r}; user_id={user_id!r}; cmd_id={cmd_id!r}) cannot write to user 0')

        transport = self.user_dict[user_id]
        full_msg_str = self.format_user_output(msg_code, msg_str, user_id=user_id, cmd_id=cmd_id)

        self.log.info(f'{self}.write_to_one_user({full_msg_str!r}); user_id={user_id}')
        transport.write((full_msg_str + '\n').encode())
