#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-04
# @Filename: test_tools.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import json
import logging
import warnings

import pytest

from clu import ActorHandler, CluWarning
from clu.tools import CallbackMixIn, CommandStatus, StatusMixIn, format_value


@pytest.fixture
def callback_object():

    class TestClass(CallbackMixIn):
        pass

    yield TestClass()


@pytest.mark.asyncio
async def test_callback_mixin(callback_object):

    results = []

    def callback_func(value):
        results.append(value)

    assert isinstance(callback_object, CallbackMixIn)

    callback_object.register_callback(callback_func)
    assert callback_func in callback_object._callbacks

    callback_object.notify(42)

    # Await to give the event loop time to get to the callback.
    await asyncio.sleep(0.01)

    assert results == [42]

    callback_object.remove_callback(callback_func)
    assert callback_func not in callback_object._callbacks


@pytest.mark.asyncio
async def test_callback_coro(callback_object):

    results = []

    async def callback_func(value):
        results.append(value)

    callback_object.register_callback(callback_func)
    assert callback_func in callback_object._callbacks

    callback_object.notify(42)

    await asyncio.sleep(0.01)

    assert results == [42]
    assert len(callback_object._running) == 0


@pytest.mark.asyncio
async def test_callback_stop(callback_object):

    results = []

    async def callback_func(value):
        await asyncio.sleep(10)
        results.append(value)

    callback_object.register_callback(callback_func)
    callback_object.notify(42)

    await asyncio.sleep(0.01)
    await callback_object.stop_callbacks()

    assert results == []
    assert len(callback_object._running) == 0


def test_callback_none(callback_object):

    results = []

    def callback_func(value):
        results.append(value)

    callback_object._callbacks = None
    callback_object.notify(42)

    assert results == []


@pytest.mark.parametrize('level', (logging.DEBUG, logging.INFO,
                                   logging.WARNING, logging.ERROR))
@pytest.mark.asyncio
async def test_actorhandler(json_client, json_actor, level):

    json_actor.log.addHandler(ActorHandler(json_actor, level=logging.DEBUG))

    json_actor.log.log(level, 'This is a log message.')

    msg_code = {logging.DEBUG: 'd', logging.INFO: 'i',
                logging.WARNING: 'w', logging.ERROR: 'f'}

    data = await json_client.reader.readline()
    data_json = json.loads(data.decode())
    assert data_json['header']['message_code'] == msg_code[level]
    assert data_json['header']['sender'] == 'json_actor'
    assert data_json['data'] == {'text': 'This is a log message.'}


@pytest.mark.asyncio
async def test_actorhandler_warning(json_client, json_actor):

    handler = ActorHandler(json_actor, level=logging.WARNING,
                           filter_warnings=[CluWarning])
    json_actor.log.addHandler(handler)
    json_actor.log.warnings_logger.addHandler(handler)

    with pytest.raises(asyncio.TimeoutError):
        warnings.warn('A deprecation warning', DeprecationWarning)
        data = await asyncio.wait_for(json_client.reader.read(100), timeout=0.01)

    warnings.warn('A CLU warning', CluWarning)

    data = await asyncio.wait_for(json_client.reader.readline(), timeout=0.01)
    data_json = json.loads(data.decode())
    assert data_json['header']['message_code'] == 'w'
    assert data_json['header']['sender'] == 'json_actor'
    assert data_json['data'] == {'text': 'A CLU warning (CluWarning)'}


@pytest.mark.parametrize('value,formatted', [(True, 'T'), (False, 'F'),
                                             ('string', 'string'),
                                             ('"string"', '"string"'),
                                             ('A string', '"A string"'),
                                             ('\'A string\'', '\'A string\''),
                                             ('"A string"', '"A string"'),
                                             (5, '5'),
                                             ([1, 2, 'A string', False],
                                              '1,2,"A string",F')])
def test_format_value(value, formatted):

    assert format_value(value) == formatted


@pytest.mark.asyncio
class TestStatusMixIn:

    async def test_callback_call_now(self, mocker):

        callback = mocker.MagicMock()

        StatusMixIn(CommandStatus, CommandStatus.READY,
                    callback_func=callback, call_now=True)

        await asyncio.sleep(0.01)

        callback.assert_called_once()

    async def test_callback(self, mocker):

        callback = mocker.MagicMock()

        s = StatusMixIn(CommandStatus, CommandStatus.READY,
                        callback_func=callback)

        s.status = CommandStatus.RUNNING

        await asyncio.sleep(0.01)

        callback.assert_called_once()

    async def test_callback_list(self, mocker):

        callback = [mocker.MagicMock(), mocker.MagicMock()]

        s = StatusMixIn(CommandStatus, CommandStatus.READY,
                        callback_func=callback)

        s.status = CommandStatus.RUNNING

        await asyncio.sleep(0.01)

        callback[0].assert_called_once()
        callback[1].assert_called_once()

    async def test_callback_tuple(self, mocker):

        callback = (mocker.MagicMock(), mocker.MagicMock())

        s = StatusMixIn(CommandStatus, CommandStatus.READY,
                        callback_func=callback)

        s.status = CommandStatus.READY  # This should not trigger callbacks
        s.status = CommandStatus.RUNNING

        await asyncio.sleep(0.01)

        callback[0].assert_called_once()
        callback[1].assert_called_once()

    async def test_no_callback(self, mocker):

        s = StatusMixIn(CommandStatus, CommandStatus.READY)

        s.status = CommandStatus.READY
        assert s.status == CommandStatus.READY

        s.status = CommandStatus.RUNNING
        assert s.status == CommandStatus.RUNNING

    async def test_wait_for_status(self, event_loop):

        def set_status(mixin, status):
            mixin.status = status

        s = StatusMixIn(CommandStatus, CommandStatus.READY)

        event_loop.call_later(0.01, set_status, s, CommandStatus.DONE)

        await s.wait_for_status(CommandStatus.DONE)

        assert s.status == CommandStatus.DONE
        assert s.watcher is None

    async def test_wait_for_status_same(self):

        s = StatusMixIn(CommandStatus, CommandStatus.READY)

        await s.wait_for_status(CommandStatus.READY)

        assert s.status == CommandStatus.READY
        assert s.watcher is None
