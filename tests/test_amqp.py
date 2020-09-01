#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-26
# @Filename: test_actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import pytest

from clu import REPLY, AMQPActor, CluError
from clu.model import Model

from .conftest import RMQ_PORT


pytestmark = [pytest.mark.asyncio]


def test_actor(amqp_actor):

    assert amqp_actor.name == 'amqp_actor'


async def test_client_send_command(amqp_client, amqp_actor):

    cmd = await amqp_client.send_command('amqp_actor', 'ping')
    await cmd

    assert len(cmd.replies) == 2
    assert cmd.replies[-1].message_code == ':'
    assert cmd.replies[-1].body['text'] == 'Pong.'


async def test_get_version(amqp_client, amqp_actor):

    cmd = await amqp_client.send_command('amqp_actor', 'version')
    await cmd

    assert len(cmd.replies) == 2
    assert cmd.replies[-1].message_code == ':'
    assert cmd.replies[-1].body['version'] == '?'


async def test_bad_command(amqp_client, amqp_actor):

    cmd = await amqp_client.send_command('amqp_actor', 'bad_command')
    await cmd

    assert "Command 'bad_command' failed." in cmd.replies[-1].body['text']


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

    callback.assert_called()

    assert kw.value == 'Pong.'
    assert kw.flatten() == {'text': 'Pong.'}

    assert amqp_client.models['amqp_actor'].flatten() == {'text': 'Pong.',
                                                          'error': None,
                                                          'schema': None,
                                                          'fwhm': None,
                                                          'help': None,
                                                          'version': None}

    json = ('{"fwhm": null, "text": "Pong.", "error": null, '
            '"schema": null, "version": null, "help": null}')
    assert amqp_client.models['amqp_actor'].jsonify() == json


async def test_client_get_schema_fails(amqp_actor, amqp_client, caplog):

    # Remove actor knowledge of its own schema
    amqp_actor.schema = None

    # Restart models.
    del amqp_client.models[amqp_actor.name]
    await amqp_client.models.load_schemas()

    assert amqp_client.models == {}

    log_msg = caplog.record_tuples[-1]
    assert 'Cannot load model' in log_msg[2]


async def test_bad_keyword(amqp_actor, caplog):

    schema = """{
    "type": "object",
    "properties": {
        "text": {"type": "string"}
    },
    "additionalProperties": false
}"""

    # Replace actor schema
    amqp_actor.schema = Model(amqp_actor.name, schema)

    with caplog.at_level(REPLY, logger=f'clu:{amqp_actor.name}'):
        await amqp_actor.write('i', {'bad_keyword': 'blah'}, broadcast=True)

    assert 'Failed validating the reply' in caplog.record_tuples[-1][2]
