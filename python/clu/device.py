#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-14
# @Filename: device.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import contextlib

from .base import CallbackScheduler
from .protocol import TCPStreamClient


__all__ = ['Device']


class Device(object):
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
        The coroutine to call when a new message is received. The coroutine
        gets a single argument with all the buffer received from the client
        until a newline arrives. If no callback is specified,
        `.process_message` is called. The callback is always awaited and it is
        the user's responsibility to handle long tasks appropriately. If the
        callback is not a coroutine, it will be converted to one.

    """

    def __init__(self, host, port, callback=None):

        self.host = host
        self.port = port

        #: TCPStreamClientContainer: the connection to the device.
        self.connection = None
        self.listener = None
        self.scheduler = CallbackScheduler()

        self.callback = callback or self.process_message
        if not asyncio.iscoroutinefunction(self.callback):
            self.callback = asyncio.coroutine(self.callback)

    async def start(self):
        """Opens the connection and starts the listener."""

        if self.is_connected():
            raise RuntimeError('connection is already running.')

        self.connection = await TCPStreamClient(self.host, self.port)
        self.listener = asyncio.create_task(self._listen())

    async def stop(self):
        """Closes the connection and stops the listener."""

        self.connection.close()
        await self.connection.writer.wait_closed()  # Waits until it's really closed.

        with contextlib.suppress(asyncio.CancelledError):
            self.listener.cancel()
            await self.listener

    def is_connected(self):
        """Returns `True` if the connection is open."""

        if self.connection is None:
            return False

        return not self.connection.writer.is_closing()

    def write(self, message, newline='\n'):
        """Write to the device. The message is encoded and a new line added."""

        assert self.is_connected() and self.connection.writer, 'device is not connected'

        message = message.strip() + newline
        self.connection.writer.write(message.encode())

    async def _listen(self):
        """Listens to the reader stream and callbacks on message received."""

        if not self.connection:
            raise RuntimeError('connection is not open.')

        while True:
            line = await self.connection.reader.readline()
            line = line.decode().strip()
            await self.callback(line)

    async def process_message(self, line):
        """Processes a newly received message."""

        pass
