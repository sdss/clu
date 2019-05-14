#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-13
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-13 19:41:23


import warnings

import clu
from clu.actor import Actor

from .tron import TronConnection


__all__ = ['LegacyActor']


class LegacyActor(Actor):
    """An actor that provides compatibility with the SDSS opscore protocol.

    Parameters
    ----------
    args, kwargs
        Arguments to be passed to `Actor`.
    tron_host : str
        The host on which Tron is running.
    tron_port : int
        The port on which Tron is running.
    tron_models : list
        A list of strings with the actors whose models will be tracked.

    """

    def __init__(self, *args, tron_host=None, tron_port=None, tron_models=None, **kwargs):

        super().__init__(*args, **kwargs)

        if tron_host and tron_port:
            self.tron = TronConnection(self.name, tron_host, tron_port, tron_models=tron_models)
        else:
            self.tron = False

    async def run(self, **kwargs):
        """Starts the server and the Tron client connection."""

        # Start tron connection
        try:
            if self.tron:
                await self.tron.start()
                self.log.info(f'started tron connection at {self.tron.host}:{self.tron.port}')
            else:
                warnings.warn('starting LegacyActor without Tron connection.', clu.CluWarning)
        except ConnectionRefusedError as ee:
            raise clu.CluError(f'failed trying to create a connection to tron: {ee}')

        await super().run(**kwargs)

    @classmethod
    def from_config(cls, config, *args, **kwargs):

        config_dict = cls._parse_config(config)
        if 'tron' in config_dict:
            kwargs.update({'tron_host': config_dict['tron'].get('host', None)})
            kwargs.update({'tron_port': config_dict['tron'].get('port', None)})
            kwargs.update({'tron_models': config_dict['tron'].get('models', None)})

        return super().from_config(config_dict, *args, **kwargs)

    @staticmethod
    def format_user_output(msg_code, msg_str=None, user_id=None, command_id=None):
        """Formats a string to send to users."""

        msg_str = '' if msg_str is None else ' ' + msg_str

        return f'{command_id:d} {user_id:d} {msg_code:s}{msg_str:s}'

    def write(self, msg_code, message=None, command=None, user_id=None,
              command_id=None, escape=True, concatenate=True):
        """Writes a message to user(s).

        Parameters
        ----------
        msg_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        message : str or dict
            The text to be output. It can be either a string with the keywords
            to output or a dictionary of pairs ``{keyword: value}`` where
            ``value`` must be a string.
        command : Command
            User command; used as a default for ``user_id`` and ``command_id``.
            If the command is done, it is ignored.
        user_id : int
            If `None` then use ``command.user_id``.
        command_id : int
            If `None` then use ``command.command_id``.
        escape : bool
            Whether to use `json.dumps` to escape the text of the message.
            This option is ignored unless ``message`` is a dictionary.
        concatenate : bool
            If ``message`` is a dictionary with multiple keywords and
            ``concatenate=True``, all the keywords will be output in a single
            reply with the keywords joined with semicolons. Otherwise each
            keyword will be output in multiple lines.

        """

        user_id, command_id = self.get_user_command_id(command=command,
                                                       user_id=user_id,
                                                       command_id=command_id)

        if message is None:
            lines = ['']
        elif isinstance(message, str):
            lines = [message]
        elif isinstance(message, dict):
            lines = []
            for keyword in message:
                value = message[keyword]
                if escape:
                    value = clu.escape(value)
                lines.append(f'{keyword}={value}')
            if concatenate:
                lines = ['; '.join(lines)]
        else:
            raise TypeError('invalid message type ' + type(message))

        for line in lines:

            full_msg_str = self.format_user_output(msg_code, line,
                                                   user_id=user_id,
                                                   command_id=command_id)

            msg = (full_msg_str + '\n').encode()

            if user_id is None or user_id == 0:
                for transport in self.user_dict.values():
                    transport.write(msg)
            else:
                transport = self.user_dict[user_id]
                transport.write(msg)
