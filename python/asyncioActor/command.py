#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-17
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-06 18:35:15

import asyncio
import re

from asyncioActor.base import CommandStatus, StatusMixIn
from asyncioActor.core import exceptions


__all__ = ['BaseCommand', 'Command']


class BaseCommand(StatusMixIn):
    """Base class for commands of all types (user and device).

    Parameters
    ----------
    cmd_str : str
        The command string to be parsed.
    user_id : int
        The ID of the user issuing this command.
    cmd_id : int
        The ID associated to this command.
    status_callback : function
        A function to call when the status changes.
    call_now : bool
        Whether to call ``status_callback`` when initialising the command.
    loop
        The event loop.
    actor : ~asyncioActor.actor.Actor
        The actor associated with this command.

    """

    def __init__(self, user_id=0, command_id=0, status_callback=None,
                 call_now=False, loop=None, actor=None):

        self.user_id = int(user_id)
        self.command_id = int(command_id)

        # Set by the actor.
        self.actor = actor

        self.loop = loop or asyncio.get_event_loop()

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

    def set_status(self, status, message=None):
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
            msg_str = None if message is None else f'text="{message}"'

            self.write(status_code, msg_str)

            self._status = status

            self.do_callbacks()

            if self.watcher is not None:
                self.watcher.set()

    def write(self, msg_code, msg_str=None, user_id=None):
        """Writes to the user(s).

        Parameters
        ----------
        msg_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        msg_str : str
            The text to be output. If `None`, only the code will be written.
        user_id : int
            The user to which to send this message. Defaults to the command
            ``user_id``.

        """

        if not self.actor:
            raise exceptions.CommandError('An actor has not been defined for '
                                          'this command. Cannot write to users.')

        self.actor.write(msg_code, msg_str=msg_str, command=self)


class Command(BaseCommand):
    """A command from a user (typically the hub)"""

    _HEADER_BODY_RE = re.compile(
        r'((?P<command_id>\d+)(?:\s+\d+)?\s+)?((?P<command_body>[A-Za-z_].*))?$')

    def __init__(self, command_string='', **kwargs):

        BaseCommand.__init__(self, **kwargs)

        self.raw_command_string = command_string
        self.body = None

        self.parse_command_string(command_string)

    def parse_command_string(self, command_string):
        """Parse command."""

        command_match = self._HEADER_BODY_RE.match(command_string)
        if not command_match:
            raise exceptions.CommandError(f'Could not parse command {command_string!r}')

        command_dict = command_match.groupdict('')
        command_id_str = command_dict['command_id']

        if command_id_str:
            self.command_id = int(command_id_str)
        else:
            self.command_id = 0

        self.body = command_dict.get('command_body', '')
