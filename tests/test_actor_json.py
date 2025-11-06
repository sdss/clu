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

from clu.actor import TCPBaseActor
from clu.command import Command, CommandError


pytestmark = [pytest.mark.asyncio]


async def test_json_actor(json_actor, json_client):
    assert json_actor.name == "json_actor"
    assert json_actor.log is not None

    assert json_actor.server.is_serving()
    assert len(json_actor.transports) == 1


async def test_json_actor_command_write(json_actor, json_client):
    command = Command(
        command_string="ping",
        actor=json_actor,
    )

    command.set_status("RUNNING")
    command.write("i", text="Pong")

    assert len(command.replies) == 2
    assert command.replies[0].message_code.value == ">"


async def test_json_actor_pong(json_client, caplog):
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

    found = False
    for record in caplog.records:
        if "New command received: 'json_actor ping'" in record.message:
            found = True
            break
    assert found


async def test_json_actor_command_fails(json_client, mocker):
    mocker.patch("clu.actor.Command", side_effect=CommandError)
    actor_write = mocker.patch.object(TCPBaseActor, "_write_internal")

    json_client.writer.write(b"10 bad-command\n")
    await asyncio.sleep(0.01)

    actor_write.assert_called()

    error = actor_write.call_args[0][0].message["error"]
    assert "Could not parse the following as a command: " in error


async def test_json_actor_broadcast(json_actor, json_client):
    json_actor.write(message={"text": "hola"}, broadcast=True)

    data = await json_client.reader.readline()
    data_json = json.loads(data.decode())
    assert data_json["header"]["message_code"] == "i"
    assert data_json["header"]["sender"] == "json_actor"
    assert data_json["data"] == {"text": "hola"}


async def test_multiline_on(json_actor, json_client):
    json_client.writer.write(b"multiline\n")
    await asyncio.sleep(0.01)

    data = (await json_client.reader.read(1000)).splitlines()
    assert len(data) > 10


async def test_multiline_off(json_actor, json_client):
    json_client.writer.write(b"multiline\n")
    await asyncio.sleep(0.1)
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
        json_actor.model,
        "validate",
        return_value=(False, "failed updating model."),
    )

    json_actor.transports["mock_transport"] = mocker.MagicMock()
    mock_transport = json_actor.transports["mock_transport"]

    json_actor.write("i", {"text": "Some message"})

    b"Failed validating the reply" in mock_transport.write.call_args[0][0]


async def test_write_no_validate(json_actor, json_client, mocker):
    mock_func = mocker.patch.object(json_actor.model, "update_model")

    json_actor.write("i", {"text": "Some message"}, validate=False)

    mock_func.assert_not_called()


async def test_actor_no_schema(json_actor):
    assert json_actor.model is not None
    json_actor.load_schema(None)
    assert json_actor.model is not None


async def test_write_exception(json_actor):
    def _raise_exception():
        raise ValueError("Error message")

    command = Command(
        command_string="ping",
        actor=json_actor,
    )

    command.set_status("RUNNING")

    try:
        _raise_exception()
    except Exception as err:
        # NOTE: the frame we want is 1, not 2, but we use 2 to test that the
        # code can handle a missing frame and return the last one.
        command.write("e", error=err, traceback_frame=2)

    assert len(command.replies) == 2
    assert command.replies[1].message_code.value == "e"

    error_kwd = command.replies[1].message["error"]
    assert error_kwd["type"] == "ValueError"
    assert error_kwd["lineno"] is not None
    assert error_kwd["filename"] is not None

    # Now output the exception just as a string
    command.write("e", error=ValueError("A simple exception"), expand_exceptions=False)
    assert command.replies[-1].message["error"] == "A simple exception"


async def test_json_write_store(json_actor):
    json_actor.write("i", {"text": "hello!"})

    assert json_actor.store is not None

    last_issued = json_actor.store.tail("text")
    assert len(last_issued) == 1

    assert last_issued[0].value == "hello!"
    assert last_issued[0].message_code.value == "i"


@pytest.mark.parametrize("write_to_log", [True, False])
async def test_write_no_log(json_actor, write_to_log: bool, caplog):
    command = Command(
        command_string="ping",
        actor=json_actor,
    )

    command.set_status("RUNNING")
    command.info("Test", write_to_log=write_to_log)

    assert len(command.replies) == 2
    assert len(caplog.records) == 2 if write_to_log else 1
