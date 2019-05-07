#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-19
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-06 23:56:05

import asyncio


__all__ = ['TCPProtocol', 'PeriodicTCPServer',
           'TCPStreamServer', 'TCPStreamPeriodicServer']


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
        Callback to call when a new client connects.
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

        self._host = host
        self._port = port

        self.transports = {}
        self.loop = loop or asyncio.get_event_loop()

        self.max_connections = max_connections

        self.connection_callback = connection_callback
        self.data_received_callback = data_received_callback

        #: The `asyncio.Server`. Created when `.start_server` is run.
        self.server = None

    async def start_server(self, host=None, port=None):
        """Returns a `~asyncio.Server` connection."""

        self.server = await asyncio.start_server(self.connection_made,
                                                 host or self._host,
                                                 port or self._port)

        return self.server

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
            except asyncio.streams.IncompleteReadError:
                writer.close()
                del self.transports[writer.transport]
                break

            if self.data_received_callback:
                await self._do_callback(self.data_received_callback,
                                        writer.transport, data)


class TCPStreamPeriodicServer(TCPStreamServer):
    """A TCP server that calls a function periodically.

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

    async def start_server(self, **kwargs):
        """Returns a `~asyncio.Server` connection."""

        server = await super().start_server(**kwargs)

        self.periodic_task = asyncio.create_task(self._emit_periodic())

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

            if self.server and self.periodic_callback:
                for transport in self.transports:
                    await self._do_callback(self.periodic_callback, transport)

            await asyncio.sleep(self.sleep_time)
