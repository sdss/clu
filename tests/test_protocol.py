#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-09-11
# @Filename: test_protocol.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from clu.protocol import (TCPStreamClient, TCPStreamPeriodicServer,
                          TCPStreamServer, TopicListener, open_connection)

from .conftest import RMQ_PORT


pytestmark = [pytest.mark.asyncio]


@pytest.fixture
async def tcp_server(event_loop, unused_tcp_port_factory):

    tcp = TCPStreamServer('localhost', unused_tcp_port_factory(),
                          max_connections=1)
    await tcp.start()
    event_loop.call_soon(tcp.serve_forever)

    yield tcp

    tcp.stop()


async def test_max_connections(tcp_server):

    client1 = await open_connection('localhost', tcp_server.port)  # noqa
    client2 = await open_connection('localhost', tcp_server.port)

    received = await client2.reader.readline()

    assert received == b'Max number of connections reached.\n'


async def test_close_client_fails(tcp_server):

    # Uninitialised client
    client = TCPStreamClient('localhost', tcp_server.port)

    with pytest.raises(RuntimeError):
        client.close()


async def test_periodic_server(unused_tcp_port_factory, mocker):

    callback = mocker.MagicMock()

    periodic_server = TCPStreamPeriodicServer('localhost',
                                              unused_tcp_port_factory(),
                                              sleep_time=0.01)
    await periodic_server.start()

    await open_connection('localhost', periodic_server.port)

    periodic_server.periodic_callback = callback

    await asyncio.sleep(0.02)

    callback.assert_called()

    periodic_server.stop()


async def test_topic_listener_url(amqp_actor):

    url = f'amqp://guest:guest@localhost:{RMQ_PORT}'
    exchange = 'test'

    listener = TopicListener(url)
    await listener.connect(exchange)

    assert listener.connection.connected.is_set()

    await listener.stop()
