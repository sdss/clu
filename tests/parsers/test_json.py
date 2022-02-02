#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-27
# @Filename: test_parser.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import json

import pytest

from clu.actor import AMQPBaseActor
from clu.parsers import JSONParser

from ..conftest import DATA_DIR


pytestmark = [pytest.mark.asyncio]


async def command1(command, payload):
    return command.finish(**payload)


def command2(command, payload):
    pass


class AMQPJSONActor(JSONParser, AMQPBaseActor):

    callbacks = {"command1": command1, "command2": command2}


@pytest.fixture
async def json_parser_actor(rabbitmq, event_loop):

    actor = AMQPJSONActor(
        name="amqp_json_actor",
        port=rabbitmq.args["port"],
        schema=DATA_DIR / "schema.json",
    )

    await actor.start()

    yield actor

    await actor.stop()


async def test_amqp_json_actor(json_parser_actor):

    assert json_parser_actor.name == "amqp_json_actor"


async def test_command(json_parser_actor, amqp_client):

    command_data = json.dumps({"command": "command1", "text": "Some value"})

    command = await amqp_client.send_command("amqp_json_actor", command_data)
    await command

    assert command.status.did_succeed
    assert command.replies[-1].message["text"] == "Some value"


async def test_bad_command_string(json_parser_actor, amqp_client):

    command = await amqp_client.send_command("amqp_json_actor", "bad_string")
    await command
    assert command.status.did_fail
    assert "Cannot deserialise command string" in command.replies[-1].message["error"]


async def test_no_command(json_parser_actor, amqp_client):

    command_data = json.dumps({"parameter1": 1})

    command = await amqp_client.send_command("amqp_json_actor", command_data)
    await command
    assert command.status.did_fail
    assert "does not contain a 'command'" in command.replies[-1].message["error"]


async def test_bad_callback(json_parser_actor, amqp_client):

    command_data = json.dumps({"command": "command3"})

    command = await amqp_client.send_command("amqp_json_actor", command_data)
    await command
    assert command.status.did_fail
    assert "Cannot find a callback for command" in command.replies[-1].message["error"]


async def test_callback_no_coro(json_parser_actor, amqp_client):

    command_data = json.dumps({"command": "command2"})

    command = await amqp_client.send_command("amqp_json_actor", command_data)
    await command
    assert command.status.did_fail
    assert "is not a coroutine function" in command.replies[-1].message["error"]
