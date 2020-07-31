#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-16
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import json
import re
import time
import uuid
from contextlib import suppress

from .base import BaseActor
from .client import AMQPClient
from .command import Command
from .exceptions import CommandError
from .model import ModelSet
from .parser import ClickParser
from .protocol import TCPStreamServer
from .tools import log_reply


try:
    import aio_pika as apika
except ImportError:
    apika = None


__all__ = ['AMQPActor', 'JSONActor', 'TimerCommand', 'TimerCommandList']


class AMQPActor(AMQPClient, ClickParser, BaseActor):
    """An actor class that uses AMQP message brokering.

    This class differs from `~clu.legacy.actor.LegacyActor` in that it uses
    an AMQP messaging broker (typically RabbitMQ) to communicate with other
    actors in the system, instead of standard TCP sockets. Although the
    internals and protocols are different the entry points and behaviour for
    both classes should be almost identical.

    See the documentation for `.AMQPClient` for parameter information.

    """

    def __init__(self, *args, model_path=None, model_names=None, **kwargs):

        AMQPClient.__init__(self, *args, **kwargs)

        self.commands_queue = None

        if model_path:

            model_names = model_names or []

            if self.name not in model_names:
                model_names.append(self.name)

            self.models = ModelSet(model_path, model_names=model_names,
                                   raise_exception=False, log=self.log)

        else:

            self.log.warning('no models loaded.')
            self.models = None

        self.timer_commands = TimerCommandList(self)

    async def start(self, **kwargs):
        """Starts the connection to the AMQP broker."""

        # This sets the replies queue but not a commands one.
        await AMQPClient.start(self, **kwargs)

        # Binds the commands queue.
        self.commands_queue = await self.connection.add_queue(
            f'{self.name}_commands', callback=self.new_command,
            bindings=[f'command.{self.name}.#'])

        self.log.info(f'commands queue {self.commands_queue.name!r} '
                      f'bound to {self.connection.connection.url!s}')

        self.timer_commands.start()

        return self

    async def new_command(self, message):
        """Handles a new command received by the actor."""

        with message.process():

            headers = message.info()['headers']
            command_body = json.loads(message.body.decode())

        commander_id = headers['commander_id'].decode()
        command_id = headers['command_id'].decode()
        command_string = command_body['command_string']

        try:
            command = Command(command_string, command_id=command_id,
                              commander_id=commander_id,
                              consumer_id=self.name,
                              actor=self, loop=self.loop)
            command.actor = self  # Assign the actor
        except CommandError as ee:
            await self.write('f', {'text': f'Could not parse the '
                                           f'following as a command: {ee!r}'})
            return

        return self.parse_command(command)

    async def handle_reply(self, message):
        """Handles a reply received by the message and updates the models.

        Parameters
        ----------
        message : aio_pika.IncomingMessage
            The message received.

        """

        reply = await AMQPClient.handle_reply(self, message)

        if self.models and reply.sender in self.models:
            self.models[reply.sender].update_model(reply.body)

        return

    async def write(self, message_code='i', message=None, command=None,
                    broadcast=False, **kwargs):
        """Writes a message to user(s).

        Parameters
        ----------
        message_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        message : dict
            The keywords to be output. Must be a dictionary of pairs
            ``{keyword: value}``.
        command : Command
            The command to which we are replying. If not set, it is assumed
            that this is a broadcast.
        broadcast : bool
            Whether to broadcast the message to all the users or only to the
            commander.
        kwargs
            Keyword arguments that will be added to the message.

        """

        message = message or {}

        assert isinstance(message, dict), 'message must be a dictionary'

        message.update(kwargs)

        message_json = json.dumps(message)

        if command is None:
            broadcast = True

        commander_id = command.commander_id if command else None
        command_id = command.command_id if command else None

        headers = {'message_code': message_code,
                   'commander_id': commander_id,
                   'command_id': command_id,
                   'sender': self.name}

        if broadcast:
            routing_key = 'reply.broadcast'
        else:
            routing_key = f'reply.{command.commander_id}'

        await self.connection.exchange.publish(
            apika.Message(message_json.encode(),
                          content_type='text/json',
                          headers=headers,
                          correlation_id=command_id),
            routing_key=routing_key)

        log_reply(self.log, message_code, message_json)


class JSONActor(ClickParser, BaseActor):
    """A TCP actor that replies using JSON.

    This implementation of `.BaseActor` uses TCP as command/reply channel and
    replies to the user by sending a JSON-valid string. This makes it useful
    as a "device" actor that is not connected to the central message parsing
    system but that we still want to accept commands and reply with easily
    parseable messages.

    Commands received by this actor must be in the format
    ``[<uid>] <command string>``, where ``<uid>`` is any integer unique
    identifier that will be used as ``command_id`` and appended to any reply.

    Parameters
    ----------
    name : str
        The actor name.
    host : str
        The host where the TCP server will run.
    port : int
        The port of the TCP server.
    args,kwargs
        Arguments to be passed to `.BaseActor`.

    """

    def __init__(self, name, host, port, *args, **kwargs):

        super().__init__(name, *args, **kwargs)

        self.host = host
        self.port = port

        #: Mapping of commander_id to transport
        self.transports = dict()

        #: TCPStreamServer: The server to talk to this actor.
        self.server = TCPStreamServer(host, port, loop=self.loop,
                                      connection_callback=self.new_user,
                                      data_received_callback=self.new_command)

        self.timer_commands = TimerCommandList(self)

    async def start(self):
        """Starts the TCP server."""

        await self.server.start_server()
        self.log.info(f'running TCP server on {self.host}:{self.port}')

        self.timer_commands.start()

        return self

    async def run_forever(self):
        """Runs the actor forever, keeping the loop alive."""

        await self.server.serve_forever()

    def new_user(self, transport):
        """Assigns userID to new client connection."""

        if transport.is_closing():
            if hasattr(transport, 'user_id'):
                self.log.debug(f'user {transport.user_id} disconnected.')
                return self.transports.pop(transport.user_id)

        user_id = str(uuid.uuid4())
        transport.user_id = user_id
        self.transports[user_id] = transport

        sock = transport.get_extra_info('socket')
        if sock is not None:
            peername = sock.getpeername()[0]
            self.log.debug(f'user {user_id} connected from {peername}.')

        return

    def new_command(self, transport, command_str):
        """Handles a new command received by the actor."""

        commander_id = getattr(transport, 'user_id', None)
        message = command_str.decode().strip()

        if not message:
            return

        command_id, command_string = re.match(r'([0-9]*)\s*(.+)', message).groups()

        if command_id == '':
            command_id = 0
        else:
            command_id = int(command_id)

        command_string = command_string.strip()

        if not command_string:
            return
        try:
            command = Command(command_string=command_string,
                              commander_id=commander_id,
                              command_id=command_id,
                              consumer_id=self.name,
                              actor=self, loop=self.loop,
                              transport=transport)
        except CommandError as ee:
            self.write('f', {'text': f'Could not parse the following as a command: {ee!r}'})
            return

        return self.parse_command(command)

    def send_command(self):
        """Not implemented for `.JSONActor`."""

        raise NotImplementedError('JSONActor cannot send commands to other actors.')

    def write(self, message_code='i', message=None, command=None,
              broadcast=False, beautify=True, **kwargs):
        """Writes a message to user(s) as a JSON.

        A ``header`` keyword with the ``commander_id`` (i.e., the user id of
        the transport that sent the command), ``command_id``, ``message_code``,
        and ``sender`` is added to each message. The payload of the message
        is written to ``data``. An example of a valid message is

        .. code-block:: yaml

            {
                "header": {
                    "command_id": 0,
                    "commander_id": 1,
                    "message_code": "i",
                    "sender": "test_camera"
                },
                "message": {
                    "camera": {
                        "name": "test_camera",
                        "uid": "DEV_12345"
                    },
                    "status": {
                        "temperature": 25.0,
                        "cooler": 10.0
                    }
                }
            }

        Parameters
        ----------
        message_code : str
            The message code (e.g., ``'i'`` or ``':'``). Ignored.
        message : dict
            The keywords to be output. Must be a dictionary of pairs
            ``{keyword: value}``.
        command : Command
            The command to which we are replying. If not set, it is assumed
            that this is a broadcast.
        broadcast : bool
            Whether to broadcast the message to all the users or only to the
            commander.
        beautify : bool
            Whether to format the JSON to make it more readable.
        kwargs
            Keyword arguments that will used to update the message.

        """

        message = message or {}
        assert isinstance(message, dict), 'message must be a dictionary'
        message.update(kwargs)

        commander_id = command.commander_id if command else None
        command_id = command.command_id if command else None
        transport = command.transport if command else None

        message_full = {}
        header = {'header': {'command_id': command_id,
                             'commander_id': commander_id,
                             'message_code': message_code,
                             'sender': self.name}
                  }

        message_full.update(header)
        message_full.update({'data': message})

        if beautify:
            message_json = json.dumps(message_full, sort_keys=False, indent=4)
        else:
            message_json = json.dumps(message_full, sort_keys=False)

        message_json += '\n'

        if broadcast or commander_id is None or transport is None:
            for transport in self.transports.values():
                transport.write(message_json.encode())
        else:
            transport.write(message_json.encode())

        log_reply(self.log, message_code, message_json)


class TimerCommandList(list):
    """A list of `.TimerCommand` objects that will be executed on a loop.

    Parameters
    ----------
    actor
        The actor in which the commands are to be run.
    resolution : float
        In seconds, how frequently to check if any of the `.TimerCommand` must
        be executed.

    """

    def __init__(self, actor, resolution=0.5, loop=None):

        self.resolution = resolution
        self.actor = actor
        self._task = None
        self.loop = loop or asyncio.get_event_loop()

        list.__init__(self, [])

    def add_command(self, command_string, **kwargs):
        """Adds a new `.TimerCommand`."""

        self.append(TimerCommand(command_string, **kwargs))

    async def poller(self):
        """The polling loop."""

        current_time = time.time()

        while True:

            for timer_command in self:
                elapsed = current_time - timer_command.last_run
                if elapsed > timer_command.delay:
                    timer_command_task = self.loop.create_task(timer_command.run(self.actor))
                    timer_command_task.add_done_callback(timer_command.done)

            self._sleep_task = self.loop.create_task(asyncio.sleep(self.resolution))

            await self._sleep_task
            current_time += self.resolution

    def start(self):
        """Starts the loop."""

        if self.running:
            raise RuntimeError('poller is already running.')

        self._task = self.loop.create_task(self.poller())

        return self

    async def stop(self):
        """Cancel the poller."""

        if not self.running:
            return

        self._task.cancel()

        with suppress(asyncio.CancelledError):
            await self._task

    @property
    def running(self):
        """Returns `True` if the poller is running."""

        if self._task and not self._task.cancelled():
            return True

        return False


class TimerCommand(object):
    """A command to be executed on a loop.

    Parameters
    ----------
    command_string : str
        The command string to run.
    delay : float
        How many seconds to wait between repeated calls.

    """

    def __init__(self, command_string, delay=1):

        self.command_string = command_string
        self.delay = delay

        self.last_run = 0.0

    async def run(self, actor):
        """Run the command."""

        await Command(self.command_string, actor=actor).parse()

    def done(self, task):
        """Marks the execution of a command."""

        self.last_run = time.time()
