#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-26
# @Filename: test_actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import logging
from unittest.mock import AsyncMock

import aio_pika
import pytest

from clu import REPLY, AMQPActor, CluError, CommandError
from clu.client import AMQPReply
from clu.command import Command
from clu.model import Model
from clu.tools import CommandStatus


pytestmark = [pytest.mark.asyncio]


@pytest.fixture
def message_maker(mocker):
    def _make_message(headers=None, body=None):
        headers = headers or {"command_id": 1, "message_code": "i", "sender": "me"}

        message = mocker.MagicMock(spec=aio_pika.IncomingMessage)
        message.correlation_id = headers["command_id"]
        message.info.return_value = {"headers": headers}
        message.body = b"{}"

        return message

    yield _make_message


async def test_actor(amqp_actor):
    assert amqp_actor.name == "amqp_actor"


async def test_client_send_command(amqp_client, amqp_actor, caplog):
    cmd = await amqp_client.send_command("amqp_actor", "ping")
    await cmd

    assert len(cmd.replies) == 2
    assert cmd.replies[-1].message_code == ":"
    assert cmd.replies[-1].message["text"] == "Pong."

    assert "New command received: 'amqp_actor ping'" in caplog.record_tuples[0][2]


async def test_client_send_command_args(amqp_client, amqp_actor):
    cmd = await amqp_client.send_command("amqp_actor", "ping", "--help")
    await cmd

    assert len(cmd.replies) == 2
    assert cmd.replies[-1].message_code == ":"
    assert "help" in cmd.replies[-1].message


async def test_get_version(amqp_client, amqp_actor):
    cmd = await amqp_client.send_command("amqp_actor", "version")
    await cmd

    assert len(cmd.replies) == 2
    assert cmd.replies[-1].message_code == ":"
    assert cmd.replies[-1].message["version"] == "?"


async def test_bad_command(amqp_client, amqp_actor):
    cmd = await amqp_client.send_command("amqp_actor", "bad_command")
    await cmd

    assert (
        "Command 'bad_command' does not exist or cannot be parsed."
        in cmd.replies[-1].message["error"]
    )


async def test_send_command_actor_not_connected(amqp_client, amqp_actor):
    cmd = await amqp_client.send_command("amqp_actor_2", "ping")
    await cmd

    assert cmd.status.did_fail
    assert "Failed routing message" in cmd.replies[-1].message["error"]


async def test_queue_locked(amqp_actor):
    with pytest.raises(CluError) as error:
        actor2 = AMQPActor(name="amqp_actor", port=amqp_actor.connection.port)
        await actor2.start()

    assert "This may indicate that another instance" in str(error)

    await actor2.stop()


async def test_model_callback(amqp_client, amqp_actor, mocker):
    def callback(model, kw):
        pass

    callback_mock = mocker.create_autospec(callback)
    amqp_client.models["amqp_actor"].register_callback(callback_mock)

    kw = amqp_client.models["amqp_actor"]["text"]
    assert kw.value is None

    cmd = await amqp_client.send_command("amqp_actor", "ping")
    await cmd

    # The callback is on a task so it may take a bit to be called.
    await asyncio.sleep(0.01)

    callback_mock.assert_called()
    assert len(callback_mock.call_args) == 2

    assert kw.value == "Pong."
    assert kw.flatten() == {"text": "Pong."}

    assert amqp_client.models["amqp_actor"].flatten() == {
        "text": "Pong.",
        "error": None,
        "schema": None,
        "fwhm": None,
        "info": None,
        "test1": None,
        "help": None,
        "version": None,
        "UserInfo": None,
        "yourUserID": None,
        "num_users": None,
        "command_model": None,
    }

    json = (
        '{"fwhm": null, "text": "Pong.", "info": null, "test1": null, "schema": null, '
        '"version": null, "help": null, "error": null, '
        '"yourUserID": null, "UserInfo": null, "num_users": null, '
        '"command_model": null}'
    )
    assert amqp_client.models["amqp_actor"].jsonify() == json


async def test_client_get_schema_fails(amqp_actor, amqp_client, caplog):
    # Remove actor knowledge of its own model
    amqp_actor.model = None

    # Restart models.
    del amqp_client.models[amqp_actor.name]
    await amqp_client.models.load_schemas()

    assert amqp_client.models == {}

    log_msg = caplog.record_tuples[-1]
    assert "Cannot load model" in log_msg[2]


async def test_write_log(amqp_actor, caplog):
    with caplog.at_level(REPLY, logger=f"clu:{amqp_actor.name}"):
        amqp_actor.write("i", {"text": "A test"}, internal=True)

    await asyncio.sleep(0.01)

    message = caplog.record_tuples[-1][2]
    assert "A test" in message
    assert '"message_code": "i"' in message


async def test_bad_keyword(amqp_actor, caplog):
    schema = """{
    "type": "object",
    "properties": {
        "text": {"type": "string"}
    },
    "additionalProperties": false
}"""

    # Replace actor schema
    amqp_actor.model = Model(amqp_actor.name, schema)

    with caplog.at_level(REPLY, logger=f"clu:{amqp_actor.name}"):
        amqp_actor.write("i", {"bad_keyword": "blah"}, broadcast=True)

    await asyncio.sleep(0.01)

    assert "Failed validating the reply" in caplog.record_tuples[-1][2]


async def test_write_update_model_fails(amqp_actor, mocker):
    mocker.patch.object(
        amqp_actor.model,
        "validate",
        return_value=(False, "failed updating model."),
    )
    mocker.patch.object(
        amqp_actor.connection.exchange,
        "publish",
        new_callable=AsyncMock,
    )
    apika_message = mocker.patch("aio_pika.Message")

    amqp_actor.write("i", {"text": "Some message"})

    await asyncio.sleep(0.01)
    assert b"failed updating model" in apika_message.call_args[0][0]


async def test_write_no_validate(amqp_actor, mocker):
    mock_func = mocker.patch.object(amqp_actor.model, "update_model")

    amqp_actor.write("i", {"text": "Some message"}, validate=False)

    mock_func.assert_not_called()


async def test_write_silent(amqp_actor, mocker):
    mock_func = mocker.patch.object(amqp_actor, "_write_internal")

    amqp_actor.write("i", {"text": "Some message"}, silent=True)

    mock_func.assert_not_called()


async def test_new_command_fails(amqp_actor, mocker):
    message = AsyncMock(spec=aio_pika.IncomingMessage)
    message.info = lambda: {"headers": {}}
    message.body = b'{"command_string": "bad-command"}'

    mocker.patch("clu.actor.Command", side_effect=CommandError)

    actor_write = mocker.patch.object(
        amqp_actor,
        "_write_internal",
        new_callable=AsyncMock,
    )

    await amqp_actor.new_command(message)

    actor_write.assert_called()

    expected_error = (
        "Could not parse the following as a command: "
        "'amqp_actor bad-command': There has been an error"
    )
    assert actor_write.call_args[0][0].message["error"] == expected_error


class TestHandleReply:
    @pytest.mark.xfail()
    async def test_client_handle_reply_bad_message(
        self, amqp_client, message_maker, caplog
    ):
        message = message_maker()
        message.correlation_id = 100

        await amqp_client.handle_reply(message)

        assert "mismatch between message" in caplog.record_tuples[-2][2]
        assert caplog.record_tuples[-1][2] == "Invalid message received."

    @pytest.mark.parametrize("log", [False, logging.getLogger()])
    async def test_reply_no_message_code(self, message_maker, log, caplog):
        message = message_maker(headers={"command_id": 1, "sender": "me"})
        reply = AMQPReply(message, log=log)

        assert reply.is_valid is False
        if log:
            assert "message without message_code" in caplog.record_tuples[-1][2]

    @pytest.mark.parametrize("log", [False, logging.getLogger()])
    async def test_reply_no_sender(self, message_maker, log, caplog):
        message = message_maker(headers={"command_id": 1, "message_code": "i"})
        reply = AMQPReply(message, log=log)

        assert reply.is_valid is True
        if log:
            assert "message without sender" in caplog.record_tuples[-1][2]


async def test_client_send_command_callback(amqp_client, amqp_actor, mocker):
    callback_mock = mocker.MagicMock()

    cmd = await amqp_client.send_command("amqp_actor", "ping", callback=callback_mock)
    await cmd

    callback_mock.assert_called()
    assert isinstance(callback_mock.mock_calls[0].args[0], AMQPReply)


async def test_write_exception(amqp_actor):
    command = Command(
        command_string="ping",
        actor=amqp_actor,
    )

    command.set_status("RUNNING")
    command.write("e", error=ValueError("Error message"))

    assert len(command.replies) == 2
    assert command.replies[1].message_code == "e"
    assert command.replies.get("error") == {
        "module": "builtins",
        "type": "ValueError",
        "message": "Error message",
        "filename": None,
        "lineno": None,
    }


async def test_send_command_from_command(amqp_actor, mocker):
    send_command_mock = mocker.patch.object(amqp_actor.connection.exchange, "publish")

    command = Command(
        command_string="",
        commander_id="APO.Jose",
        command_id=5,
        actor=amqp_actor,
    )
    await command.send_command("otheractor", "command1 --option", await_command=False)

    send_command_mock.assert_called()


async def test_child_command(amqp_actor, mocker):
    send_command_mock = mocker.patch.object(amqp_actor.connection.exchange, "publish")

    command = Command(
        command_string="",
        commander_id="APO.Jose",
        command_id=5,
        actor=amqp_actor,
    )
    await command.child_command("help")

    send_command_mock.assert_called()


async def test_send_command_time_limit(amqp_actor):
    @amqp_actor.parser.command()
    async def timeout_command(command):
        await asyncio.sleep(1)

    cmd = await amqp_actor.send_command("amqp_actor", "timeout-command", time_limit=0.1)

    await asyncio.sleep(0.2)

    assert cmd.status == CommandStatus.TIMEDOUT


async def test_model_patternProperties(amqp_client, amqp_actor):
    amqp_actor.model = Model(
        "amqp_actor",
        {
            "type": "object",
            "properties": {},
            "patternProperties": {
                "prop[0-9]": {"type": "integer"},
                "additionalProperties": False,
            },
        },
    )

    amqp_actor.write("i", {"prop1": 5})

    await asyncio.sleep(0.01)
    assert "prop1" in amqp_client.models["amqp_actor"]
    assert amqp_client.models["amqp_actor"]["prop1"].value == 5
    assert amqp_client.models["amqp_actor"]["prop1"].in_schema is False


async def test_internal_command(amqp_client, amqp_actor):
    cmd = await amqp_client.send_command("amqp_actor", "ping", internal=True)
    await cmd

    assert len(cmd.replies) == 2

    for reply in cmd.replies:
        assert reply.internal


async def test_get_command_model(amqp_client, amqp_actor):
    cmd = await amqp_client.send_command("amqp_actor", "get-command-model help")
    await cmd

    assert len(cmd.replies) == 2


async def test_reply_callback(amqp_client, amqp_actor, mocker):
    async def callback(reply):
        pass

    callback_mock = mocker.create_autospec(callback)
    amqp_client.add_reply_callback(callback_mock)

    assert len(amqp_client._callbacks) == 1

    # Just send a command that emits some replies.
    cmd = await amqp_client.send_command("amqp_actor", "help")
    await cmd
    await asyncio.sleep(0.01)

    callback_mock.assert_called()

    amqp_client.remove_reply_callback(callback_mock)
    assert len(amqp_client._callbacks) == 0


async def test_task_handler(amqp_actor, amqp_client, mocker):
    task_handler = mocker.AsyncMock()

    amqp_actor.add_task_handler("my-task", task_handler)

    await amqp_client.send_task("amqp_actor", "my-task", {"value": 1})

    await asyncio.sleep(0.1)

    task_handler.assert_called()
    task_handler.assert_called_with({"value": 1, "__actor__": amqp_actor})


async def test_unknown_task(amqp_actor, amqp_client, mocker):
    actor_write = mocker.patch.object(
        amqp_actor,
        "_write_internal",
        new_callable=AsyncMock,
    )

    await amqp_client.send_task("amqp_actor", "invalid-task")

    await asyncio.sleep(0.1)

    actor_write.assert_called()
    assert "Unknown task" in actor_write.call_args[0][0].message["error"]


async def test_amqp_context(amqp_client):
    await amqp_client.stop()

    assert amqp_client.is_connected() is False

    async with amqp_client:
        assert amqp_client.is_connected() is True


async def test_amqp_context_reconnect(amqp_client, mocker):
    amqp_client.start = mocker.MagicMock()

    async with amqp_client:
        assert amqp_client.is_connected() is True

    amqp_client.start.assert_not_called()


async def test_amqp_context_fails(amqp_client, mocker):
    await amqp_client.stop()

    amqp_client.start = mocker.MagicMock(side_effect=ValueError)

    async with amqp_client:
        assert amqp_client.is_connected() is False
