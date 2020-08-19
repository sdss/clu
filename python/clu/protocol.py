#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-19
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

from .exceptions import CluError


try:
    import aio_pika as apika
    import aiormq
except ImportError:
    apika = None


__all__ = ['TCPProtocol', 'PeriodicTCPServer',
           'TCPStreamServer', 'TCPStreamPeriodicServer',
           'TCPStreamClient', 'open_connection',
           'TopicListener']


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
    max_connections : int
        How many clients the server accepts. If `None`, unlimited connections
        are allowed.

    """

    def __init__(self, loop=None, connection_callback=None,
                 data_received_callback=None, max_connections=None):

        self.connection_callback = connection_callback
        self.data_received_callback = data_received_callback

        self.transports = []
        self.max_connections = max_connections

        self.loop = loop or asyncio.get_event_loop()

    @classmethod
    async def create_server(cls, host, port, **kwargs):
        """Returns a `~asyncio.Server` connection."""

        loop = kwargs.get('loop', asyncio.get_event_loop())

        new_tcp = cls(**kwargs)

        server = await loop.create_server(lambda: new_tcp, host, port)

        await server.start_serving()

        return server

    @classmethod
    async def create_client(cls, host, port, **kwargs):
        """Returns a `~asyncio.Transport` and `~asyncio.Protocol`."""

        if 'connection_callback' in kwargs:
            raise KeyError('connection_callback not allowed when creating a client.')

        loop = kwargs.get('loop', asyncio.get_event_loop())

        new_tcp = cls.__new__(cls, **kwargs)
        transport, protocol = await loop.create_connection(lambda: new_tcp, host, port)

        return transport, protocol

    def connection_made(self, transport):
        """Receives a connection and calls the connection callback."""

        if self.max_connections is None or (len(self.transports) < self.max_connections):
            self.transports.append(transport)
        else:
            transport.write('Maximum number of connections reached.')
            transport.close()

        if self.connection_callback:
            self.connection_callback(transport)

    def data_received(self, data):
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
    sleep_time : float
        The delay between two calls to ``periodic_callback``.
    kwargs : dict
        Parameters to pass to `TCPProtocol`

    """

    def __init__(self, periodic_callback=None, sleep_time=1, **kwargs):

        self._periodic_callback = periodic_callback
        self.sleep_time = sleep_time

        self.periodic_task = None

        super().__init__(**kwargs)

    @classmethod
    async def create_client(cls, *args, **kwargs):

        raise NotImplementedError('create_client is not implemented for PeriodicTCPServer.')

    @classmethod
    async def create_server(cls, host, port, *args, **kwargs):
        """Returns a `~asyncio.Server` connection."""

        loop = kwargs.get('loop', asyncio.get_event_loop())

        new_tcp = cls(*args, **kwargs)

        server = await loop.create_server(lambda: new_tcp, host, port)

        await server.start_serving()

        new_tcp.periodic_task = asyncio.create_task(new_tcp._emit_periodic())

        return server

    @property
    def periodic_callback(self):
        """Returns the periodic callback."""

        return self._periodic_callback

    @periodic_callback.setter
    def periodic_callback(self, func):
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
    host : str
        The server host.
    port : int
        The server port.
    connection_callback
        Callback to call when a new client connects or disconnects.
    data_received_callback
        Callback to call when a new data is received.
    loop
        The event loop. The current event loop is used by default.
    max_connections : int
        How many clients the server accepts. If `None`, unlimited connections
        are allowed.

    """

    def __init__(self, host, port, connection_callback=None,
                 data_received_callback=None, loop=None, max_connections=None):

        self.host = host
        self.port = port

        self.transports = {}
        self.loop = loop or asyncio.get_event_loop()

        self.max_connections = max_connections

        self.connection_callback = connection_callback
        self.data_received_callback = data_received_callback

        # The `asyncio.Server`. Created when `.start_server` is run.
        self._server = None

    async def start(self):
        """Starts the server and returns a `~asyncio.Server` connection."""

        self._server = await asyncio.start_server(self.connection_made,
                                                  self.host, self.port)

        return self._server

    def stop(self):
        """Stops the server."""

        self._server.close()

    def serve_forever(self):
        """Exposes ``TCPStreamServer.server.serve_forever``."""

        return self._server.serve_forever()

    def is_serving(self):
        return self._server.is_serving()

    async def _do_callback(self, cb, *args, **kwargs):
        """Calls a function or coroutine callback."""

        if asyncio.iscoroutinefunction(cb):
            return await asyncio.create_task(cb(*args, **kwargs))
        else:
            return cb(*args, **kwargs)

    async def connection_made(self, reader, writer):
        """Called when a new client connects to the server.

        Stores the writer protocol in ``transports``, calls the connection
        callback, if any, and starts a loop to read any incoming data.

        """

        if self.max_connections and len(self.transports) == self.max_connections:
            writer.write('Max number of connections reached.\n'.encode())
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
                await self._do_callback(self.data_received_callback,
                                        writer.transport, data)


class TCPStreamClient:
    """An object containing a writer and reader stream to a TCP server."""

    def __init__(self, host, port):

        self.host = host
        self.port = port

        self.reader = None
        self.writer = None

    async def open_connection(self):
        """Creates the connection."""

        self.reader, self.writer = await asyncio.open_connection(self.host,
                                                                 self.port)

    def close(self):
        """Closes the stream."""

        if self.writer:
            self.writer.close()
        else:
            raise RuntimeError('connection cannot be closed '
                               'because it is not open.')


async def open_connection(host, port):
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
    host : str
        The server host.
    port : int
        The server port.
    period_callback
        Callback to run every iteration.
    sleep_time : float
        The delay between two calls to ``periodic_callback``.
    kwargs : dict
        Parameters to pass to `TCPStreamServer`

    """

    def __init__(self, host, port, periodic_callback=None,
                 sleep_time=1, **kwargs):

        self._periodic_callback = periodic_callback
        self.sleep_time = sleep_time

        self.periodic_task = None

        super().__init__(host, port, **kwargs)

    async def start(self):
        """Starts the server and returns a `~asyncio.Server` connection."""

        self._server = await super().start()

        self.periodic_task = asyncio.create_task(self._emit_periodic())

        return self._server

    @property
    def periodic_callback(self):
        """Returns the periodic callback."""

        return self._periodic_callback

    @periodic_callback.setter
    def periodic_callback(self, func):
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
    user : str
        The user to connect to the RabbitMQ broker.
    host : str
        The host where the RabbitMQ message broker lives.

    """

    def __init__(self, user=None, host=None):

        if not apika:
            raise ImportError('cannot use TopicListener without aoi_pika.')

        self.user = user
        self.host = host

        self.connection = None
        self.channel = None
        self.exchange = None
        self.queues = []

    async def connect(self, exchange_name, channel=None, loop=None,
                      exchange_type=apika.ExchangeType.TOPIC):
        """Initialise the connection.

        Parameters
        ----------
        exchange_name : str
            The name of the exchange to create.
        channel
            If specified, ``user`` and ``host`` are ignored and the connection
            and channel are set from ``channel``.
        exchange_type : str
            The type of exchange to create.
        loop
            Event loop. If empty, the current event loop will be used.

        """

        self.loop = loop or asyncio.get_event_loop()

        if not channel:

            assert self.user and self.host, 'either user or host are not set.'

            self.connection = await apika.connect_robust(user=self.user,
                                                         host=self.host,
                                                         loop=self.loop)

            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=1)

        else:

            self.connection = channel._connection
            self.channel = channel

            self.user = self.connection.url.user
            self.host = self.connection.url.host

        self.exchange = await self.channel.declare_exchange(exchange_name,
                                                            type=exchange_type,
                                                            auto_delete=True)

        return self

    async def add_queue(self, queue_name, callback=None, bindings='*'):
        """Adds a queue with bindings.

        Parameters
        ----------
        queue_name : str
            The name of the queue to create.
        callback
            A callable that will be called when a new message is received in
            the queue. Can be a coroutine.
        bindings : list or str
            The list of bindings for the queue. Can be a list of string or a
            single string in which the bindings are comma-separated.

        """

        if isinstance(bindings, str):
            bindings = bindings.split(',')
        elif isinstance(bindings, (list, tuple)):
            bindings = list(bindings)
        else:
            raise TypeError('invalid type for bindings {bindings!r}.')

        try:
            queue = await self.channel.declare_queue(queue_name, exclusive=True)
        except aiormq.exceptions.ChannelLockedResource:
            raise CluError(f'cannot create queue {queue_name}. '
                           'This may indicate that another instance of the '
                           'same actor is running.')

        for binding in bindings:
            await queue.bind(self.exchange, routing_key=binding)

        self.queues.append(queue)

        if callback:
            queue.consumer_task = self.loop.create_task(queue.consume(callback))

        return queue
