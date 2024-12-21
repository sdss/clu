#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-01-25
# @Filename: rabbitmq.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import os
import re
import socket
import subprocess
from tempfile import gettempdir

import pytest
from aio_pika import Connection, Exchange, Queue, connect
from mirakuru import TCPExecutor
from mirakuru.exceptions import ProcessExitedWithError


# This file copies several functions from pytest-rabbitmq which don't work anymore
# pampqp and other newer package versions.
# See https://github.com/ClearcodeHQ/pytest-rabbitmq


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 0))
    portnum = s.getsockname()[1]
    s.close()

    if portnum > 65000:
        return find_free_port()

    return portnum


class RabbitMqExecutor(TCPExecutor):
    """RabbitMQ executor to start specific rabbitmq instances."""

    _UNWANTED_QUEUE_PATTERN = re.compile("(done|timeout:|listing queues)")
    _UNWANTED_EXCHANGE_PATTERN = re.compile("(done|timeout:|listing exchanges)")

    def __init__(
        self,
        command,
        host,
        port,
        rabbit_ctl,
        path,
        plugin_path,
        node_name=None,
        **kwargs,
    ):
        """Initialize RabbitMQ executor."""

        envvars = {
            "RABBITMQ_LOG_BASE": gettempdir() + f"/rabbit-server.{port}.log",
            "RABBITMQ_MNESIA_BASE": path + "mnesia",
            "RABBITMQ_ENABLED_PLUGINS_FILE": plugin_path + "/plugins",
            "RABBITMQ_NODE_PORT": str(port),
            "RABBITMQ_NODENAME": node_name or f"rabbitmq-test-{port}",
        }
        super().__init__(command, host, port, timeout=60, envvars=envvars, **kwargs)
        self.rabbit_ctl = rabbit_ctl

    def rabbitctl_output(self, *args):
        """Query rabbitctl with args."""
        ctl_command = [self.rabbit_ctl]
        ctl_command.extend(args)
        return subprocess.check_output(
            ctl_command,
            env=self._popen_kwargs["env"],
        ).decode("utf-8")

    def list_exchanges(self):
        """Get exchanges defined on given rabbitmq."""
        exchanges = []
        output = self.rabbitctl_output("list_exchanges", "name")

        for exchange in output.split("\n"):
            exc_lower = exchange.strip(". ").lower()
            if exchange and not self._UNWANTED_EXCHANGE_PATTERN.search(exc_lower):
                exchanges.append(str(exchange))

        return exchanges

    def list_queues(self):
        """Get queues defined on given rabbitmq."""
        queues = []
        output = self.rabbitctl_output("list_queues", "name")

        for queue in output.split("\n"):
            queue_lower = queue.strip(". ").lower()
            if queue and not self._UNWANTED_QUEUE_PATTERN.search(queue_lower):
                queues.append(str(queue))

        return queues


def get_rabbitmq_proc_fixture(
    server=None,
    host=None,
    port=None,
    node=None,
    ctl=None,
    logsdir=None,
    plugindir=None,
):
    """Fixture factory for RabbitMQ process."""

    @pytest.fixture(scope="session")
    def rabbitmq_proc_fixture(request):
        """Fixture for RabbitMQ process."""

        DEFAULT_CTL = "/opt/homebrew/opt/rabbitmq/sbin/rabbitmqctl"
        DEFAULT_SERVER = "/opt/homebrew/opt/rabbitmq/sbin/rabbitmq-server"

        env_ctl = os.environ.get("PYTEST_RABBITMQ_CTL", DEFAULT_CTL)
        env_server = os.environ.get("PYTEST_RABBITMQ_SERVER", DEFAULT_SERVER)

        rabbit_ctl = ctl or env_ctl or DEFAULT_CTL
        rabbit_server = server or env_server or DEFAULT_SERVER
        rabbit_host = host or "127.0.0.1"

        # Erlang starts a port at rabbitmq port + 20000. We need to be sure that
        # port is in range. This is not perfect because it doesn't ensure port - 20000
        # is going to be free, but should be ok almost always.
        rabbit_port = port or find_free_port() - 20000

        rabbit_path = os.path.join(gettempdir(), f"rabbitmq.{rabbit_port}/")
        rabbit_plugin_path = plugindir or rabbit_path

        rabbit_executor = RabbitMqExecutor(
            rabbit_server,
            rabbit_host,
            rabbit_port,
            rabbit_ctl,
            path=rabbit_path,
            plugin_path=rabbit_plugin_path,
            node_name=node,
        )

        rabbit_executor.start()
        yield rabbit_executor
        try:
            rabbit_executor.stop()
        except ProcessExitedWithError:
            pass

    return rabbitmq_proc_fixture


async def clear_rabbitmq(process, rabbitmq_connection):
    """
    Clear queues and exchanges from given rabbitmq process.
    :param RabbitMqExecutor process: rabbitmq process
    :param rabbitpy.Connection rabbitmq_connection: connection to rabbitmq
    """

    channel = await rabbitmq_connection.channel()
    await channel.set_qos(prefetch_count=1)

    for exchange in process.list_exchanges():
        if exchange.startswith("amq."):
            # ----------------------------------------------------------------
            # From rabbit docs:
            # https://www.rabbitmq.com/amqp-0-9-1-reference.html
            # ----------------------------------------------------------------
            # Exchange names starting with "amq." are reserved for pre-declared
            # and standardised exchanges. The client MAY declare an exchange
            # starting with "amq." if the passive option is set, or the
            # exchange already exists. Error code: access-refused
            # ----------------------------------------------------------------
            continue
        ex = Exchange(channel, exchange)
        await ex.delete(if_unused=True)

    for queue_name in process.list_queues():
        if queue_name.startswith("amq."):
            # ----------------------------------------------------------------
            # From rabbit docs:
            # https://www.rabbitmq.com/amqp-0-9-1-reference.html
            # ----------------------------------------------------------------
            # Queue names starting with "amq." are reserved for pre-declared
            # and standardised queues. The client MAY declare a queue starting
            # with "amq." if the passive option is set, or the queue already
            # exists. Error code: access-refused
            # ----------------------------------------------------------------
            continue
        queue = Queue(channel, queue_name)
        await queue.delete(if_unused=True)


def get_rabbitmq_client_fixture(process_fixture_name, teardown=clear_rabbitmq):
    """
    Client fixture factory for RabbitMQ.
    :param str process_fixture_name: name of RabbitMQ process variable
        returned by rabbitmq_proc
    :param callable teardown: custom callable that clears rabbitmq
    .. note::
        calls to rabbitmqctl might be as slow or even slower
        as restarting process. To speed up, provide Your own teardown function,
        to remove queues and exchanges of your choosing, without querying
        rabbitmqctl underneath.
    :returns RabbitMQ connection
    """

    @pytest.fixture
    async def rabbitmq_factory(request):
        """Client fixture for RabbitMQ."""

        # Load required process fixture
        process = request.getfixturevalue(process_fixture_name)

        url = f"amqp://guest:guest@{process.host}:{process.port}/"
        connection: Connection = await connect(url)

        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)

        yield connection
        await teardown(process, connection)
        await connection.close()

    return rabbitmq_factory
