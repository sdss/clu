#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-13
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import warnings

import clu

from ..base import BaseActor
from ..command import Command, TimedCommandList, parse_legacy_command
from ..parser import ClickParser
from ..protocol import TCPStreamServer
from ..tools import log_reply
from .tron import TronConnection


__all__ = ['LegacyActor', 'BaseLegacyActor']


class BaseLegacyActor(BaseActor):
    """An actor that provides compatibility with the SDSS opscore protocol.

    The TCP servers need to be started by awaiting the coroutine `.start`.
    Note that `.start` does not block so you will need to use asyncio's
    `.run_forever` or a similar system ::

        >>> loop = asyncio.get_event_loop()
        >>> my_actor = await LegacyActor('my_actor', '127.0.0.1', 9999, loop=loop).start()
        >>> loop.run_forever()

    Parameters
    ----------
    name : str
        The name of the actor.
    host : str
        The host where the TCP server will run.
    port : int
        The port of the TCP server.
    tron_host : str
        The host on which Tron is running.
    tron_port : int
        The port on which Tron is running.
    models : list
        A list of strings with the actors whose models will be tracked.
    version : str
        The version of the actor.
    loop
        The event loop. If `None`, the current event loop will be used.
    log_dir : str
        The directory where to store the logs. Defaults to
        ``$HOME/logs/<name>`` where ``<name>`` is the name of the actor.
    log : ~logging.Logger
        A `~logging.Logger` instance to be used for logging instead of creating
        a new one.
    schema : str
        The path to the datamodel schema for the actor, in JSON Schema format.
        If the schema is provided all replies will be validated against it.
        An invalid reply will fail and not be emitted. The schema can also be
        set when subclassing by setting the class ``schema`` attribute.

    """

    host = None
    port = None

    def __init__(self, name, host, port, tron_host=None, tron_port=None,
                 models=None, version=None, loop=None, log_dir=None,
                 log=None, verbose=False, schema=None):

        super().__init__(name, version=version, loop=loop,
                         log_dir=log_dir, log=log, verbose=verbose,
                         schema=schema)

        #: Mapping of user_id to transport
        self.transports = dict()

        self.host = host
        self.port = port

        # TCPStreamServer: The server to talk to this actor.
        self._server = TCPStreamServer(host, port, loop=self.loop,
                                       connection_callback=self.new_user,
                                       data_received_callback=self.new_command)

        if tron_host and tron_port:
            #: TronConnection: The client connection to Tron.
            self.tron = TronConnection(host=tron_host, port=tron_port,
                                       models=models, log=self.log)
        else:
            self.tron = None

        #: dict: Actor models.
        self.models = self.tron.models if self.tron else None

        self.timed_commands = TimedCommandList(self)

    def __repr__(self):

        return f'<{str(self)} (name={self.name!r}, host={self.host!r}, port={self.port})>'

    async def start(self):
        """Starts the server and the Tron client connection."""

        await self._server.start()
        self.log.info(f'running TCP server on {self.host}:{self.port}')

        # Start tron connection
        try:
            if self.tron:
                await self.tron.start()
                self.log.info('started tron connection at '
                              f'{self.tron.host}:{self.tron.port}')
            else:
                warnings.warn('starting LegacyActor without Tron connection.',
                              clu.CluWarning)
        except (ConnectionRefusedError, OSError) as ee:
            warnings.warn(f'connection to tron was refused: {ee}. '
                          'Some functionality will be limited.', clu.CluWarning)

        self.timed_commands.start()

        return self

    async def stop(self):
        """Stops the client connection and running tasks."""

        if self._server.is_serving():
            self._server.stop()

        await self.timed_commands.stop()

        if self.tron:
            self.tron.stop()

    async def run_forever(self):
        """Runs the actor forever, keeping the loop alive."""

        await self._server.serve_forever()

    def new_user(self, transport):
        """Assigns userID to new client connection."""

        if transport.is_closing():
            if hasattr(transport, 'user_id'):
                self.log.debug(f'user {transport.user_id} disconnected.')
                return self.transports.pop(transport.user_id)

        curr_ids = set(self.transports.keys())
        user_id = 1 if len(curr_ids) == 0 else max(curr_ids) + 1

        transport.user_id = user_id

        self.transports[user_id] = transport

        # report user information and additional info
        self.show_new_user_info(user_id)

        return

    def new_command(self, transport, command_str):
        """Handles a new command received by the actor."""

        commander_id = getattr(transport, 'user_id', 0)
        command_str = command_str.decode().strip()

        if not command_str:
            return
        try:
            command_id, command_body = parse_legacy_command(command_str)

            command = Command(command_string=command_body, commander_id=commander_id,
                              command_id=command_id, consumer_id=self.name,
                              actor=self, loop=self.loop, transport=transport)
        except clu.CommandError as ee:
            self.write('f',
                       {'text': f'Could not parse the command string: {ee!r}'},
                       user_id=commander_id)
            return

        return self.parse_command(command)

    @staticmethod
    def format_user_output(user_id, command_id, message_code, msg_str=None):
        """Formats a string to send to users."""

        msg_str = '' if msg_str is None else ' ' + msg_str

        return f'{user_id} {command_id:d} {message_code:s}{msg_str:s}'

    def show_new_user_info(self, user_id):
        """Shows information for new users. Called when a new user connects."""

        self.show_user_info(user_id)
        self.show_version(user_id=user_id)

        transport = self.transports[user_id]
        peername = transport.get_extra_info('peername')[0]
        self.log.debug(f'user {user_id} connected from {peername!r}.')

    def show_user_info(self, user_id):
        """Shows user information including your user_id."""

        num_users = len(self.transports)
        if num_users == 0:
            return

        msg = {'yourUserID': user_id,
               'num_users': num_users}

        self.write('i', msg, user_id=user_id)
        self.show_user_list()

    def show_user_list(self):
        """Shows a list of connected users. Broadcast to all users."""

        user_id_list = sorted(self.transports.keys())
        for user_id in user_id_list:
            transport = self.transports[user_id]
            peername = transport.get_extra_info('peername')[0]
            msg = {'UserInfo': f'{user_id}, {peername}'}
            self.write('i', msg)

    @staticmethod
    def get_user_command_id(command=None, user_id=None, command_id=None):
        """Returns commander_id, command_id based on user-supplied information.

        Parameters
        ----------
        command : Command
            User command; used as a default for ``user_id`` and
            ``command_id``.
        user_id : int
            If `None` then use ``command.user_id``.
        command_id : int
            If `None` then use ``command.command_id``.

        Returns
        -------
        user_id, command_id : `tuple`
            The commander ID and the command ID, parsed from the inputs. If
            they cannot be determined, returns zeros.

        """

        user_id = user_id or (command.commander_id if command else 0)
        command_id = command_id or (command.command_id if command else 0)

        return (user_id, command_id)

    def show_version(self, user_id=None):
        """Shows actor version."""

        msg = {'version': repr(self.version)}

        self.write('i', msg, user_id=user_id)

    def send_command(self, target, command_string, command_id=None):
        """Sends a command through the hub.

        Parameters
        ----------
        target : str
            The actor to command.
        command_string : str
            The command to send.
        command_id : int
            The command id. If `None`, a sequentially increasing value will
            be used. You should not specify a ``command_id`` unless you really
            know what you're doing.

        """

        if self.tron:
            command = self.tron.send_command(target, command_string,
                                             commander=f'{self.name}.{self.name}',
                                             mid=command_id)
            command.actor = self
            return command

        else:
            raise clu.CluError('cannot connect to tron.')

    def write(self, message_code='i', message=None, command=None, user_id=None,
              command_id=None, concatenate=True, broadcast=False,
              no_validate=False, **kwargs):
        """Writes a message to user(s).

        Parameters
        ----------
        message_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        message : dict
            The keywords to be output. Must be a dictionary of pairs
            ``{keyword: value}``. If ``value`` is a list it will be converted
            into a comma-separated string. To prevent unexpected casting,
            it is recommended for ``value`` to always be a string.
        command : Command
            User command; used as a default for ``user_id`` and
            ``command_id``. If the command is done, it is ignored.
        user_id : int
            The user (transport) to which to write. `None` defaults to 0.
        command_id : int
            If `None` then use ``command.command_id``.
        concatenate : bool
            Concatenates all the keywords to be output in a single
            reply with the keyword-values joined with semicolons. Otherwise
            each keyword will be output as a different message.
        broadcast : bool
            Whether to broadcast the reply. Equivalent to ``user_id=0``.
        no_validate : bool
            Do not validate the reply against the actor schema. This is
            ignored if the actor was not started with knowledge of its own
            schema.
        kwargs
            Keyword arguments that will be added to the message. If a keyword
            is both in ``message`` and in ``kwargs``, the value in ``kwargs``
            supersedes ``message``.

        """

        # For a reply, the commander ID is the user assigned to the transport
        # that issues this command.
        transport = command.transport if command else None
        user_id = (transport.user_id if transport else None) or user_id

        if broadcast:
            user_id = 0
            command_id = 0

        user_id, command_id = self.get_user_command_id(
            command=command, user_id=user_id, command_id=command_id)

        if message is None or (isinstance(message, str) and message.strip() == ''):
            message = {}
        elif isinstance(message, str):
            message = {'text': message}
        elif not isinstance(message, dict):
            raise TypeError('invalid message type ' + str(type(message)))

        if not no_validate and hasattr(self, 'schema') and self.schema is not None:
            result, err = self.schema.update_model(message)
            if result is False:
                message = {'error': f'Failed validating the reply: {err}'}
                message_code = 'e'

        message.update(kwargs)

        lines = []
        for keyword in message:
            value = clu.format_value(message[keyword])
            lines.append(f'{keyword}={value}')

        if concatenate:
            lines = ['; '.join(lines)]

        for line in lines:

            full_msg_str = self.format_user_output(user_id, command_id,
                                                   message_code, line)
            msg = (full_msg_str + '\n').encode()

            if user_id is None or user_id == 0 or transport is None:
                for transport in self.transports.values():
                    transport.write(msg)
            else:
                transport.write(msg)

            log_reply(self.log, message_code, full_msg_str)


class LegacyActor(ClickParser, BaseLegacyActor):
    """A legacy actor that uses the `.ClickParser`."""
