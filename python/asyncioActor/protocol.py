#!/usr/bin/env python
# encoding: utf-8
#
# @Author: José Sánchez-Gallego
# @Date: Jan 19, 2018
# @Filename: protocol.py
# @License: BSD 3-Clause
# @Copyright: José Sánchez-Gallego


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import


__all__ = ['TCPServerClientProtocol']


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
