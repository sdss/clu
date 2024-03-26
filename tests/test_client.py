#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-26
# @Filename: test_client.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import logging

import pytest

from clu import BaseClient


class SimpleClientTester(BaseClient):
    def __init__(
        self,
        name,
        version=None,
        loop=None,
        log_dir=None,
        log=None,
        verbose=False,
        custom_kw=None,
        config={},
    ):
        super().__init__(
            name,
            version=version,
            loop=loop,
            log_dir=log_dir,
            log=log,
            verbose=verbose,
            config=config,
        )

        self.custom_kw = custom_kw

    async def start(self):
        pass


def test_client(caplog):
    client = SimpleClientTester("test_client", version="0.1.0", verbose=True)

    assert client.name == "test_client"
    assert client.version == "0.1.0"

    assert client.log is not None
    assert client.log.sh is not None
    assert client.log.fh is None

    assert len(caplog.record_tuples) == 1
    assert caplog.record_tuples[0] == (
        "clu:test_client",
        logging.DEBUG,
        "test_client: logging system initiated.",
    )


def test_client_file_log(tmpdir):
    log_dir = tmpdir / "logs"
    client = SimpleClientTester("test_client", version="0.1.0", log_dir=log_dir)

    assert client.log.sh is not None
    assert client.log.fh is not None

    assert (log_dir / "test_client.log").exists

    # Remove the fh handler so that test_client_file_log_bad_path doesn't inherit it.
    client.log.handlers.remove(client.log.fh)
    client.log.fh = None


def test_client_file_log_bad_path(mocker):
    log_dir = "InvalidPath"

    logger = mocker.Mock(fh=None)
    logger.configure_mocker(**{"start_file_logger.return_value": None})

    mocker.patch("clu.base.get_logger", return_value=logger)

    client = SimpleClientTester("test_client", version="0.1.0", log_dir=log_dir)

    assert client.log.fh is None


@pytest.mark.asyncio
async def test_client_stop(caplog):
    async def test_task():
        asyncio.sleep(1)

    client = SimpleClientTester("test_client", version="0.1.0")

    task = asyncio.create_task(test_task())

    await client.stop()

    assert task.cancelled


def test_client_config(tmpdir):
    config_file = tmpdir / "config.yaml"

    config_file.write(
        """
name: test_client_from_config
version: '0.1.0'
"""
    )

    client = SimpleClientTester.from_config(config_file)

    assert client.name == "test_client_from_config"
    assert client.version == "0.1.0"
    assert client.custom_kw is None


@pytest.mark.parametrize("header", ("actor", "client"))
def test_client_config_extra_kwarg(tmpdir, header):
    config_file = tmpdir / "config.yaml"

    config_file.write(
        f"""
{header}:
    name: test_client_from_config
    version: '0.1.0'
    custom_kw: 'my custom value'
    extra_kw: 1
"""
    )

    client = SimpleClientTester.from_config(config_file, custom_kw="hola")

    assert client.name == "test_client_from_config"
    assert client.version == "0.1.0"
    assert client.custom_kw == "hola"


def test_client_config_extra_kwarg_varkw():
    # Repeat previous test but now the client has a **kwargs catch-all

    class SimpleClientKwTester(BaseClient):
        def __init__(self, *args, custom_kw=None, **kwargs):
            kwargs.pop("extra_kw")
            super().__init__(*args, **kwargs)
            self.custom_kw = custom_kw

        def start(self):
            pass

    # Also, we pass a dictionary this time, just to test that as well.
    config = {
        "name": "test_client_from_config",
        "version": "0.1.0",
        "custom_kw": "my custom value",
        "extra_kw": 1,
    }

    client = SimpleClientKwTester.from_config(config)

    assert client.name == "test_client_from_config"
    assert client.version == "0.1.0"
    assert client.custom_kw == "my custom value"


def test_client_proxy(mocker):
    client = SimpleClientTester("test_client")
    send_command_mocker = mocker.patch.object(client, "send_command")

    proxy = client.proxy("some_actor")
    proxy.send_command("command1", "--param", "value")

    send_command_mocker.assert_called_with("some_actor", "command1 --param value")
