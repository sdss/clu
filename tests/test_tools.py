#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-04
# @Filename: test_tools.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from clu.tools import CallbackMixIn


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
