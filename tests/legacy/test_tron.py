#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-04
# @Filename: test_tron.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import logging
import sys

import pytest

from clu.legacy import TronConnection, TronKey
from clu.legacy.types.parser import ParseError


pytestmark = [pytest.mark.asyncio]


async def test_get_keys(tron_client):
    assert tron_client.models["alerts"]["version"].value is not None
    assert tron_client.models["alerts"]["version"].value[0] == "2.0.1"


async def test_update_model(tron_client, tron_server):

    # Get the tron_client transport and write to it as if coming from tron
    client_transport = list(tron_server.transports.values())[0]

    client_transport.write(".alerts 0 alerts i activeAlerts=Alert1,Alert2\n".encode())

    await asyncio.sleep(0.01)

    act_alert = tron_client.models["alerts"]["activeAlerts"]

    assert act_alert.value is not None

    assert act_alert.value[0] == "Alert1"
    assert act_alert.keyword[0].name == "alertID"

    assert act_alert.last_seen is not None
    assert tron_client.models["alerts"].last_seen is not None

    assert act_alert.value[1] == "Alert2"
    assert act_alert.keyword[1].name == "alertID"

    assert repr(act_alert) == ("<TronKey (activeAlerts): ['Alert1', 'Alert2']>")


@pytest.mark.skipif(sys.version_info < (3, 8), reason="Test fails in PY37")
async def test_model_callback(tron_client, tron_server, mocker):
    def callback(model, kw):
        pass

    callback_mock = mocker.create_autospec(callback)
    tron_client.models["alerts"].loop = None
    tron_client.models["alerts"].register_callback(callback_mock)

    client_transport = list(tron_server.transports.values())[0]
    client_transport.write(".alerts 0 alerts i activeAlerts=Alert1,Alert2\n".encode())
    await asyncio.sleep(0.01)

    callback_mock.assert_called()
    assert len(callback_mock.call_args) == 2
    assert isinstance(callback_mock.call_args.args[-1], TronKey)
    assert callback_mock.call_args.args[-1].value == ["Alert1", "Alert2"]


async def test_parser_fails(tron_client, tron_server, caplog, mocker):

    caplog.set_level(logging.WARNING, logger="tron-test")

    client_transport = list(tron_server.transports.values())[0]

    mocker.patch.object(tron_client.rparser, "parse", side_effect=ParseError)
    client_transport.write(".alerts 0 alerts i activeAlerts=Alert1\n".encode())

    await asyncio.sleep(0.01)

    assert tron_client.models["alerts"]["activeAlerts"].value[0] != "Alert1"

    assert caplog.record_tuples[-1][1] == logging.WARNING
    assert "Failed parsing reply" in caplog.record_tuples[-1][2]


async def test_model_parse_reply_fails(tron_client, tron_server, caplog, mocker):

    caplog.set_level(logging.WARNING, logger="tron-test")

    client_transport = list(tron_server.transports.values())[0]

    mocker.patch.object(
        tron_client.models["alerts"], "parse_reply", side_effect=ParseError
    )
    client_transport.write(".alerts 0 alerts i activeAlerts=Alert1\n".encode())

    await asyncio.sleep(0.01)

    assert tron_client.models["alerts"]["activeAlerts"].value[0] != "Alert1"

    assert caplog.record_tuples[-1][1] == logging.WARNING
    assert "Failed parsing reply" in caplog.record_tuples[-1][2]


async def test_send_command(actor, tron_server):

    command = actor.send_command("alerts", "ping")
    await command

    assert b"test_actor.test_actor" in tron_server.received[-1]
    assert b"alerts ping" in tron_server.received[-1]

    assert len(command.replies) == 1


async def test_parse_reply_unknown_actor(tron_client, tron_server, caplog):

    client_transport = list(tron_server.transports.values())[0]
    client_transport.write(".sop 0 sop i version=1.0.0\n".encode())

    await asyncio.sleep(0.01)

    # Ensure this reply didn't produce any warning.
    assert len(caplog.record_tuples) == 0


async def test_tron_no_models():

    tron = TronConnection(host="localhost", port=6093)

    assert tron.models == {}
    assert tron.keyword_dicts == {}


async def test_mid_out_of_range(tron_client, tron_server):

    tron_client.send_command("actor", "command", mid=(2 ** 32 + 2))

    assert 2 in tron_client.running_commands


async def test_reload_model(tron_client):

    assert tron_client.models["alerts"]["version"].value[0] == "2.0.1"

    tron_client.models["alerts"].reload()

    assert tron_client.models["alerts"]["version"].value[0] is None


async def test_tron_connected(actor, tron_server):

    assert actor.tron.connected()

    actor.tron.transport.close()

    assert actor.tron.connected() is False
