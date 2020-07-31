#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-17
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import re

import clu
from clu.tools import CommandStatus, StatusMixIn


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
    parent : .BaseCommand
        Another `.BaseCommand` object that is issuing this subcommand. If they
        are not specified, sets ``commander_id`` and ``consumer_id``
        appropriately.
    status_callback : function
        A function to call when the status changes.
    call_now : bool
        Whether to call ``status_callback`` when initialising the command.
    default_keyword : str
        The keyword to use when writing a message that does not specify a
        keyword.
    loop
        The event loop.

    """

    def __init__(self, commander_id=0, command_id=0, consumer_id=0, parent=None,
                 status_callback=None, call_now=False, default_keyword='text',
                 loop=None):

        self.commander_id = commander_id
        self.consumer_id = consumer_id
        self.command_id = command_id

        self.parent = parent

        if self.parent:
            if not isinstance(self.parent, BaseCommand):
                raise clu.CluError('invalid parent type.')
            if self.parent.command_id != 0 and self.command_id == self.parent.command_id:
                raise clu.CluError('subcommand cannot have the '
                                   'same command_id as the parent.')

            self.commander_id = self.commander_id or self.parent.commander_id
            self.consumer_id = self.consumer_id or self.parent.consumer_id

        self.default_keyword = default_keyword
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

        self.set_status(status)

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

            self.write(status_code, message, **kwargs)

            self._status = status

            self.do_callbacks()

            # If the command is done, set the result of the future.
            if self._status.is_done:
                self.set_result(self)

            # Set the status watcher
            if self.watcher is not None:
                self.watcher.set()

    def finish(self, *args, **kwargs):
        """Convenience method to mark a command `~.CommandStatus.DONE`."""

        self.set_status(CommandStatus.DONE, *args, **kwargs)
        return self

    def fail(self, *args, **kwargs):
        """Convenience method to mark a command `~.CommandStatus.FAILED`."""

        self.set_status(CommandStatus.FAILED, *args, **kwargs)
        return self

    def debug(self, *args, **kwargs):
        """Writes a debug-level message."""

        self.write('d', *args, **kwargs)

    def info(self, *args, **kwargs):
        """Writes an info-level message."""

        self.write('i', *args, **kwargs)

    def warning(self, *args, **kwargs):
        """Writes a warning-level message."""

        self.write('w', *args, **kwargs)

    def error(self, *args, **kwargs):
        """Writes an error-level message (does not fail the command)."""

        self.write('e', *args, **kwargs)

    def write(self, message_code='i', message=None, broadcast=False, **kwargs):
        """Writes to the user(s).

        Parameters
        ----------
        message_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        message : str or dict
            The text to be output. If `None`, only the code will be written.

        """

        if message is None:
            message = {}
        elif isinstance(message, dict):
            pass
        elif isinstance(message, str):
            message = {self.default_keyword: message}
        else:
            raise ValueError(f'invalid message {message!r}')

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

        if not self.actor and kwargs.get('parent', None):
            self.actor = self.parent.actor

        #: The `~click.Context` running this command. Only relevant if
        #: using the built-in click-based parser.
        self.ctx = None

        self.transport = transport

    def parse(self):
        """Parses the command."""

        if not self.actor:
            raise clu.CluError('the actor is not defined. Cannot parse command.')

        self.actor.parse_command(self)

        return self

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
