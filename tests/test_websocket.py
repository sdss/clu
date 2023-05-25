#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-05-25
# @Filename: test_websocket.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import json

import pytest
import websockets.client

from clu.websocket import WebsocketServer


@pytest.fixture()
async def websocket_server(amqp_actor):
    ws = WebsocketServer(wport=19876, port=amqp_actor.connection.port)
    await ws.start()

    yield ws

    await ws.stop()


async def test_websocket_client(websocket_server, amqp_client):
    """Test receive message in a websocket client."""

    async with websockets.client.connect("ws://localhost:19876") as websocket:
        # Send a message to the actor to trigger a reply.
        await amqp_client.send_command("amqp_actor", "ping")
        await asyncio.sleep(0.1)

        # Skip first message
        await websocket.recv()

        message = await websocket.recv()

        assert message is not None
        assert isinstance(message, str)

        js = json.loads(message)
        assert "headers" in js
        assert "body" in js
        assert js["body"] == {"text": "Pong."}


async def test_websocket_client_send_command(websocket_server):
    """Test send command from websocket client."""

    async with websockets.client.connect("ws://localhost:19876") as websocket:
        # Send a message to the actor from the ws client.
        await websocket.send(
            json.dumps(
                {
                    "consumer": "amqp_actor",
                    "command_string": "ping",
                    "command_id": "id-1234",
                }
            )
        )
        await asyncio.sleep(0.1)

        # Skip first message
        await websocket.recv()

        message = await websocket.recv()

        assert message is not None
        assert isinstance(message, str)

        js = json.loads(message)
        assert "headers" in js
        assert "body" in js
        assert js["body"] == {"text": "Pong."}
        assert js["headers"]["command_id"] == "id-1234"


async def test_websocket_client_send_bad_command1(websocket_server):
    """Test sending an invalid command to the websocket server."""

    async with websockets.client.connect("ws://localhost:19876") as websocket:
        await websocket.send("hello")
        await asyncio.sleep(0.1)

        # Check we don't receive new replies because the message didn't
        # trigger a new command.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(websocket.recv(), 0.5)


async def test_websocket_client_send_bad_command2(websocket_server):
    """Test sending an invalid command to the websocket server."""

    async with websockets.client.connect("ws://localhost:19876") as websocket:
        await websocket.send(json.dumps({"command_string": "ping"}))
        await asyncio.sleep(0.1)

        # Check we don't receive new replies because the message didn't
        # trigger a new command.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(websocket.recv(), 0.5)
