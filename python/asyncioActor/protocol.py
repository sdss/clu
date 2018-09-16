#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-19
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2018-09-06 16:56:06


from __future__ import absolute_import, division, print_function

import asyncio


__all__ = ['TCPServerClientProtocol', 'TCPClientProtocol', 'TronConnection']


class TCPServerClientProtocol(asyncio.Protocol):

    def __init__(self, conn_cb=None, read_cb=None):

        self.conn_cb = conn_cb
        self.transport = None

        self._read_callback = read_cb

    def connection_made(self, transport):
        """Receives a connection and sends the transport to ``conn_cb``."""

        self.transport = transport
        self.transport._user_id = 0

        if self.conn_cb:
            self.conn_cb(transport)

    def data_received(self, data):

        if self._read_callback:
            self._read_callback(self.transport, data.decode())

    def set_read_callback(self, cb):
        """Sets the callback for `data_received`."""

        self._read_callback = cb


class TCPClientProtocol(asyncio.Protocol):

    def __init__(self, loop):

        self.loop = loop
        self.transport = None

    def connection_made(self, transport):

        self.transport = transport

    def data_received(self, data):
        print('Data received from Tron: {!r}'.format(data.decode()))

    def connection_lost(self, exc):
        self.loop.stop()


class TronConnection(object):

    def __init__(self, host, port, connect_now=True):

        self.host = host
        self.port = port

        self.loop = asyncio.get_event_loop()
        self._conn = self.loop.create_connection(lambda: TCPClientProtocol(self.loop), host, port)

        if connect_now:
            self.connect()

    def connect(self):
        """Initiates the connection."""

        self.transport, self.client_protocol = self.loop.run_until_complete(self._conn)
