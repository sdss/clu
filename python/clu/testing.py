#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-10-05
# @Filename: testing.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import re
import types
import unittest.mock

from asynctest import CoroutineMock

from clu.command import Command


__all__ = ['MockReply', 'MockReplyList', 'setup_test_actor', 'TestCommand']


class MockReply(dict):
    """Stores a reply written to a transport.

    Keywords are stored as part of the dictionary.

    Attributes
    ----------
    user_id : int
        The user ID of the client to which the reply was sent.
    command_id : int
        The command ID of the command that produced this reply.
    flag : str
        The message type flag.

    """

    def __init__(self, command_id, user_id, flag, keywords={}):

        self.command_id = command_id
        self.user_id = user_id
        self.flag = flag

        dict.__init__(self, keywords)

    def __repr__(self):
        return (f'<MockReply ({self.user_id} {self.command_id} '
                f'{self.flag} {super().__repr__()})>')


class MockReplyList(list):
    """Stores replies as `.MockReply` objects."""

    PATTERN = re.compile(r'([0-9]+)\s+([0-9]+)\s+((?:[a-z]|\:))\s+(.*)')

    def __init__(self):
        list.__init__(self)

    def parse_reply(self, reply):
        """Parses a reply and construct a `.MockReply`, which is appended."""

        if isinstance(reply, bytes):
            reply = reply.decode()

        match = self.PATTERN.match(reply)
        if not match:
            return

        user_id, command_id, flag, keywords_raw = match.groups()

        keywords = {}
        for keyword_raw in keywords_raw.split(';'):
            if keyword_raw.strip() == '':
                continue
            name, value = keyword_raw.split('=')
            keywords[name] = value

        list.append(self, MockReply(int(user_id), int(command_id), flag, keywords))

    def clear(self):
        list.__init__(self)


async def setup_test_actor(actor, user_id=1):
    """Setups an actor for testing, mocking the client transport.

    Takes an ``actor`` and modifies it in two ways:

    - Adds a ``invoke_mock_command`` method to it that allows to submit a
      command string as if it had been received from a transport.

    - Mocks a client transport with ``user_id`` that is connected to the actor.
      Messages written to the transport are stored as `.MockReply` in a
      `.MockReplyList` that is accessible via a new ``actor.mock_replies``
      attribute.

    The actor is modified in place and also returned.

    """

    def invoke_mock_command(self, command_str, command_id=0):
        if isinstance(command_str, str):
            command_str = command_str.encode('utf-8')
        full_command = f' {command_id} '.encode('utf-8') + command_str
        return self.new_command(actor.user_dict['mock_user'], full_command)

    actor.run = CoroutineMock(return_value=actor)

    # Adds an invoke_mock_command method.
    # We use types.MethodType to bind a method to an existing instance
    # (see http://bit.ly/35buk1m)
    actor.invoke_mock_command = types.MethodType(invoke_mock_command, actor)

    # Mocks a user transport and stores the replies in a MockReplyListobject
    actor.mock_replies = MockReplyList()

    mock_transport = unittest.mock.MagicMock(spec=asyncio.Transport)
    mock_transport.user_id = user_id
    mock_transport.write.side_effect = actor.mock_replies.parse_reply

    actor.user_dict['mock_user'] = mock_transport

    actor = await actor.run()

    return actor


class TestCommand(Command):
    """A `.Command` that can be reset."""

    def reset(self):
        """Resets the command."""

        self._status = self.flags.READY

        if self.watcher:
            self.watcher.clear()
        self.watcher = None

        asyncio.Future.__init__(self, loop=self.loop)
