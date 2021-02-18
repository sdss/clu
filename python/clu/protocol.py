#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-19
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

import aio_pika as apika
import aiormq

from .exceptions import CluError


__all__ = [
    "TCPProtocol",
    "PeriodicTCPServer",
    "TCPStreamServer",
    "TCPStreamPeriodicServer",
    "TCPStreamClient",
    "open_connection",
    "TopicListener",
]

T = TypeVar("T")
ConnectionCallbackType = Callable[[Any], Any]
DataReceivedCallbackType = Callable[[Any, bytes], Any]


class TCPProtocol(asyncio.Protocol):
    """A TCP server/client based on asyncio protocols.

    This is a high-level implementation of the client and server asyncio
    protocols. See `asyncio protocol
    <https://docs.python.org/3/library/asyncio-protocol.html>`__ for details.

    Parameters
    ----------
    loop
        The event loop. The current event loop is used by default.
    connection_callback
        Callback to call when a new client connects.
    data_received_callback
        Callback to call when a new data is received.
    max_connections
        How many clients the server accepts. If `None`, unlimited connections
        are allowed.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop = None,
        connection_callback: Optional[ConnectionCallbackType] = None,
        data_received_callback: Optional[Callable[[str], Any]] = None,
        max_connections: Optional[int] = None,
    ):

        self.connection_callback = connection_callback
        self.data_received_callback = data_received_callback

        self.transports = []
        self.max_connections = max_connections

        self.loop = loop or asyncio.get_event_loop()

    @classmethod
    async def create_server(cls, host: str, port: int, **kwargs):
        """Returns a `~asyncio.Server` connection."""

        loop = kwargs.get("loop", asyncio.get_event_loop())

        new_tcp = cls(**kwargs)

        server = await loop.create_server(lambda: new_tcp, host, port)

        await server.start_serving()

        return server

    @classmethod
    async def create_client(cls, host: str, port: int, **kwargs):
        """Returns a `~asyncio.Transport` and `~asyncio.Protocol`."""

        if "connection_callback" in kwargs:
            raise KeyError("connection_callback not allowed when creating a client.")

        loop = kwargs.get("loop", asyncio.get_event_loop())

        new_tcp = cls.__new__(cls, **kwargs)
        transport, protocol = await loop.create_connection(lambda: new_tcp, host, port)

        return transport, protocol

    def connection_made(self, transport: asyncio.Transport):
        """Receives a connection and calls the connection callback."""

        if self.max_connections is None or (
            len(self.transports) < self.max_connections
        ):
            self.transports.append(transport)
        else:
            transport.write("Maximum number of connections reached.")
            transport.close()

        if self.connection_callback:
            self.connection_callback(transport)

    def data_received(self, data: bytes):
        """Decodes the received data."""

        if self.data_received_callback:
            self.data_received_callback(data.decode())

    def connection_lost(self, exc):
        """Called when connection is lost."""

        pass


class PeriodicTCPServer(TCPProtocol):
    """A TCP server that runs a callback periodically.

    Parameters
    ----------
    period_callback
        Callback to run every iteration.
    sleep_time
        The delay between two calls to ``periodic_callback``.
    kwargs
        Parameters to pass to `TCPProtocol`

    """

    def __init__(
        self,
        periodic_callback: Optional[ConnectionCallbackType] = None,
        sleep_time: float = 1,
        **kwargs,
    ):

        self._periodic_callback = periodic_callback
        self.sleep_time = sleep_time

        self.periodic_task = None

        super().__init__(**kwargs)

    @classmethod
    async def create_client(cls, *args, **kwargs):

        raise NotImplementedError(
            "create_client is not implemented for PeriodicTCPServer."
        )

    @classmethod
    async def create_server(cls, host: str, port: int, *args, **kwargs):
        """Returns a `~asyncio.Server` connection."""

        loop = kwargs.get("loop", asyncio.get_event_loop())

        new_tcp = cls(*args, **kwargs)

        server = await loop.create_server(lambda: new_tcp, host, port)

        await server.start_serving()

        new_tcp.periodic_task = asyncio.create_task(new_tcp._emit_periodic())

        return server

    @property
    def periodic_callback(self) -> Optional[ConnectionCallbackType]:
        """Returns the periodic callback."""

        return self._periodic_callback

    @periodic_callback.setter
    def periodic_callback(self, func: Callable[[asyncio.Transport], Any]):
        """Sets the periodic callback."""

        self._periodic_callback = func

    async def _emit_periodic(self):

        while True:

            if self.periodic_callback is not None:
                for transport in self.transports:
                    if asyncio.iscoroutinefunction(self.periodic_callback):
                        await self.periodic_callback(transport)
                    else:
                        self.periodic_callback(transport)

            await asyncio.sleep(self.sleep_time)


class TCPStreamServer(object):
    """A TCP server based on asyncio streams.

    This is a high-level implementation of the asyncio server using
    streams. See `asyncio streams
    <https://docs.python.org/3/library/asyncio-stream.html>`__ for details.

    Parameters
    ----------
    host
        The server host.
    port
        The server port.
    connection_callback
        Callback to call when a new client connects or disconnects.
    data_received_callback
        Callback to call when a new data is received.
    loop
        The event loop. The current event loop is used by default.
    max_connections
        How many clients the server accepts. If `None`, unlimited connections
        are allowed.
    """

    def __init__(
        self,
        host: str,
        port: int,
        connection_callback: Optional[ConnectionCallbackType] = None,
        data_received_callback: Optional[DataReceivedCallbackType] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        max_connections: Optional[int] = None,
    ):

        self.host = host
        self.port = port

        self.transports = {}
        self.loop = loop or asyncio.get_event_loop()

        self.max_connections = max_connections

        self.connection_callback = connection_callback
        self.data_received_callback = data_received_callback

        # The `asyncio.Server`. Created when `.start_server` is run.
        self._server = None

    async def start(self) -> asyncio.AbstractServer:
        """Starts the server and returns a `~asyncio.Server` connection."""

        self._server = await asyncio.start_server(
            self.connection_made,
            self.host,
            self.port,
        )

        return self._server

    def stop(self):
        """Stops the server."""

        self._server.close()

    def serve_forever(self):
        """Exposes ``TCPStreamServer.server.serve_forever``."""

        return self._server.serve_forever()

    def is_serving(self) -> bool:
        return self._server.is_serving()

    async def _do_callback(self, cb, *args, **kwargs):
        """Calls a function or coroutine callback."""

        if asyncio.iscoroutinefunction(cb):
            return await asyncio.create_task(cb(*args, **kwargs))
        else:
            return cb(*args, **kwargs)

    async def connection_made(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        """Called when a new client connects to the server.

        Stores the writer protocol in ``transports``, calls the connection
        callback, if any, and starts a loop to read any incoming data.
        """

        if self.max_connections and len(self.transports) == self.max_connections:
            writer.write("Max number of connections reached.\n".encode())
            return

        self.transports[writer.transport] = writer

        if self.connection_callback:
            await self._do_callback(self.connection_callback, writer.transport)

        while True:

            try:
                data = await reader.readuntil()
            except asyncio.IncompleteReadError:
                writer.close()
                self.transports.pop(writer.transport)
                if self.connection_callback:
                    await self._do_callback(self.connection_callback, writer.transport)
                break

            if self.data_received_callback:
                await self._do_callback(
                    self.data_received_callback, writer.transport, data
                )


class TCPStreamClient:
    """An object containing a writer and reader stream to a TCP server."""

    def __init__(self, host: str, port: int):

        self.host = host
        self.port = port

        self.reader = None
        self.writer = None

    async def open_connection(self):
        """Creates the connection."""

        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

    def close(self):
        """Closes the stream."""

        if self.writer:
            self.writer.close()
        else:
            raise RuntimeError("connection cannot be closed because it is not open.")


async def open_connection(host: str, port: int) -> TCPStreamClient:
    """Returns a TCP stream connection with a writer and reader.

    This function is equivalent to doing ::

        >>> client = TCPStreamClient('127.0.0.1', 5555)
        >>> await client.open_connection()

    Instead just do ::

        >>> client = await TCPStreamClient('127.0.0.1', 5555)
        >>> client.writer.write('Hi!\\n'.encode())

    Parameters
    ----------
    host : str
        The host of the TCP server.
    port : int
        The port of the TCP server.

    Returns
    -------
    client : `.TCPStreamClient`
        A container for the stream reader and writer.
    """

    client = TCPStreamClient(host, port)
    await client.open_connection()

    return client


class TCPStreamPeriodicServer(TCPStreamServer):
    """A TCP server that calls a function periodically.

    Parameters
    ----------
    host
        The server host.
    port
        The server port.
    period_callback
        Callback to run every iteration. It is called for each transport
        that is connected to the server and receives the transport object.
    sleep_time
        The delay between two calls to ``periodic_callback``.
    kwargs
        Parameters to pass to `TCPStreamServer`

    """

    def __init__(
        self,
        host: str,
        port: int,
        periodic_callback: Optional[Callable[[asyncio.Transport], Any]] = None,
        sleep_time: float = 1,
        **kwargs,
    ):

        self._periodic_callback = periodic_callback
        self.sleep_time = sleep_time

        self.periodic_task = None

        super().__init__(host, port, **kwargs)

    async def start(self) -> asyncio.AbstractServer:
        """Starts the server and returns a `~asyncio.Server` connection."""

        self._server = await super().start()

        self.periodic_task = asyncio.create_task(self._emit_periodic())

        return self._server

    def stop(self):

        self.periodic_task.cancel()
        super().stop()

    @property
    def periodic_callback(self):
        """Returns the periodic callback."""

        return self._periodic_callback

    @periodic_callback.setter
    def periodic_callback(self, func: Callable[[asyncio.Transport], Any]):
        """Sets the periodic callback."""

        self._periodic_callback = func

    async def _emit_periodic(self):

        while True:

            if self._server and self.periodic_callback:
                for transport in self.transports:
                    await self._do_callback(self.periodic_callback, transport)

            await asyncio.sleep(self.sleep_time)


class TopicListener(object):
    """A class to declare and listen to AMQP queues with topic conditions.

    Parameters
    ----------
    url
        RFC3986 formatted broker address. When used, the other keyword
        arguments are ignored.
    user
        The user to connect to the RabbitMQ broker.
    password
        The password for the user.
    host
        The host where the RabbitMQ message broker runs.
    virtualhost
         Virtualhost parameter. ``'/'`` by default.
    port
        The port on which the RabbitMQ message broker is running.
    ssl
        Whether to use TLS/SSL connection.
    """

    def __init__(
        self,
        url: str = None,
        user: str = "guest",
        password: str = "guest",
        host: str = "localhost",
        virtualhost: str = "/",
        port: int = 5672,
        ssl: bool = False,
    ):

        self.url = url
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.virtualhost = virtualhost
        self.ssl = ssl

        self.connection: apika.RobustConnection
        self.channel: apika.Channel
        self.exchange: apika.Exchange
        self.queues: List[apika.Queue] = []

        self._consumer_tag: Dict[apika.Queue, apika.queue.ConsumerTag] = {}

    async def connect(
        self,
        exchange_name: str,
        exchange_type: apika.ExchangeType = apika.ExchangeType.TOPIC,
    ) -> TopicListener:
        """Initialise the connection.

        Parameters
        ----------
        exchange_name
            The name of the exchange to create.
        exchange_type
            The type of exchange to create.
        """

        if self.url:
            self.connection = await apika.connect_robust(self.url)
        else:
            self.connection = await apika.connect_robust(
                login=self.user,
                host=self.host,
                port=self.port,
                password=self.password,
                virtualhost=self.virtualhost,
                ssl=self.ssl,
            )

        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=1)

        self.exchange = await self.channel.declare_exchange(
            exchange_name, type=exchange_type, auto_delete=True
        )

        return self

    async def add_queue(
        self,
        queue_name: str,
        callback: Optional[Callable[[apika.IncomingMessage], Any]] = None,
        bindings: Union[str, List[str]] = "*",
    ) -> apika.Queue:
        """Adds a queue with bindings.

        Parameters
        ----------
        queue_name
            The name of the queue to create.
        callback
            A callable that will be called when a new message is received in
            the queue. Can be a coroutine.
        bindings
            The list of bindings for the queue. Can be a list of string or a
            single string in which the bindings are comma-separated.
        """

        if isinstance(bindings, str):
            bindings = bindings.split(",")
        elif isinstance(bindings, (list, tuple)):
            bindings = list(bindings)
        else:
            raise TypeError(f"invalid type for bindings {bindings!r}.")

        try:
            queue = await self.channel.declare_queue(queue_name, exclusive=True)
        except aiormq.exceptions.ChannelLockedResource:
            raise CluError(
                f"cannot create queue {queue_name}. "
                "This may indicate that another instance of the "
                "same actor is running."
            )

        for binding in bindings:
            await queue.bind(self.exchange, routing_key=binding)

        if callback:
            self._consumer_tag[queue] = await queue.consume(callback)

        self.queues.append(queue)

        return queue

    async def stop(self):
        """Cancels queues and closes the connection."""

        for queue in self.queues:
            consumer_tag = self._consumer_tag.get(queue, None)
            if hasattr(queue, "consumer_tag") and consumer_tag is not None:
                await queue.cancel(consumer_tag)

        await self.connection.close()
