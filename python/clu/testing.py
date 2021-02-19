#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-10-05
# @Filename: testing.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import json
import re
import sys
import types
import unittest.mock

from typing import Any, Dict, List, Optional, TypeVar, Union, cast

import aio_pika
import pamqp.specification
from aiormq.types import DeliveredMessage
from pamqp.header import ContentHeader

import clu
from clu.actor import AMQPActor, JSONActor
from clu.command import Command
from clu.legacy.actor import LegacyActor


if sys.version_info.major == 3 and sys.version_info.minor >= 8:
    CoroutineMock = unittest.mock.AsyncMock
else:
    try:
        from asynctest import CoroutineMock
    except ImportError:
        raise ImportError("clu.testing requires asynctest if Python < 3.8.")


__all__ = ["MockReply", "MockReplyList", "setup_test_actor"]


class MockedActor(JSONActor, LegacyActor, AMQPActor):
    invoke_mock_command: Any
    mock_replies: List[MockReply]


T = TypeVar("T", bound=MockedActor)


class MockReply(dict):
    """Stores a reply written to a transport.

    The data of the message is stored as part of the dictionary.

    Parameters
    ----------
    user_id
        The user ID of the client to which the reply was sent.
    command_id
        The command ID of the command that produced this reply.
    flag
        The message type flag.
    data
        The payload of the message.
    """

    def __init__(
        self,
        command_id: int,
        user_id: int,
        flag: str,
        data: Dict[str, Any] = {},
    ):

        self.command_id = command_id
        self.user_id = user_id
        self.flag = flag

        dict.__init__(self, data)

    def __repr__(self):
        return (
            f"<MockReply ({self.user_id} {self.command_id} "
            f"{self.flag} {super().__repr__()})>"
        )


class MockReplyList(list):
    """Stores replies as `.MockReply` objects."""

    LEGACY_REPLY_PATTERN = re.compile(
        r"([0-9]+)\s+([0-9]+)\s+((?:[a-z]|\:|\>|\!))\s+(.*)"
    )

    def __init__(self, actor):

        self.actor = actor

        list.__init__(self)

    def parse_reply(
        self,
        reply: Union[bytes, str, aio_pika.Message],
        routing_key: Optional[str] = None,
    ):
        """Parses a reply and construct a `.MockReply`, which is appended."""

        if isinstance(reply, bytes):
            reply = reply.decode()

        if issubclass(self.actor.__class__, clu.LegacyActor):
            reply = cast(str, reply)
            match = self.LEGACY_REPLY_PATTERN.match(reply)
            if not match:
                return

            user_id, command_id, flag, keywords_raw = match.groups()

            user_id = int(user_id)
            command_id = int(command_id)

            data = {}
            for keyword_raw in keywords_raw.split(";"):
                if keyword_raw.strip() == "":
                    continue
                name, value = keyword_raw.split("=", maxsplit=1)
                data[name] = value

        elif issubclass(self.actor.__class__, clu.JSONActor):
            reply = cast(str, reply)
            reply_dict: Dict[str, Any] = json.loads(reply)

            header = reply_dict["header"]
            user_id = header.pop("commander_id", None)
            command_id = header.pop("command_id", None)
            flag = header.pop("message_code", "d")

            data = reply_dict["data"]

        elif issubclass(self.actor.__class__, clu.AMQPActor):
            reply = cast(aio_pika.Message, reply)

            header = reply.headers

            user_id = header.get("commander_id", None)
            command_id = header.get("command_id", None)
            flag = header.get("message_code", "d")

            data = json.loads(reply.body.decode())

        else:
            raise RuntimeError("This type of actor is not supported")

        list.append(self, MockReply(user_id, command_id, flag, data))

    def clear(self):
        list.__init__(self)

    def __contains__(self, m):

        return any([m in reply[kw] for reply in self for kw in reply.keys()])


async def setup_test_actor(actor: T, user_id: int = 1) -> T:
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

    if not issubclass(actor.__class__, (clu.LegacyActor, clu.JSONActor, clu.AMQPActor)):
        raise RuntimeError("setup_test_actor is not implemented for this type of actor")

    def invoke_mock_command(self, command_str, command_id=0):
        if issubclass(actor.__class__, (clu.LegacyActor, clu.JSONActor)):
            if isinstance(command_str, str):
                command_str = command_str.encode("utf-8")
            full_command = f" {command_id} ".encode("utf-8") + command_str
            return self.new_command(actor.transports["mock_user"], full_command)
        elif issubclass(actor.__class__, clu.AMQPActor):
            command_id = str(command_id)
            headers = {"command_id": command_id, "commander_id": "mock_test_client"}
            header = ContentHeader(
                properties=pamqp.specification.Basic.Properties(
                    content_type="text/json",
                    headers=headers,
                )
            )
            message_body = {"command_string": command_str}
            message = aio_pika.IncomingMessage(
                DeliveredMessage(
                    pamqp.specification.Basic.Deliver(),
                    header,
                    json.dumps(message_body).encode(),
                    None,
                ),
            )
            return self.new_command(message, ack=False)

    actor.start = CoroutineMock(return_value=actor)

    # Adds an invoke_mock_command method.
    # We use types.MethodType to bind a method to an existing instance
    # (see http://bit.ly/35buk1m)
    actor.invoke_mock_command = types.MethodType(invoke_mock_command, actor)

    # Mocks a user transport and stores the replies in a MockReplyListobject
    actor.mock_replies = MockReplyList(actor)

    if issubclass(actor.__class__, (clu.LegacyActor, clu.JSONActor)):
        mock_transport = unittest.mock.MagicMock(spec=asyncio.Transport)
        mock_transport.user_id = user_id
        mock_transport.write.side_effect = actor.mock_replies.parse_reply
        actor.transports["mock_user"] = mock_transport
    elif issubclass(actor.__class__, clu.AMQPActor):
        actor.connection.exchange = unittest.mock.MagicMock()
        actor.connection.exchange.publish = CoroutineMock(
            side_effect=actor.mock_replies.parse_reply
        )

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
