#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-27
# @Filename: test_testing.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from clu.command import Command
from clu.legacy import LegacyActor
from clu.parsers.click import command_parser, timeout
from clu.testing import setup_test_actor


pytestmark = [pytest.mark.asyncio]


@command_parser.group()
def group1():
    pass


@group1.command()
async def command1(command):
    command.debug(text="A debug message")
    command.info(text="A info message")
    command.warning(text="A warning message")
    command.error(error="An error message")
    command.finish("This command is finished")


@group1.command()
async def command2(command):
    command.fail(error="This command failed")


@command_parser.command()
@timeout(0.1)
async def slow_command(command):
    await asyncio.sleep(1)
    command.finish("This command is finished")


@pytest.fixture
async def actor(unused_tcp_port_factory):

    _actor = LegacyActor("test_actor", host="localhost", port=unused_tcp_port_factory())
    _actor = await setup_test_actor(_actor)

    yield _actor

    # Clear replies in preparation for next test.
    _actor.mock_replies.clear()


async def test_actor(actor):
    assert actor.name == "test_actor"


async def test_send_command(actor):

    cmd = actor.invoke_mock_command("ping")
    await cmd

    assert isinstance(cmd, Command)
    assert cmd.status.is_done

    assert len(actor.mock_replies) == 2
    assert actor.mock_replies[-1].flag == ":"
    assert actor.mock_replies[-1]["text"] == "Pong."


async def test_send_command1(actor):

    cmd = actor.invoke_mock_command("group1 command1")
    await cmd

    assert cmd.status.is_done

    assert len(actor.mock_replies) == 6
    assert actor.mock_replies[0].flag == ">"
    assert actor.mock_replies[1].flag == "d"
    assert actor.mock_replies[2].flag == "i"
    assert actor.mock_replies[3].flag == "w"
    assert actor.mock_replies[4].flag == "e"
    assert actor.mock_replies[-1].flag == ":"
    assert actor.mock_replies[-1]["text"] == '"This command is finished"'


async def test_send_command2(actor):

    cmd = actor.invoke_mock_command("group1 command2")
    await cmd

    assert cmd.status.did_fail

    assert len(actor.mock_replies) == 2
    assert actor.mock_replies[-1].flag == "f"
    assert actor.mock_replies[-1]["error"] == '"This command failed"'


async def test_command_timeout(actor):

    cmd = actor.invoke_mock_command("slow-command")
    await cmd

    assert cmd.status == cmd.status.TIMEDOUT


async def test_json_actor(json_actor):

    json_actor = await setup_test_actor(json_actor)

    cmd = json_actor.invoke_mock_command("ping")
    await cmd

    assert isinstance(cmd, Command)
    assert cmd.status.is_done

    assert len(json_actor.mock_replies) == 2
    assert json_actor.mock_replies[-1].flag == ":"
    assert json_actor.mock_replies[-1]["text"] == "Pong."


async def test_amqp_actor(amqp_actor):

    amqp_actor = await setup_test_actor(amqp_actor)

    cmd = await amqp_actor.invoke_mock_command("ping")
    await cmd

    assert isinstance(cmd, Command)
    assert cmd.status.is_done

    assert len(amqp_actor.mock_replies) == 2
    assert amqp_actor.mock_replies[-1].flag == ":"
    assert amqp_actor.mock_replies[-1]["text"] == "Pong."
