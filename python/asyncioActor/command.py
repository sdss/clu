#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-17
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2018-09-09 19:56:18


from __future__ import absolute_import, division, print_function

import re

from .base import CallbackMixIn, StatusFlags
from .core import exceptions


__all__ = ['Command', 'UserCommand']


class Command(CallbackMixIn):
    """Base class for commands of all types (user and device).

    Parameters
    ----------
    cmd_str : str
        The command string to be parsed.
    user_id : int
        The ID of the user issuing this command.
    cmd_id : int
        The ID associated to this command.

    """

    def __init__(self, cmd_str, user_id=0, cmd_id=0, callback=None, call_now=False):

        self._cmd_str = cmd_str
        self.user_id = int(user_id)
        self.cmd_id = int(cmd_id)
        self._status = StatusFlags.READY

        self._write_to_users = None  # Set by the actor.
        self.user_commanded = False

        CallbackMixIn.__init__(callback=callback, call_now=call_now)

    @property
    def cmd_str(self):
        return self._cmd_str

    @property
    def status(self):
        """The status of the command."""

        return self._status

    def setState(self, newState, textMsg=None, hubMsg=None):
        """Set the state of the command and call callbacks.

        If new state is done then remove all callbacks (after calling them).

        @param[in] newState  new state of command
        @param[in] textMsg  a message to be printed using the Text keyword; if None then not changed
        @param[in] hubMsg  a message in keyword=value format (without a header); if None then not changed

        You can set both textMsg and hubMsg, but typically only one or the other will be displayed
        (depending on the situation).

        If the new state is Failed then please supply a textMsg and/or hubMsg.

        Error conditions:
        - Raise RuntimeError if this command is finished.
        """


        if textMsg is not None:
            self._textMsg = str(textMsg)
        if hubMsg is not None:
            self._hubMsg = str(hubMsg)
        log.info(str(self))
        self._basicDoCallbacks(self)
        if self.isDone:
            self._timeoutTimer.cancel()
            self._removeAllCallbacks()
            self.untrackCmd()

    @status.setter
    def status(self, value):

        if self.is_done:
            raise RuntimeError(f'Command {self!s} is done; cannot change state')

        if isinstance(value, str):
            flag = getattr(StatusFlags, value.upper())

        assert flag.is_combination is False, 'cannot set a combination flag.'
        assert flag in StatusFlags.ALL_STATES, 'invalid flag'

        self._status = flag

        self.do_callbacks()

    def get_key_val_msg(self):
        """Get full message data as (msg_code, msg_str).

        Return:
            msg_code : str
                Message code (e.g. 'W').
            msg_str : str
                Message string: a combination of _textMsg and _hubMsg in keyword-value format.
            Warning: he "Text" keyword will be repeated if _textMsg is non-empty and _hubMsg contains "Text="
        """

        msg_code = self.state.msg_code

        msgInfo = []
        if self._hubMsg:
            msgInfo.append(self._hubMsg)
        if self._textMsg or textPrefix:
            msgInfo.append("text=%s" % (quoteStr(textPrefix + self._textMsg),))
        msgStr = "; ".join(msgInfo)
        return (msgCode, msgStr)

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

    def __init__(self, user_id=0, cmd_str='', **kwargs):

        Command.__init__(self, cmd_str=cmd_str, user_id=user_id, **kwargs)
        self.parse_cmd_str(cmd_str)

    def parse_cmd_str(self, cmd_str):
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
