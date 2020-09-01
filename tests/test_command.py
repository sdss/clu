#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-09-01
# @Filename: test_command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from clu import CluError, Command, CommandError, CommandStatus


@pytest.fixture
def command(mocker):

    yield Command(command_string='say-hello', command_id=100,
                  actor=mocker.MagicMock())


def test_command(command):

    assert command.body == 'say-hello'


def test_set_status(command):

    command.set_status(CommandStatus.DONE)
    assert command.status.is_done
    assert command.status == CommandStatus.DONE
    assert command.done()


def test_set_done_command(command):

    command.set_status(CommandStatus.DONE)

    with pytest.raises(RuntimeError):
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

    command.status = 'TIMEDOUT'
    assert command.status.is_done
    assert command.status.did_fail
    assert command.status == CommandStatus.TIMEDOUT
    assert command.done()


def test_set_status_str_fails(command):

    with pytest.raises(TypeError):
        command.set_status('AAAAA')


def test_child_command(command):

    child = Command(command_string='new-command', parent=command)
    assert child.parent == command


def test_child_command_bad_command_id(command):

    with pytest.raises(CluError):
        Command(command_string='new-command', parent=command, command_id=100)


def test_child_command_bad_parent(command):

    with pytest.raises(CluError):
        Command(command_string='new-command', parent='blah')


def test_write_str(command):

    command.write('i', 'hello')
    command.actor.write.assert_called_with('i', message={'text': 'hello'},
                                           command=command,
                                           broadcast=False, **{})


def test_write_dict(command):

    command.write('i', {'key': 'hello'})
    command.actor.write.assert_called_with('i', message={'key': 'hello'},
                                           command=command,
                                           broadcast=False, **{})


def test_write_bad_message(command):

    with pytest.raises(ValueError):
        command.write('i', 100)


def test_write_no_actor(command):

    command.actor = None

    with pytest.raises(CommandError):
        command.write('i', 'hi')


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

    def callback():
        global result
        result = result + 1

    command.callbacks.append(callback)
    command.finish()
    await asyncio.sleep(0.01)

    assert result
