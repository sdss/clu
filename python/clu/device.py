#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-14
# @Filename: device.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import contextlib

from .protocol import open_connection
from .tools import CallbackMixIn


__all__ = ['Device']


class Device(CallbackMixIn):
    """A class that handles the TCP connection to a device.

    There are two ways to create a new device. You can create a subclass from
    `.Device` and override the `.process_message` method which handles how you
    react to a new line being received ::

        class MyDevice(Device):

            async def process_message(self, line):
                print(line)

        my_device = MyDevice('192.168.1.10', 4444)
        await my_device.start()

    Note that `.process_message` must be a coroutine. Alternatively you can
    pass a callback that will be called instead of `.process_message` when
    a new message arrives. The callback must also be a coroutine ::

        async def printer(line):
            print(line)

        my_device = MyDevice('192.168.1.10', 4444, callback=printer)
        await my_device.start()


    Parameters
    ----------
    host : str
        The host of the device.
    port : int
        The port on which the device is serving.
    callback
        The callback to call with each new message received from the client.
        If no callback is specified, `.process_message` is called. If the
        callback is not a coroutine, it will be converted to one.

    """

    def __init__(self, host, port, callback=None):

        self.host = host
        self.port = port

        # TCPStreamClient: the connection to the device.
        self._client = None
        self.listener = None

        callback = callback or self.process_message
        CallbackMixIn.__init__(self, callbacks=[callback])

    async def start(self):
        """Opens the connection and starts the listener."""

        if self.is_connected():
            raise RuntimeError('connection is already running.')

        self._client = await open_connection(self.host, self.port)
        self.listener = asyncio.create_task(self._listen())

    async def stop(self):
        """Closes the connection and stops the listener."""

        if self._client:
            self._client.close()

        with contextlib.suppress(asyncio.CancelledError):
            if self.listener:
                self.listener.cancel()
                await self.listener

    def is_connected(self):
        """Returns `True` if the connection is open."""

        if self._client is None:
            return False

        return not self._client.writer.is_closing()

    def write(self, message, newline='\n'):
        """Write to the device. The message is encoded and a new line added."""

        assert self.is_connected() and self._client.writer, 'device is not connected'

        message = message.strip() + newline
        self._client.writer.write(message.encode())

    async def _listen(self):
        """Listens to the reader stream and callbacks on message received."""

        if not self._client:
            raise RuntimeError('connection is not open.')

        while True:
            line = await self._client.reader.readline()
            line = line.decode().strip()
            self.notify(line)

    async def process_message(self, line):  # pragma: no cover
        """Processes a newly received message."""

        pass
