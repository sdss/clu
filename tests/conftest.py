#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-26
# @Filename: conftest.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import os
import pathlib

import pytest

from clu import AMQPActor, AMQPClient, JSONActor
from clu.protocol import open_connection


DATA_DIR = pathlib.Path(os.path.dirname(__file__)) / "data"
# RMQ_PORT = 18888


@pytest.fixture
async def amqp_actor(rabbitmq, event_loop):

    port = rabbitmq.args["port"]

    actor = AMQPActor(name="amqp_actor", schema=DATA_DIR / "schema.json", port=port)
    await actor.start()

    yield actor

    await actor.stop()


@pytest.fixture
async def amqp_client(rabbitmq, amqp_actor, event_loop):

    port = rabbitmq.args["port"]

    client = AMQPClient(name="amqp_client", models=["amqp_actor"], port=port)
    await client.start()

    yield client

    await client.stop()


@pytest.fixture
async def json_actor(unused_tcp_port_factory, event_loop, tmpdir):

    actor = JSONActor(
        "json_actor",
        host="localhost",
        port=unused_tcp_port_factory(),
        log_dir=tmpdir,
        schema=DATA_DIR / "schema.json",
    )

    await actor.start()
    await asyncio.sleep(0.01)

    yield actor

    await actor.stop()


@pytest.fixture
async def json_client(json_actor):

    client = await open_connection(json_actor.host, json_actor.port)
    client.actor = json_actor

    yield client

    client.close()
