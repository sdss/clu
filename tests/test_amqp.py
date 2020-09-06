#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-26
# @Filename: test_actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import sys
import unittest.mock

import pytest

from clu import REPLY, AMQPActor, CluError, CommandError
from clu.model import Model

from .conftest import RMQ_PORT


if sys.version_info.major == 3 and sys.version_info.minor >= 8:
    CoroutineMock = unittest.mock.AsyncMock
else:
    from asynctest import CoroutineMock


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


async def test_write_update_model_fails(amqp_actor, mocker):

    mocker.patch.object(amqp_actor.schema, 'update_model',
                        return_value=(False, 'failed updating model.'))
    mocker.patch.object(amqp_actor.connection.exchange, 'publish',
                        new_callable=CoroutineMock)
    apika_message = mocker.patch('aio_pika.Message', new_callable=CoroutineMock)

    await amqp_actor.write('i', {'text': 'Some message'})

    assert b'failed updating model' in apika_message.call_args.args[0]


async def test_write_no_validate(amqp_actor, mocker):

    mock_func = mocker.patch.object(amqp_actor.schema, 'update_model')

    await amqp_actor.write('i', {'text': 'Some message'}, no_validate=True)

    mock_func.assert_not_called()


@pytest.mark.xfailif(sys.version_info < (3, 8), reason='Python < 3.8')
async def test_new_command_fails(amqp_actor, mocker):

    message = mocker.MagicMock()
    mocker.patch('clu.actor.Command', side_effect=CommandError)
    mocker.patch('json.loads')

    actor_write = mocker.patch.object(amqp_actor, 'write',
                                      new_callable=CoroutineMock)

    await amqp_actor.new_command(message)

    actor_write.assert_awaited()
    assert 'Could not parse the following' in actor_write.call_args.args[1]['error']
