#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-10-05
# @Filename: testing.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import json
import re
import sys
import types
import unittest.mock

import clu
from clu.command import Command


if sys.version_info.major == 3 and sys.version_info.minor >= 8:
    CoroutineMock = unittest.mock.AsyncMock
else:
    try:
        from asynctest import CoroutineMock
    except ImportError:
        raise ImportError('clu.testing requires asynctest if Python < 3.8.')


__all__ = ['MockReply', 'MockReplyList', 'setup_test_actor']


class MockReply(dict):
    """Stores a reply written to a transport.

    The data of the message is stored as part of the dictionary.

    Parameters
    ----------
    user_id : int
        The user ID of the client to which the reply was sent.
    command_id : int
        The command ID of the command that produced this reply.
    flag : str
        The message type flag.
    data : dict
        The payload of the message.

    """

    def __init__(self, command_id, user_id, flag, data={}):

        self.command_id = command_id
        self.user_id = user_id
        self.flag = flag

        dict.__init__(self, data)

    def __repr__(self):
        return (f'<MockReply ({self.user_id} {self.command_id} '
                f'{self.flag} {super().__repr__()})>')


class MockReplyList(list):
    """Stores replies as `.MockReply` objects."""

    LEGACY_REPLY_PATTERN = re.compile(r'([0-9]+)\s+([0-9]+)\s+((?:[a-z]|\:|\>|\!))\s+(.*)')

    def __init__(self, actor):

        self.actor = actor

        list.__init__(self)

    def parse_reply(self, reply):
        """Parses a reply and construct a `.MockReply`, which is appended."""

        if isinstance(reply, bytes):
            reply = reply.decode()

        if issubclass(self.actor.__class__, clu.LegacyActor):

            match = self.LEGACY_REPLY_PATTERN.match(reply)
            if not match:
                return

            user_id, command_id, flag, keywords_raw = match.groups()

            user_id = int(user_id)
            command_id = int(command_id)

            data = {}
            for keyword_raw in keywords_raw.split(';'):
                if keyword_raw.strip() == '':
                    continue
                name, value = keyword_raw.split('=', maxsplit=1)
                data[name] = value

        elif issubclass(self.actor.__class__, clu.JSONActor):

            reply = json.loads(reply)

            header = reply['header']
            user_id = header.pop('commander_id', None)
            command_id = header.pop('command_id', None)
            flag = header.pop('message_code', 'd')

            data = reply['data']

        else:
            raise RuntimeError('actor must be LegacyActor or JSONActor.')

        list.append(self, MockReply(user_id, command_id, flag, data))

    def clear(self):
        list.__init__(self)

    def __contains__(self, m):

        return any([m in reply[kw] for reply in self for kw in reply.keys()])


async def setup_test_actor(actor, user_id=1):
    """Setups an actor for testing, mocking the client transport.

    Takes an ``actor`` and modifies it in two ways:

    - Adds a ``invoke_mock_command`` method to it that allows to submit a
      command string as if it had been received from a transport.

    - Mocks a client transport with ``user_id`` that is connected to the actor.
      Messages written to the transport are stored as `.MockReply` in a
      `.MockReplyList` that is accessible via a new ``actor.mock_replies``
      attribute.

    The actor is modified in place and returned.

    """

    if not issubclass(actor.__class__, (clu.LegacyActor, clu.JSONActor)):
        raise RuntimeError('setup_test_actor is only usable with '
                           'LegacyActor or JSONActor actors.')

    def invoke_mock_command(self, command_str, command_id=0):
        if isinstance(command_str, str):
            command_str = command_str.encode('utf-8')
        full_command = f' {command_id} '.encode('utf-8') + command_str
        return self.new_command(actor.transports['mock_user'], full_command)

    actor.start = CoroutineMock(return_value=actor)

    # Adds an invoke_mock_command method.
    # We use types.MethodType to bind a method to an existing instance
    # (see http://bit.ly/35buk1m)
    actor.invoke_mock_command = types.MethodType(invoke_mock_command, actor)

    # Mocks a user transport and stores the replies in a MockReplyListobject
    actor.mock_replies = MockReplyList(actor)

    mock_transport = unittest.mock.MagicMock(spec=asyncio.Transport)
    mock_transport.user_id = user_id
    mock_transport.write.side_effect = actor.mock_replies.parse_reply

    actor.transports['mock_user'] = mock_transport

    actor = await actor.start()

    return actor


class TestCommand(Command):  # pragma: no cover
    """A `.Command` that can be reset."""

    def reset(self):
        """Resets the command."""

        self._status = self.flags.READY

        if self.watcher:
            self.watcher.clear()
        self.watcher = None

        asyncio.Future.__init__(self, loop=self.loop)
