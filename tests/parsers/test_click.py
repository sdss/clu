#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-27
# @Filename: test_parser.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import logging
import os

import click
import pytest

import clu.parsers.click
from clu import Command
from clu.parsers.click import (
    ClickParser,
    cancellable,
    command_parser,
    pass_args,
    unique,
)
from clu.testing import setup_test_actor


pytestmark = [pytest.mark.asyncio]


# Use context_settings={"ignore_unknown_options": False} just to hit another
# branch in the parser, it should not change anything in this case.
@command_parser.command(context_settings={"ignore_unknown_options": False})
@click.option("--finish", is_flag=True)
async def command_exit(command, object, finish):
    if finish:
        command.finish()
    raise click.exceptions.Exit()


@command_parser.command()
async def command_abort(command, object):
    raise click.exceptions.Abort()


@command_parser.command()
async def bad_command(command, object):
    raise ValueError("This is an exception in the command.")


@command_parser.group()
@pass_args()
def mygroup(command, object):
    command.replies.append({"object": object})


@mygroup.command()
@click.argument("NEGNUMBER", type=int)
@click.option("-r", "--recursive", is_flag=True)
@click.option("--text", type=str)
async def neg_number_command(command, object, negnumber, recursive, text):
    # Add the values to command.replies so that the test can easily get them.
    command.replies.append({"value": negnumber, "recursive": recursive, "text": text})
    command.finish()


@command_parser.command()
@unique()
async def unique_command(command, object):
    await asyncio.sleep(0.5)
    return command.finish()


@command_parser.command()
@cancellable()
async def cancellable_command(command, object):
    await asyncio.sleep(0.5)
    return command.finish()


@pytest.fixture
async def click_parser(json_actor):

    parser = ClickParser()
    parser.parser_args = ["my_object"]

    # Hack some needed parameters because we are not using ClickParser
    # as a mixin.
    parser.name = "my-parser"
    parser.log = json_actor.log

    json_actor = await setup_test_actor(json_actor)

    yield parser

    json_actor.mock_replies.clear()


async def test_help(json_actor, click_parser):

    cmd = Command(command_string="ping --help", actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.is_done


async def test_help_not_found(json_actor, click_parser):

    cmd = Command(command_string="png --help", actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.did_fail


async def test_exit(json_actor, click_parser):

    cmd = Command(command_string="command-exit", actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.did_fail
    assert "Command 'command-exit' was aborted" in json_actor.mock_replies[-1]["error"]


async def test_exit_finish(json_actor, click_parser):

    cmd = Command(command_string="command-exit --finish", actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    # Wait a bit more to allow for extra messages to arrive.
    await asyncio.sleep(0.1)

    assert cmd.status.is_done


async def test_abort(json_actor, click_parser):

    cmd = Command(command_string="command-abort", actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.did_fail
    assert "Command 'command-abort' was aborted" in json_actor.mock_replies[-1]["error"]


async def test_uncaught_exception(json_actor, click_parser, caplog):

    cmd = Command(command_string="bad-command", actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.did_fail
    assert "uncaught error" in json_actor.mock_replies[-1]["error"]

    last_log = caplog.record_tuples[-1]
    assert last_log[1] == logging.ERROR
    assert "Command 'bad-command' failed with error:" in last_log[2]

    # Confirm the traceback was logged.
    log_filename = click_parser.log.log_filename
    assert os.path.exists(log_filename)

    log_data = open(log_filename).read()
    assert "This is an exception in the command." in log_data


@pytest.mark.parametrize(
    "command_string",
    [
        "neg-number-command -15",
        "neg-number-command -r -15",
        "neg-number-command --recursive -15",
        "neg-number-command -15 -r",
        "neg-number-command -15 --recursive",
        "neg-number-command -r 15",
    ],
)
async def test_command_neg_number(json_actor, click_parser, command_string):

    cmd = Command(command_string="mygroup " + command_string, actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.did_succeed
    # This is a different test. We are testing that mygroup got called
    # with the parser_obj "object" and its value was passed.
    assert cmd.replies[-3]["object"] == "my_object"

    if "-15" in command_string:
        assert cmd.replies[-2]["value"] == -15
    else:
        assert cmd.replies[-2]["value"] == 15

    if "-r" in command_string or "--recursive" in command_string:
        assert cmd.replies[-2]["recursive"] is True
    else:
        assert cmd.replies[-2]["recursive"] is False


async def test_keyword(json_actor, click_parser):

    cmd = Command(command_string="keyword version", actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.did_succeed
    assert len(json_actor.mock_replies) == 5
    assert json_actor.mock_replies[1]["text"].strip() == "version = {"


async def test_keyword_bad_parameter(json_actor, click_parser):

    cmd = Command(command_string="keyword bad_param", actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.did_fail
    assert len(json_actor.mock_replies) == 2
    assert "is not part of the data model" in json_actor.mock_replies[1]["error"]


async def test_keyword_no_model(json_actor, click_parser):

    json_actor.model = None

    cmd = Command(command_string="keyword version", actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.did_fail
    assert len(json_actor.mock_replies) == 2
    assert "Actor does not have a data model" in json_actor.mock_replies[1]["error"]


async def test_string_with_spaces(json_actor, click_parser):

    cmd = Command(command_string='mygroup neg-number-command --text "A test" -1')
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.did_succeed
    assert cmd.replies[-1]["text"] == "A test"


async def test_unique(json_actor, click_parser):

    cmd = Command("unique-command", actor=json_actor)
    click_parser.parse_command(cmd)
    await asyncio.sleep(0.01)

    cmd2 = Command("unique-command", actor=json_actor)
    click_parser.parse_command(cmd2)
    await cmd2

    assert cmd2.status.did_fail
    assert (
        "Another command with name unique-command" in cmd2.replies[-1].message["error"]
    )


async def test_cancellable(json_actor, click_parser):

    cmd = Command("cancellable-command", actor=json_actor)
    click_parser.parse_command(cmd)
    await asyncio.sleep(0.01)

    cmd2 = Command("cancellable-command --stop", actor=json_actor)
    click_parser.parse_command(cmd2)
    await cmd2
    await cmd

    assert cmd.status.did_fail
    assert cmd2.status.did_succeed
    assert "This command has been cancelled." in cmd.replies[-1].message["error"]
    assert "Command has been stopped." in cmd2.replies[-1].message["text"]


async def test_cancellable_cannot_find(json_actor, click_parser, mocker):

    mocker.patch.object(clu.parsers.click, "get_running_tasks", return_value=None)

    cmd = Command("cancellable-command --stop", actor=json_actor)
    click_parser.parse_command(cmd)
    await cmd

    assert cmd.status.did_fail
    assert "Cannot find a running command" in cmd.replies[-1].message["error"]


async def test_cancellable_duplicate(json_actor, click_parser):

    cmd = Command("cancellable-command", actor=json_actor)
    click_parser.parse_command(cmd)
    await asyncio.sleep(0.01)

    cmd2 = Command("cancellable-command", actor=json_actor)
    click_parser.parse_command(cmd2)
    await cmd2

    assert cmd2.status.did_fail
    assert (
        "Another command with name cancellable-command"
        in cmd2.replies[-1].message["error"]
    )
