#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-09-01
# @Filename: test_command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import logging

import pytest

from clu import Command, CommandError, CommandStatus
from clu.exceptions import CluWarning


@pytest.fixture
def command(mocker):

    yield Command(command_string="say-hello", command_id=100, actor=mocker.MagicMock())


def test_command(command):

    assert command.body == "say-hello"


def test_set_status(command):

    command.set_status(CommandStatus.DONE)
    assert command.status.is_done
    assert command.status == CommandStatus.DONE
    assert command.done()


def test_set_done_command(command):

    command.set_status(CommandStatus.DONE)

    with pytest.warns(CluWarning):
        command.set_status(CommandStatus.DONE)


def test_set_status_fails(command):

    with pytest.raises(TypeError):
        command.set_status({})


def test_set_status_int(command):

    command.set_status(CommandStatus.FAILED.value)
    assert command.status.is_done
    assert command.status.did_fail
    assert command.done()


def test_set_status_str(command):

    command.status = "TIMEDOUT"
    assert command.status.is_done
    assert command.status.did_fail
    assert command.status == CommandStatus.TIMEDOUT
    assert command.done()


def test_set_status_str_fails(command):

    with pytest.raises(TypeError):
        command.set_status("AAAAA")


def test_child_command(command):

    child = Command(command_string="new-command", parent=command)
    assert child.parent == command


def test_child_command_write(command):

    command.command_id = 666
    child = Command(command_string="new-command", parent=command)

    child.write("i", "hello")
    command.actor.write.assert_called_with(
        "i",
        message={"text": "hello"},
        command=command,
        broadcast=False,
        silent=False,
        **{},
    )


def test_child_command_finished(command):

    child = Command(command_string="new-command", parent=command)

    child.finish(text="Finished")
    command.actor.write.assert_called_with(
        "i",
        message={},
        text="Finished",
        command=command,
        broadcast=False,
        silent=False,
        **{},
    )

    assert child.status.did_succeed


def test_child_command_running(command):

    child = Command(command_string="new-command", parent=command)

    child.set_status("RUNNING")
    command.actor.write.assert_not_called()


def test_child_command_failed(command):

    child = Command(command_string="new-command", parent=command)

    child.fail(error="Failed")
    command.actor.write.assert_called_with(
        "e",
        message={},
        error="Failed",
        command=command,
        broadcast=False,
        silent=False,
        **{},
    )

    assert child.status.did_fail


def test_write_str(command):

    command.write("i", "hello")
    command.actor.write.assert_called_with(
        "i",
        message={"text": "hello"},
        command=command,
        broadcast=False,
        silent=False,
        **{},
    )


def test_write_dict(command):

    command.write("i", {"key": "hello"})
    command.actor.write.assert_called_with(
        "i",
        message={"key": "hello"},
        command=command,
        broadcast=False,
        silent=False,
        **{},
    )


def test_write_bad_message(command):

    with pytest.raises(ValueError):
        command.write("i", 100)


def test_write_no_actor(command):

    command.actor = None

    with pytest.raises(CommandError):
        command.write("i", "hi")


@pytest.mark.asyncio
async def test_wait_for_status(command, event_loop):
    async def mark_cancelled():
        await asyncio.sleep(0.01)
        command.set_status(CommandStatus.CANCELLED)

    event_loop.create_task(mark_cancelled())

    await command.wait_for_status(CommandStatus.CANCELLED)

    assert True


@pytest.mark.asyncio
async def test_status_callback(command):

    global result
    result = 0

    def callback(status):
        global result
        result = result + 1
        assert isinstance(status, CommandStatus)

    command.callbacks.append(callback)
    command.finish()
    await asyncio.sleep(0.01)

    assert result


@pytest.mark.asyncio
async def test_time_limit(event_loop):

    command = Command(command_string="new-command", time_limit=0.5)
    await asyncio.sleep(0.6)

    assert command.status == CommandStatus.TIMEDOUT
    assert command.done()


@pytest.mark.parametrize(
    "logcode,sdss_code",
    [
        (logging.DEBUG, "d"),
        (logging.INFO, "i"),
        (logging.WARNING, "w"),
        (logging.ERROR, "e"),
    ],
)
def test_write_logging_code(command, logcode, sdss_code):

    command.write(logcode, "hello")
    command.actor.write.assert_called_with(
        sdss_code,
        message={"text": "hello"},
        command=command,
        broadcast=False,
        silent=False,
        **{},
    )


def test_write_bad_logging_code(command):

    with pytest.raises(ValueError):
        command.write(2, "hello")
