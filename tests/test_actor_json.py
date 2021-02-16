#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-27
# @Filename: test_actor_json.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import json

import pytest


pytestmark = [pytest.mark.asyncio]


async def test_json_actor(json_actor, json_client):

    assert json_actor.name == "json_actor"
    assert json_actor.log is not None

    assert json_actor.server.is_serving()
    assert len(json_actor.transports) == 1


async def test_json_actor_pong(json_client):

    json_client.writer.write(b"0 ping\n")

    data = await json_client.reader.readline()
    data_json = json.loads(data.decode())
    assert data_json["header"]["message_code"] == ">"
    assert data_json["header"]["sender"] == "json_actor"
    assert data_json["data"] == {}

    data = await json_client.reader.readline()
    data_json = json.loads(data.decode())
    assert data_json["header"]["message_code"] == ":"
    assert data_json["data"] == {"text": "Pong."}


async def test_json_actor_broadcast(json_actor, json_client):

    json_actor.write(message={"my_key": "hola"}, broadcast=True)

    data = await json_client.reader.readline()
    data_json = json.loads(data.decode())
    assert data_json["header"]["message_code"] == "i"
    assert data_json["header"]["sender"] == "json_actor"
    assert data_json["data"] == {"my_key": "hola"}


async def test_multiline_on(json_actor, json_client):

    json_client.writer.write(b"multiline\n")
    await asyncio.sleep(0.01)

    data = (await json_client.reader.read(1000)).splitlines()
    assert len(data) > 10


async def test_multiline_off(json_actor, json_client):

    json_client.writer.write(b"multiline\n")
    json_client.writer.write(b"multiline --off\n")
    await asyncio.sleep(0.01)

    data = (await json_client.reader.read(100000)).splitlines()
    data_json = json.loads(data[-1].decode())
    assert data_json["header"]["message_code"] == ":"
    assert data_json["header"]["sender"] == "json_actor"
    assert data_json["data"] == {"text": "Multiline mode is off"}


async def test_json_actor_send_command(json_actor):

    with pytest.raises(NotImplementedError) as error:
        json_actor.send_command("a_command")

    assert "JSONActor cannot send commands to other actors." in str(error)


async def test_timed_command(json_actor, json_client):

    json_actor.timed_commands.add_command("ping", delay=0.5)

    await asyncio.sleep(1.6)

    data = (await json_client.reader.read(10000)).splitlines()

    assert len(data) == 4  # Two commands, each with a running and a done msg

    data_json = json.loads(data[1])
    assert data_json["header"]["message_code"] == ":"
    assert data_json["data"] == {"text": "Pong."}

    data_json = json.loads(data[3])
    assert data_json["header"]["message_code"] == ":"
    assert data_json["data"] == {"text": "Pong."}


async def test_write_update_model_fails(json_actor, json_client, mocker):

    mocker.patch.object(
        json_actor.model, "update_model", return_value=(False, "failed updating model.")
    )

    json_actor.transports["mock_transport"] = mocker.MagicMock()
    mock_transport = json_actor.transports["mock_transport"]

    json_actor.write("i", {"text": "Some message"})

    b"Failed validating the reply" in mock_transport.write.call_args[0][0]


async def test_write_no_validate(json_actor, json_client, mocker):

    mock_func = mocker.patch.object(json_actor.model, "update_model")

    json_actor.write("i", {"text": "Some message"}, validate=False)

    mock_func.assert_not_called()
