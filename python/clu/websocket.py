#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-05-25
# @Filename: websocket.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import json

from typing import TYPE_CHECKING

from websockets.legacy.protocol import broadcast
from websockets.server import serve

from clu.client import AMQPClient


if TYPE_CHECKING:
    from websockets.server import WebSocketServerProtocol

    from clu.client import AMQPReply


class WebsocketServer:
    """A websocket server that allows communication with the RabbitMQ exchange.

    The websocket server is a simple pass-through between a websocket client and
    an `.AMQPClient` that connects to the RabbitMQ exchange. Any `.AMQPReply`
    received by the AMQP client is packaged as a JSON and forwarded to the
    websocket clients. Websocket clients can send messages with the format ::

        {
            "consumer": ...,
            "command_string": ...,
            "command_id": ...
        }

    that will be sent to the corresponding actor commands queue. The websocket
    server does not track command completion, which is left to the user. Including
    a ``command_id`` with the message is recommended for the client to be able to
    track commands.

    Parameters
    ----------
    whost
        The host where to run the websocket server.
    wport
        The TCP port on which to run the websocket server.
    client_kwargs
        Arguments to pass to the `.AMQPClient` connection to RabbitMQ.

    """

    def __init__(self, whost: str = "0.0.0.0", wport: int = 9876, **client_kwargs):
        self.client = AMQPClient(**client_kwargs)

        self.wparams = (whost, wport)
        self.wclients: set[WebSocketServerProtocol] = set()

    async def start(self):
        """Start the server and AMQP client."""

        self.client.add_reply_callback(self._handle_reply)
        await self.client.start()

        self.websocket_server = await serve(
            self._handle_websocket,
            *self.wparams,
        )

        return self

    async def stop(self):
        """Stop the server and AMQP client."""

        await self.client.stop()
        self.websocket_server.close()

    async def _handle_websocket(self, websocket: WebSocketServerProtocol):
        """Handle a connection to the websocket server."""

        # Register the client
        self.wclients.add(websocket)

        async for data in websocket:
            try:
                message = json.loads(data)
                if not isinstance(message, dict):
                    continue
            except ValueError:
                continue

            if "consumer" not in message or "command_string" not in message:
                continue

            command_id = message.get("command_id", None)
            await self.client.send_command(
                message["consumer"],
                message["command_string"],
                command_id=command_id,
                await_command=False,
            )

        self.wclients.remove(websocket)

    async def _handle_reply(self, reply: AMQPReply):
        """Broadcast a reply to the connected websockets."""

        message = reply.message
        data = dict(
            headers=message.headers,
            exchange=message.exchange,
            message_id=message.message_id,
            routing_key=message.routing_key,
            timestamp=message.timestamp.isoformat() if message.timestamp else None,
            body=reply.body,
        )
        broadcast(self.wclients, json.dumps(data))
