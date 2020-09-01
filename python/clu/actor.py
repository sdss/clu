#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-16
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import json
import re
import uuid

import aio_pika as apika

from .base import BaseActor
from .client import AMQPClient
from .command import Command, TimedCommandList
from .exceptions import CommandError
from .model import Model
from .parser import ClickParser, get_schema
from .protocol import TCPStreamServer
from .tools import log_reply


__all__ = ['AMQPActor', 'JSONActor']


class AMQPActor(AMQPClient, ClickParser, BaseActor):
    """An actor class that uses AMQP message brokering.

    This class differs from `~clu.legacy.actor.LegacyActor` in that it uses
    an AMQP messaging broker (typically RabbitMQ) to communicate with other
    actors in the system, instead of standard TCP sockets. Although the
    internals and protocols are different the entry points and behaviour for
    both classes should be almost identical.

    See the documentation for `.AMQPClient` for additional parameter
    information.

    Parameters
    ----------
    schema : str
        The path to the datamodel schema for the actor, in JSON Schema format.
        If the schema is provided all replies will be validated against it.
        An invalid reply will fail and not be emitted. The schema can also be
        set when subclassing by setting the class ``schema`` attribute.

    """

    schema = None

    def __init__(self, *args, schema=None, **kwargs):

        AMQPClient.__init__(self, *args, **kwargs)

        self.commands_queue = None

        self.timed_commands = TimedCommandList(self)

        # TODO: for now the AMQPActor is the only actor that may use the
        # self-validating schema, but eventually this code should be moved
        # to BaseActor or to a mixin.
        self.schema = self._validate_schema(schema or self.schema)

        # Add the command to get the schema. This command is not added by
        # default because only AMQPActor should have it.
        self.parser.add_command(get_schema)

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

        self.timed_commands.start()

        return self

    def _validate_schema(self, schema):
        """Loads and validates the actor schema."""

        if schema is None:
            return None

        model = Model(self.name, schema, is_file=True, log=self.log)

        return model

    async def new_command(self, message):
        """Handles a new command received by the actor."""

        async with message.process():

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

    async def write(self, message_code='i', message=None, command=None,
                    broadcast=False, no_validate=False, **kwargs):
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
        no_validate : bool
            Do not validate the reply against the actor schema. This is
            ignored if the actor was not started with knowledge of its own
            schema.
        kwargs
            Keyword arguments that will be added to the message.

        """

        message = message or {}

        assert isinstance(message, dict), 'message must be a dictionary'

        message.update(kwargs)

        if not no_validate and self.schema is not None:
            result, err = self.schema.update_model(message)
            if result is False:
                message = {'error': f'Failed validating the reply: {err}'}

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

    def __init__(self, name, host=None, port=None, *args, **kwargs):

        super().__init__(name, *args, **kwargs)

        self.host = host or 'localhost'
        self.port = port

        if self.port is None:
            raise ValueError('port needs to be specified.')

        #: Mapping of commander_id to transport
        self.transports = dict()

        #: TCPStreamServer: The server to talk to this actor.
        self.server = TCPStreamServer(host, port, loop=self.loop,
                                      connection_callback=self.new_user,
                                      data_received_callback=self.new_command)

        self.timed_commands = TimedCommandList(self)

    async def start(self):
        """Starts the TCP server."""

        await self.server.start()
        self.log.info(f'running TCP server on {self.host}:{self.port}')

        self.timed_commands.start()

        return self

    async def stop(self):
        """Stops the client connection and running tasks."""

        if self.server.is_serving():
            self.server.stop()

        await self.timed_commands.stop()

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

    def send_command(self, *args, **kwargs):
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

        Although the messsage is displayed here in multiple lines, it is
        written as a single line to the TCP clients to facilitate parsing.

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

        message_json = json.dumps(message_full, sort_keys=False)
        message_json += '\n'

        if broadcast or commander_id is None or transport is None:
            for transport in self.transports.values():
                transport.write(message_json.encode())
        else:
            transport.write(message_json.encode())

        log_reply(self.log, message_code, message_json)
