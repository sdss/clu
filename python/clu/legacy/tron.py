#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-10
# @Filename: tron.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

from clu.model import BaseModel, Property
from clu.protocol import TCPStreamClient

from .keys import KeysDictionary
from .parser import ParseError, ReplyParser


__all__ = ['TronConnection', 'TronModel', 'TronKey']


class TronKey(Property):
    """A Tron model key with callbacks.

    Differs from `.Property` in that it is usually instantiated by
    `.TronModel` with a ``key`` that is of type ``clu.legacy.keys.Key``
    instead of a string.

    """

    def __repr__(self):
        return f'<{self.__class__.__name__!s} ({self.key.name}): {self.value}>'


class TronModel(BaseModel):
    """A JSON-compliant model for actor keywords.

    Parameters
    ----------
    keydict : KeysDictionary
        A dictionary of keys that define the datamodel.
    callback
        A function or coroutine to call when the datamodel changes. The
        function is called with the instance of `TronModel` as the only
        parameter. If the callback is a coroutine, it is scheduled as a task.
    log : ~logging.Logger
        Where to log messages.

    """

    def __init__(self, keydict, callback=None, log=None):

        super().__init__(keydict.name, callback, log=log)

        self.keydict = keydict

        for key in self.keydict.keys:
            key = self.keydict.keys[key]
            self[key.name] = TronKey(key, model=self)

    def parse_reply(self, reply):
        """Parses a reply and updates the datamodel."""

        for reply_key in reply.keywords:

            key_name = reply_key.name.lower()
            if key_name not in self.keydict:
                if self.log:
                    self.log.warning('cannot parse unknown keyword '
                                     f'{self.name}.{reply_key.name}.')
                continue

            # When parsed the values in reply_key are string. After consuming
            # it with the Key, the values become typed values.
            result = self.keydict.keys[key_name].consume(reply_key)

            if not result:
                if self.log:
                    self.log.warning('failed parsing keyword '
                                     f'{self.name}.{reply_key.name}.')
                continue

            self[reply_key.name].value = [value.native for value in reply_key.values]

            if self.callback:
                self.scheduler.add_callback(self.callback, self)


class TronConnection(object):
    """Allows to send commands to Tron and manages the feed of replies.

    Parameters
    ----------
    actor : str
        The actor that is connecting to Tron. Used as the commander when
        sending commands through the hub.
    host : str
        The host on which Tron is running.
    port : int
        The port on which Tron is running.
    model_names : list
        A list of strings with the actors whose models will be tracked.
    log : ~logging.Logger
        Where to log messages.

    """

    def __init__(self, actor, host, port, model_names=None, log=None):

        self.actor = actor

        self.host = host
        self.port = port

        self.log = log

        self._mid = 1

        model_names = model_names or []

        #: dict: The `KeysDictionary` associated with each actor to track.
        self.keyword_dicts = {actor: KeysDictionary.load(actor)
                              for actor in model_names}

        #: dict: The `TronModel` instance holding the model and values of each actor being tracked.
        self.models = {actor: TronModel(self.keyword_dicts[actor], log=log)
                       for actor in model_names}

        self._parser = None

        self.connection = None

    async def start(self, get_keys=True):
        """Starts the connection to Tron.

        Parameters
        ----------
        get_keys : bool
            If `True`, gets all the keys in the models.

        """

        self.connection = await TCPStreamClient(self.host, self.port)

        self._parser = asyncio.create_task(self._parse_tron())

        if get_keys:
            asyncio.create_task(self.get_keys())

    def send_command(self, target, command_string, mid=None):
        """Sends a command through the hub.

        Parameters
        ----------
        target : str
            The actor to command.
        command_string : str
            The command to send.
        mid : int
            The message id. If `None`, a sequentially increasing value will
            be used. You should not specify a ``mid`` unless you really know
            what you're doing.

        """

        mid = mid or self._mid

        # The mid must be a 32-bit unsigned number.
        if mid >= 2**32:
            self._mid = mid = 1

        # The format for the SDSS Hub is "commander message_id target command"
        # where commander needs to start with a letter and have a program and
        # a user joined by a dot. Otherwise the command will be accepted but
        # the reply will fail to parse.
        command = f'{self.actor}.{self.actor} {mid} {target} {command_string}\n'

        self.connection.writer.write(command.encode())

        self._mid += 1

    async def get_keys(self):
        """Gets all the keys for the models being tracked."""

        # Number of keys to be requested at once
        n_keys = 10

        for model in self.models.values():

            actor = model.name
            keys = [key.lower() for key in model]

            for ii in range(0, len(keys), n_keys):

                keys_to_request = keys[ii:ii + n_keys]

                if len(keys_to_request) == 0:
                    break

                keys_joined = ' '.join(keys_to_request)

                command_string = f'getFor={actor} {keys_joined}'

                self.send_command('keys', command_string)

    async def _parse_tron(self):
        """Tracks new replies from Tron and updates the model."""

        rparser = ReplyParser()

        while True:

            line = await self.connection.reader.readline()

            try:
                line = line.decode()  # Do not strip here or that will cause parsing problems.
                reply = rparser.parse(line)
            except ParseError:
                if self.log:
                    self.log.debug(f'failed parsing reply {line}.')
                continue

            actor = reply.header.actor

            # The keys command returns keywords as if from the actor
            # keys_<actor> (e.g. keys_tcc).
            if actor.startswith('keys_'):
                actor = actor.split('_')[1]

            if actor not in self.models:
                continue

            try:
                self.models[actor].parse_reply(reply)
            except Exception as ee:
                if self.log:
                    self.log.debug(f'failed parsing reply {reply!r} with error: {ee!s}')
