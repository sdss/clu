#!/usr/bin/env python
# encoding: utf-8
#
# @Author: José Sánchez-Gallego
# @Date: Jan 17, 2018
# @Filename: command.py
# @License: BSD 3-Clause
# @Copyright: José Sánchez-Gallego


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import re

from .core import exceptions


__all__ = ['Command', 'UserCommand']


class Command(object):
    """Base class for commands of all types (user and device)."""

    DONE = 'done'
    CANCELLED = 'cancelled'
    FAILED = 'failed'
    READY = 'ready'
    RUNNING = 'running'
    CANCELLING = 'cancelling'
    FAILING = 'failing'
    ACTIVE_STATES = frozenset((RUNNING, CANCELLING, FAILING))
    FAILED_STATES = frozenset((CANCELLED, FAILED))
    FAILING_STATES = frozenset((CANCELLING, FAILING))
    DONE_STATES = frozenset((DONE,)) | FAILED_STATES
    ALL_STATES = frozenset((READY,)) | ACTIVE_STATES | DONE_STATES

    _MSG_CODE_DICT = dict(
        ready='i',
        running='i',
        cancelling='w',
        failing='w',
        cancelled='f',
        failed='f',
        debug='d',
        done=':')

    _INV_MSG_CODE_DICT = dict((val, key) for key, val in _MSG_CODE_DICT.items())

    def __init__(self, cmd_str, user_id=0, cmd_id=0):
        """Constructs a BaseCmd."""

        self._cmd_str = cmd_str
        self.user_id = int(user_id)
        self.cmd_id = int(cmd_id)
        self._state = self.READY

        self._write_to_users = None  # Set by the actor.
        self.user_commanded = False

    @property
    def cmd_str(self):
        return self._cmd_str

    @property
    def did_fail(self):
        """Command failed or was cancelled."""

        return self._state in self.FAILED_STATES

    @property
    def is_active(self):
        """Command is running, canceling or failing."""

        return self._state in self.ACTIVE_STATES

    @property
    def is_done(self):
        """Command is done (whether successfully or not)."""

        return self._state in self.DONE_STATES

    @property
    def is_failing(self):
        """Command is being cancelled or is failing."""

        return self._state in self.FAILED_STATES

    @property
    def msg_code(self):
        """The hub message code appropriate to the current state."""

        return self._MSG_CODE_DICT[self._state]

    @property
    def state(self):
        """The state of the command.

        Must be a string which is one of the state constants,
        e.g. ``self.DONE``.

        """

        return self._state

    def set_write_to_users(self, write_to_users_func):
        """Sets the function to call when writing to users."""

        if self._write_to_users is not None:
            raise RuntimeError('Write to users is already set')
        else:
            self._write_to_users = write_to_users_func

    def write_to_users(self, msg_code, msg_str, user_id=None, cmd_id=None):

        if self._write_to_users is None:
            print(f'{self} writeToUsers not set: ', msg_code, msg_str, user_id, cmd_id, '!!!')
        else:
            self._write_to_users(msg_code, msg_str, user_id, cmd_id)


class UserCommand(Command):
    """A command from a user (typically the hub)"""

    _HEADER_BODY_RE = re.compile(r'((?P<cmd_id>\d+)(?:\s+\d+)?\s+)?((?P<cmd_body>[A-Za-z_].*))?$')

    def __init__(self, user_id=0, cmd_str=''):

        Command.__init__(self, cmd_str=cmd_str, user_id=user_id)
        self.parseCmdStr(cmd_str)

    def parseCmdStr(self, cmd_str):
        """Parse command."""

        cmd_match = self._HEADER_BODY_RE.match(cmd_str)
        if not cmd_match:
            raise exceptions.CommandError(f'Could not parse command {cmd_str!r}')

        cmd_dict = cmd_match.groupdict('')
        cmd_id_str = cmd_dict['cmd_id']

        if cmd_id_str:
            self.cmd_id = int(cmd_id_str)
        else:
            self.cmd_id = 0

        self.cmd_body = cmd_dict.get('cmd_body', '')
