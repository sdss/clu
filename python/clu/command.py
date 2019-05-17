#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-17
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-17 16:05:08

import asyncio
import re

import clu
from clu.base import CommandStatus, StatusMixIn


__all__ = ['BaseCommand', 'Command']


class BaseCommand(StatusMixIn):
    """Base class for commands of all types (user and device).

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
    status_callback : function
        A function to call when the status changes.
    call_now : bool
        Whether to call ``status_callback`` when initialising the command.
    loop
        The event loop.
    actor : ~clu.actor.Actor
        The actor associated with this command.

    """

    def __init__(self, commander_id=0, command_id=0, status_callback=None,
                 call_now=False, loop=None, actor=None):

        self.commander_id = commander_id
        self.command_id = command_id

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

            if message is None:
                pass
            elif isinstance(message, dict):
                pass
            else:
                message = {'text': message}

            self.write(status_code, message)

            self._status = status

            self.do_callbacks()

            if self.watcher is not None:
                self.watcher.set()

    def write(self, msg_code, message=None, broadcast=False, **kwargs):
        """Writes to the user(s).

        Parameters
        ----------
        msg_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        message : str or dict
            The text to be output. If `None`, only the code will be written.

        """

        if not self.actor:
            raise clu.CommandError('An actor has not been defined for '
                                   'this command. Cannot write to users.')

        result = self.actor.write(msg_code, message=message, command=self,
                                  broadcast=broadcast, **kwargs)

        if asyncio.iscoroutine(result):
            self.loop.create_task(result)


class Command(BaseCommand):
    """A command from a user (typically the hub)."""

    _HEADER_BODY_RE = re.compile(
        r'((?P<command_id>\d+)(?:\s+\d+)?\s+)?((?P<command_body>[A-Za-z_].*))?$')

    def __init__(self, command_string='', **kwargs):

        BaseCommand.__init__(self, **kwargs)

        #: The raw command string.
        self.raw_command_string = command_string

        #: The body of the command, after parsing.
        self.body = None

        #: The actor in which this command will run.
        self.actor = None

        self.parse_command_string(command_string)

    def __str__(self):

        return (f'<Command (commander_id={self.commander_id!r}, '
                f'command_id={self.command_id!r}, body={self.body!r})>')

    def parse_command_string(self, command_string):
        """Parse command."""

        command_match = self._HEADER_BODY_RE.match(command_string)
        if not command_match:
            raise clu.CommandError(f'Could not parse command {command_string!r}')

        command_dict = command_match.groupdict('')
        command_id_str = command_dict['command_id']

        if command_id_str:
            self.command_id = int(command_id_str)
        else:
            # Only set command_id to 0 if we haven't set it somehow else.
            if self.command_id is None:
                self.command_id = 0

        self.body = command_dict.get('command_body', '')
