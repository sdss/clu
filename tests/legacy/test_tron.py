#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-04
# @Filename: test_tron.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import logging

import pytest

from clu.legacy.parser import ParseError


pytestmark = pytest.mark.asyncio


async def test_get_keys(tron_client):

    assert tron_client.models['alerts']['version'].value is not None
    assert tron_client.models['alerts']['version'].value[0] == '2.0.1'


async def test_update_model(tron_client):

    tron_client._client.writer.write('.alerts 0 alerts i '
                                     'activeAlerts=Alert1,Alert2\n'
                                     .encode())

    await asyncio.sleep(0.01)

    act_alert = tron_client.models['alerts']['activeAlerts']

    assert act_alert.value is not None

    assert act_alert.value[0] == 'Alert1'
    assert act_alert.key[0].name == 'alertID'

    assert act_alert.value[1] == 'Alert2'
    assert act_alert.key[1].name == 'alertID'

    assert repr(act_alert) == ("<TronKey (activeAlerts): "
                               "['Alert1', 'Alert2']>")


async def test_parser_fails(tron_client, caplog, mocker):

    mocker.patch.object(tron_client.rparser, 'parse', side_effect=ParseError())
    tron_client._client.writer.write('.alerts 0 alerts i '
                                     'activeAlerts=Alert1\n'
                                     .encode())

    await asyncio.sleep(0.01)

    assert tron_client.models['alerts']['activeAlerts'].value[0] != 'Alert1'

    assert caplog.record_tuples == [('tron-test', logging.DEBUG,
                                     'failed parsing reply .alerts '
                                     '0 alerts i activeAlerts=Alert1.')]
