#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-04
# @Filename: test_actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from clu.command import CommandStatus
from clu.exceptions import CluError, CluWarning
from clu.legacy import LegacyActor


pytestmark = [pytest.mark.asyncio]


async def test_actor(actor, actor_client):

    assert actor.version == "0.1.0"
    assert actor.host == "localhost"
    assert actor.tron is not None
    assert actor.log is not None
    assert actor.model is not None

    assert actor._server._server.is_serving()
    assert len(actor.transports) == 1


async def test_tron(actor):

    assert actor.models["alerts"]["version"].value[0] == "2.0.1"


async def test_actor_no_tron(unused_tcp_port_factory):

    actor = LegacyActor(
        "test_actor", "localhost", unused_tcp_port_factory(), version="0.1.0"
    )

    with pytest.warns(CluWarning):
        await actor.start()

    assert actor.tron is None

    await actor.stop()


async def test_actor_write(actor, actor_client):

    actor.write("i", text="Hi!", broadcast=True)

    assert (await actor_client.reader.readuntil()).strip().decode() == "0 0 i text=Hi!"

    # Check the file log
    file_log_data = open(actor.log.log_filename).read()

    assert "REPLY - 0 0 i text=Hi!" in file_log_data


async def test_new_command_client(actor, actor_client):

    actor_client.writer.write(b"2 ping\n")

    await asyncio.sleep(0.01)

    data = await actor_client.reader.read(100)

    assert data is not None

    lines = data.decode().splitlines()

    assert lines[0] == "1 2 > "
    assert lines[1] == "1 2 : text=Pong."


async def test_get_version(actor, actor_client):

    actor_client.writer.write(b"0 version\n")

    await asyncio.sleep(0.01)

    data = await actor_client.reader.read(100)

    assert data is not None

    lines = data.decode().splitlines()

    assert lines[0] == "1 0 > "
    assert lines[1] == "1 0 : version=0.1.0"


async def test_new_command(actor, actor_client):

    assert actor == actor_client.actor

    # This is the transport that correspond to actor_client. Note that
    # actor_client.writer.transport != actor.transports[1]. What we store
    # in actor.transports is the transport of the connection from the server
    # to the client, while actor_client.writer.transport belongs to the client.
    transport = actor.transports[1]

    command = actor.new_command(transport, b"0 ping\n")
    await command.wait_for_status(CommandStatus.DONE)

    await asyncio.sleep(0.01)  # Wait for last message to arrive

    data = await actor_client.reader.read(100)

    assert data is not None

    lines = data.decode().splitlines()

    assert lines[0] == "1 0 > "
    assert lines[1] == "1 0 : text=Pong."


async def test_bad_command(actor, actor_client):

    actor_client.writer.write("0X bad_command argument\n".encode())

    await asyncio.sleep(0.01)

    data = await actor_client.reader.read(100)

    assert data is not None

    lines = data.decode().splitlines()

    assert '1 0 f text="Could not parse the command string' in lines[0]


async def test_help_command(actor, actor_client):

    actor_client.writer.write(b"help\n")

    await asyncio.sleep(0.01)

    data = (await actor_client.reader.read(100)).decode()

    assert "Usage:" in data


async def test_ping_help_command(actor, actor_client):

    actor_client.writer.write(b"ping --help\n")

    await asyncio.sleep(0.01)

    data = (await actor_client.reader.read(200)).decode()

    assert "Pings the actor" in data
    assert "Usage:" in data


async def test_command_failed_to_parse(actor, actor_client):

    transport = actor.transports[1]
    command = actor.new_command(transport, b"0 badcommand\n")

    await asyncio.sleep(0.01)

    data = await actor_client.reader.read(200)

    assert command.status.did_fail

    assert b"UsageError" in data
    assert b"Command 'badcommand' failed" in data


async def test_write_update_model_fails(actor, actor_client, mocker):

    mocker.patch.object(
        actor.model, "update_model", return_value=(False, "failed updating model.")
    )

    actor.transports[1] = mocker.MagicMock()

    actor.write("i", {"text": "Some message"})

    actor.transports[1].write.assert_called_with(
        b'0 0 e error="Failed validating the reply: ' b'failed updating model."\n'
    )


async def test_write_no_validate(actor, actor_client, mocker):

    mock_func = mocker.patch.object(actor.model, "update_model")

    actor.write("i", {"text": "Some message"}, validate=False)

    mock_func.assert_not_called()


async def test_write_str(actor, actor_client, mocker):

    actor.transports[1].write = mocker.MagicMock()

    actor.write("i", "Some message")

    actor.transports[1].write.assert_called_with(b'0 0 i text="Some message"\n')


async def test_write_invalid(actor):

    with pytest.raises(TypeError):
        actor.write("i", 100)


async def test_write_concatenate_false(actor, actor_client, mocker):

    actor.transports[1].write = mocker.MagicMock()

    actor.write(
        "i",
        {"text": "Some message", "key": "value"},
        concatenate=False,
        no_validate=True,
    )

    actor.transports[1].write.assert_has_calls(
        [mocker.call(b'0 0 i text="Some message"\n'), mocker.call(b"0 0 i key=value\n")]
    )


async def test_send_command_no_tron(actor):

    actor.tron = None

    with pytest.raises(CluError):
        actor.send_command("actor2", "command")


async def test_write_dict(actor, actor_client):
    actor.write("i", message={"test1": {"subtest1": 1, "subtest2": 2}})
    data = await actor_client.reader.read(200)
    assert data == b"0 0 i test1=1,2\n"


async def test_write_dict_max_depth(actor, actor_client):
    with pytest.raises(TypeError):
        actor.write("i", message={"test1": {"subtest1": {"subtest2": 2}}})
