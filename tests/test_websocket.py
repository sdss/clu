#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-05-25
# @Filename: test_websocket.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

import pytest
import websockets.client

from clu.websocket import WebsocketServer


@pytest.fixture()
async def websocket_server(amqp_actor):
    ws = WebsocketServer(wport=19876, port=amqp_actor.port)
    await ws.start()

    yield ws

    await ws.stop()


async def test_websocket_client(websocket_server, amqp_client):
    """Test receive message in a websocket client."""

    async with websockets.client.connect("ws://localhost:19876") as websocket:
        # Send a message to the actor to trigger a reply.
        await amqp_client.send_command("amqp_actor", "ping")
        await asyncio.sleep(0.1)

        message = websocket.recv()
        assert message is not None
        assert isinstance(message, dict)
