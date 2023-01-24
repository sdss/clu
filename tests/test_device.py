#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-27
# @Filename: test_device.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from clu import Device
from clu.protocol import TCPStreamPeriodicServer


pytestmark = [pytest.mark.asyncio]


@pytest.fixture
async def device(unused_tcp_port_factory, event_loop):
    async def emit_number(transport):
        transport.write(f"Writing to transport {str(transport)}\n".encode())

    server = TCPStreamPeriodicServer(
        host="localhost",
        port=unused_tcp_port_factory(),
        periodic_callback=emit_number,
        sleep_time=0.1,
    )

    await server.start()

    yield server

    server.stop()


@pytest.fixture
async def device_client(device):
    received = []

    async def handle_received(line):
        received.append(line)

    _device = Device("localhost", device.port, callback=handle_received)
    _device.received = received

    await _device.start()
    await asyncio.sleep(0.01)

    yield _device

    await _device.stop()


async def test_device(device_client):
    await asyncio.sleep(0.55)
    assert len(device_client.received) == 5


async def test_write_to_device(device_client):
    assert device_client.write("writing to device") is None


async def test_connection_not_open(device):
    device_client = Device("localhost", device.port)

    with pytest.raises(RuntimeError):
        await device_client._listen()


async def test_connection_already_open(device, device_client):
    with pytest.raises(RuntimeError):
        await device_client.start()
