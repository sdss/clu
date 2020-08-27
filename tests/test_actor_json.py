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

    assert json_actor.name == 'json_actor'
    assert json_actor.log is not None

    assert json_actor.server.is_serving()
    assert len(json_actor.transports) == 1


async def test_json_actor_pong(json_client):

    json_client.writer.write(b'0 ping\n')

    data = await json_client.reader.readline()
    data_json = json.loads(data.decode())
    assert data_json['header']['message_code'] == 'i'
    assert data_json['header']['sender'] == 'json_actor'
    assert data_json['data'] == {}

    data = await json_client.reader.readline()
    data_json = json.loads(data.decode())
    assert data_json['header']['message_code'] == ':'
    assert data_json['data'] == {'text': 'Pong.'}


async def test_json_actor_broadcast(json_actor, json_client):

    json_actor.write(message={'my_key': 'hola'}, broadcast=True)

    data = await json_client.reader.readline()
    data_json = json.loads(data.decode())
    assert data_json['header']['message_code'] == 'i'
    assert data_json['header']['sender'] == 'json_actor'
    assert data_json['data'] == {'my_key': 'hola'}


async def test_json_actor_send_command(json_actor):

    with pytest.raises(NotImplementedError) as error:
        json_actor.send_command('a_command')

    assert 'JSONActor cannot send commands to other actors.' in str(error)


async def test_timed_command(json_actor, json_client):

    json_actor.timed_commands.add_command('ping', delay=0.5)

    await asyncio.sleep(1.6)

    data = (await json_client.reader.read(10000)).splitlines()

    assert len(data) == 4  # Two commands, each with a running and a done msg

    data_json = json.loads(data[1])
    assert data_json['header']['message_code'] == ':'
    assert data_json['data'] == {'text': 'Pong.'}

    data_json = json.loads(data[3])
    assert data_json['header']['message_code'] == ':'
    assert data_json['data'] == {'text': 'Pong.'}
