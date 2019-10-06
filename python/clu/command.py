#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-17
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-10-05 19:38:07

import asyncio
import re

import clu
from clu.base import CommandStatus, StatusMixIn


__all__ = ['BaseCommand', 'Command', 'parse_legacy_command']


class BaseCommand(asyncio.Future, StatusMixIn):
    """Base class for commands of all types (user and device).

    A `BaseCommand` instance is a `~asyncio.Future` whose result gets set
    when the status is done (either successfully or not).

    Parameters
    ----------
    cmd_str : str
        The command string to be parsed.
    commander_id : str or int
        The ID of the commander issuing this command. Can be a string or an
        integer. Normally the former is used for new-style actor and the latter
        for legacy actors.
    command_id : str or int
        The ID associated to this command. As with the commander_id, it can be
        a string or an integer
    consumer_id : str or int
        The actor that is consuming this command. Normally this is our own
        actor but if we are commanding another actor ``consumer_id`` will
        be the destination actor.
    status_callback : function
        A function to call when the status changes.
    call_now : bool
        Whether to call ``status_callback`` when initialising the command.
    loop
        The event loop.

    """

    def __init__(self, commander_id=0, command_id=0, consumer_id=0,
                 status_callback=None, call_now=False, loop=None):

        self.commander_id = commander_id
        self.consumer_id = consumer_id
        self.command_id = command_id

        self.loop = loop or asyncio.get_event_loop()

        asyncio.Future.__init__(self, loop=self.loop)

        StatusMixIn.__init__(self, CommandStatus, initial_status=CommandStatus.READY,
                             callback_func=status_callback, call_now=call_now)

    @property
    def status(self):
        """Returns the status."""

        return self._status

    @status.setter
    def status(self, status):
        """Sets the status. A message is output to the users.

        This setter calls `.set_status` with an empty message to the users.

        Parameters
        ----------
        status : CommandStatus or int or str
            The status to set, either as a `CommandStatus` value or the
            integer associated with the maskbit. If ``value`` is a string,
            loops over the bits in `CommandStatus` and assigns the one whose
            name matches.

        """

        self.set_state(status)

    def set_status(self, status, message=None, **kwargs):
        """Same as `.status` but allows to specify a message to the users."""

        if self.status.is_done:
            raise RuntimeError('cannot modify a done command.')

        if not isinstance(status, self.flags):
            if isinstance(status, int):
                status = self.flags(int)
            elif isinstance(status, str):
                for bit in self.flags:
                    if status.lower() == bit.name.lower():
                        status = bit
                        break
            else:
                raise ValueError(f'status {status!r} is not a valid command status.')

        if status != self._status:

            status_code = status.code

            if message is None:
                pass
            elif isinstance(message, dict):
                pass
            else:
                message = {'text': message}

            self.write(status_code, message, **kwargs)

            self._status = status

            self.do_callbacks()

            # If the command is done, set the result of the future.
            if self._status.is_done:
                self.set_result(self.status)

            # Set the status watcher
            if self.watcher is not None:
                self.watcher.set()

    def write(self, message_code='i', message=None, broadcast=False, **kwargs):
        """Writes to the user(s).

        Parameters
        ----------
        message_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        message : str or dict
            The text to be output. If `None`, only the code will be written.

        """

        if not self.actor:
            raise clu.CommandError('An actor has not been defined for '
                                   'this command. Cannot write to users.')

        result = self.actor.write(message_code, message=message, command=self,
                                  broadcast=broadcast, **kwargs)

        if asyncio.iscoroutine(result):
            self.loop.create_task(result)


class Command(BaseCommand):
    """A command from a user.

    Parameters
    ----------
    command_string : str
        The string that defines the body of the command.
    actor : ~clu.actor.BaseActor
        The actor instance associated to this command.
    transport
        The TCP transport associated with this command (only relevant
        for `.LegacyActor` commands).

    """

    def __init__(self, command_string='', actor=None, transport=None, **kwargs):

        BaseCommand.__init__(self, **kwargs)

        #: The raw command string.
        self.raw_command_string = command_string

        #: The body of the command.
        self.body = command_string

        #: The actor in which this command will run.
        self.actor = actor

        #: The `~click.Context` running this command. Only relevant if
        #: using the built-in click-based parser.
        self.ctx = None

        self.transport = transport

    def __str__(self):

        return (f'<Command (commander_id={self.commander_id!r}, '
                f'command_id={self.command_id!r}, body={self.body!r})>')


def parse_legacy_command(command_string):
    """Parses a command received by a legacy actor.

    Parameters
    ----------
    command_string : str
        The command to parse, including an optional header.

    Returns
    -------
    command_id, command_body : tuple
        The command ID, and the command body parsed from the command
        string.

    """

    _HEADER_BODY_RE = re.compile(r'((?P<cmdID>\d+)(?:\s+\d+)?\s+)?((?P<cmdBody>[A-Za-z_].*))?$')

    command_match = _HEADER_BODY_RE.match(command_string)
    if not command_match:
        raise clu.CommandError(f'Could not parse command {command_string!r}')

    command_dict = command_match.groupdict('')

    command_id = command_dict['cmdID']
    if command_id:
        command_id = int(command_id)
    else:
        command_id = 0

    command_body = command_dict.get('cmdBody', '').strip()

    return command_id, command_body
