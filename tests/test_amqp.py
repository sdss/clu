#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-26
# @Filename: test_actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from clu import AMQPActor, CluError

from .conftest import RMQ_PORT


pytestmark = [pytest.mark.asyncio]


def test_actor(amqp_actor):

    assert amqp_actor.name == 'amqp_actor'


async def test_client_send_command(amqp_client, amqp_actor):

    cmd = await amqp_client.send_command('amqp_actor', 'ping')
    await cmd

    assert len(amqp_client.replies) == 2
    assert amqp_client.replies[-1].message_code == ':'
    assert amqp_client.replies[-1].body['text'] == 'Pong.'


async def test_bad_command(amqp_client, amqp_actor):

    cmd = await amqp_client.send_command('amqp_actor', 'bad_command')
    await cmd

    assert "Command 'bad_command' failed." in amqp_client.replies[-1].body['text']


async def test_queue_locked(amqp_actor):

    with pytest.raises(CluError) as error:
        actor2 = AMQPActor(name='amqp_actor', port=RMQ_PORT)
        await actor2.start()

    assert 'This may indicate that another instance' in str(error)

    await actor2.stop()


async def test_model_callback(amqp_client, amqp_actor, mocker):

    callback = mocker.MagicMock()
    amqp_client.models['amqp_actor']['text'].register_callback(callback)

    kw = amqp_client.models['amqp_actor']['text']
    assert kw.value is None

    cmd = await amqp_client.send_command('amqp_actor', 'ping')
    await cmd
    await asyncio.sleep(0.01)

    callback.assert_called()

    assert kw.value == 'Pong.'
    assert kw.flatten() == {'text': 'Pong.'}

    assert amqp_client.models['amqp_actor'].flatten() == {'text': 'Pong.'}
    assert amqp_client.models['amqp_actor'].jsonify() == '{"text": "Pong."}'
