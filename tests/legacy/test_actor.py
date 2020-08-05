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
from clu.legacy import LegacyActor


pytestmark = pytest.mark.asyncio


async def test_actor(actor, actor_client):

    assert actor.version == '0.1.0'
    assert actor.host == 'localhost'
    assert actor.tron is not None
    assert actor.log is not None

    assert actor._server._server.is_serving()
    assert len(actor.transports) == 1


async def test_tron(actor):

    assert actor.models['alerts']['version'].value[0].native == '2.0.1'


async def test_actor_no_tron(unused_tcp_port_factory):

    actor = LegacyActor('test_actor', 'localhost',
                        unused_tcp_port_factory(),
                        version='0.1.0')

    await actor.start()

    assert actor.tron is None

    await actor.stop()


async def test_actor_write(actor, actor_client):

    actor.write('i', text='Hi!', broadcast=True)

    assert (await actor_client.reader.readuntil()).strip().decode() == '0 0 i text=Hi!'


async def test_new_command_client(actor, actor_client):

    actor_client.writer.write(b'0 ping\n')

    await asyncio.sleep(0.01)

    data = await actor_client.reader.read(100)

    assert data is not None

    lines = data.decode().splitlines()

    assert lines[0] == '1 0 i '
    assert lines[1] == '1 0 : text=Pong.'


async def test_new_command(actor, actor_client):

    assert actor == actor_client.actor

    # This is the transport that correspond to actor_client. Note that
    # actor_client.writer.transport != actor.transports[1]. What we store
    # in actor.transports is the transport of the connection from the server
    # to the client, while actor_client.writer.transport belongs to the client.
    transport = actor.transports[1]

    command = actor.new_command(transport, b'0 ping\n')
    await command.wait_for_status(CommandStatus.DONE)

    await asyncio.sleep(0.01)  # Wait for last message to arrive

    data = await actor_client.reader.read(100)

    assert data is not None

    lines = data.decode().splitlines()

    assert lines[0] == '1 0 i '
    assert lines[1] == '1 0 : text=Pong.'


async def test_bad_command(actor, actor_client):

    actor_client.writer.write('0X bad_command argument\n'.encode())

    await asyncio.sleep(0.01)

    data = await actor_client.reader.read(100)

    assert data is not None

    lines = data.decode().splitlines()

    assert '1 0 f text="Could not parse the command string' in lines[0]


async def test_help_command(actor, actor_client):

    actor_client.writer.write(b'help\n')

    await asyncio.sleep(0.01)

    data = (await actor_client.reader.read(100)).decode()

    assert 'Usage:' in data


async def test_ping_help_command(actor, actor_client):

    actor_client.writer.write(b'ping --help\n')

    await asyncio.sleep(0.01)

    data = (await actor_client.reader.read(200)).decode()

    assert 'Pings the actor' in data
    assert 'Usage:' in data


async def test_command_failed_to_parse(actor, actor_client):

    transport = actor.transports[1]
    command = actor.new_command(transport, b'0 badcommand\n')

    await asyncio.sleep(0.01)

    data = await actor_client.reader.read(200)

    assert command.status.did_fail

    assert b'UsageError' in data
    assert b'Command \'badcommand\' failed' in data


async def test_send_command(actor, tron_server):

    actor.send_command('alerts', 'ping')

    await asyncio.sleep(0.01)

    assert b'test_actor.test_actor' in tron_server.received[-1]
    assert b'alerts ping' in tron_server.received[-1]
