#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-09-07
# @Filename: base.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import collections
import contextlib
import enum
import functools
import json
import logging

from .misc.logger import REPLY


__ALL__ = ['CommandStatus', 'StatusMixIn', 'format_value', 'CallbackScheduler',
           'CaseInsensitiveDict', 'cli_coro', 'value', 'as_complete_failer',
           'log_reply']


class Maskbit(enum.Flag):
    """A maskbit enumeration. Intended for subclassing."""

    @property
    def active_bits(self):
        """Returns a list of flags that match the value."""

        return [bit for bit in self.__class__ if bit.value & self.value]


COMMAND_STATUS_TO_CODE = {
    'DONE': ':',
    'CANCELLED': 'f',
    'FAILED': 'f',
    'TIMEDOUT': 'f',
    'READY': 'i',
    'RUNNING': 'i',
    'CANCELLING': 'w',
    'FAILING': 'w',
    'DEBUG': 'd',
}


class CommandStatus(Maskbit):

    DONE = enum.auto()
    CANCELLED = enum.auto()
    FAILED = enum.auto()
    TIMEDOUT = enum.auto()
    READY = enum.auto()
    RUNNING = enum.auto()
    CANCELLING = enum.auto()
    FAILING = enum.auto()
    DEBUG = enum.auto()

    ACTIVE_STATES = RUNNING | CANCELLING | FAILING
    FAILED_STATES = CANCELLED | FAILED | TIMEDOUT
    FAILING_STATES = CANCELLING | FAILING
    DONE_STATES = DONE | FAILED_STATES
    ALL_STATES = READY | ACTIVE_STATES | DONE_STATES

    def __init__(self, *args):

        if self.name.upper() in COMMAND_STATUS_TO_CODE:
            self.code = COMMAND_STATUS_TO_CODE[self.name.upper()]
        else:
            self.code = None

    @property
    def is_combination(self):
        """Returns True if a flag is a combination."""

        if bin(self).count('1') > 1:
            return True
        return False

    @property
    def did_fail(self):
        """Command failed or was cancelled."""

        return self in self.FAILED_STATES

    @property
    def is_active(self):
        """Command is running, cancelling or failing."""

        return self in self.ACTIVE_STATES

    @property
    def is_done(self):
        """Command is done (whether successfully or not)."""

        return self in self.DONE_STATES

    @property
    def is_failing(self):
        """Command is being cancelled or is failing."""

        return self in self.FAILING_STATES

    @staticmethod
    def get_inverse_dict():
        """Gets a reversed dictionary of code to status.

        Note that the inverse dictionary is not unique and you can get
        different statuses associated with the same code.

        """

        return dict((status.code, status) for status in CommandStatus if status.code)


class StatusMixIn(object):
    """A mixin that provides status tracking with callbacks.

    Provides a status property that executes a list of callbacks when
    the status changes.

    Parameters
    ----------
    maskbit_flags : class
        A class containing the available statuses as a series of maskbit
        flags. Usually as subclass of `enum.Flag`.
    initial_status : str
        The initial status.
    callback_func : function
        The function to call if the status changes.
    call_now : bool
        Whether the callback function should be called when initialising.

    Attributes
    ----------
    callbacks : list
        A list of the callback functions to call.

    """

    def __init__(self, maskbit_flags, initial_status=None,
                 callback_func=None, call_now=False):

        self.flags = maskbit_flags
        self.callbacks = []
        self._status = initial_status
        self.watcher = None

        if callback_func is not None:
            if isinstance(callback_func, (list, tuple)):
                self.callbacks = callback_func
            else:
                self.callbacks.append(callback_func)

        if call_now is True:
            self.do_callbacks()

    def do_callbacks(self):
        """Calls functions in ``callbacks``."""

        assert hasattr(self, 'callbacks'), 'missing callbacks attribute.'

        loop = self.loop if hasattr(self, 'loop') else asyncio.get_event_loop()

        for func in self.callbacks:
            loop.call_soon(func)

    @property
    def status(self):
        """Returns the status."""

        return self._status

    @status.setter
    def status(self, value):
        """Sets the status."""

        if value != self._status:
            self._status = self.flags(value)
            self.do_callbacks()
            if self.watcher is not None:
                self.watcher.set()

    async def wait_for_status(self, value, loop=None):
        """Awaits until the status matches ``value``."""

        if self.status == value:
            return

        if loop is None:
            if hasattr(self, 'loop') and self.loop is not None:
                loop = self.loop
            else:
                loop = asyncio.get_event_loop()

        self.watcher = asyncio.Event(loop=loop)

        while self.status != value:
            await self.watcher.wait()
            if self.watcher is not None:
                self.watcher.clear()

        self.watcher = None


class CallbackScheduler(object):
    """A queue for executing callbacks."""

    def __init__(self, loop=None):

        self.loop = loop or asyncio.get_event_loop()
        self.queue = asyncio.Queue()

        self.running = []  # Running callbacks
        self._task = self.loop.create_task(self._process_queue())

    async def stop(self):
        """Stops processing callbacks and awaits currently running ones."""

        self._task.cancel()

        for cb in self.running:
            if not cb.done():
                cb.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await self._task
            for cb in self.running:
                await cb

        self.running = []

    def add_callback(self, cb, *args, **kwargs):
        """Add a callback to the queue.

        The callback will be called as ``cb(*args, **kwargs).

        """

        self.queue.put_nowait((cb, args, kwargs))

    async def _process_queue(self):
        """Processes new callbacks."""

        while True:

            cb, args, kwargs = await self.queue.get()

            if asyncio.iscoroutinefunction(cb):
                self.running.append(asyncio.create_task(cb(*args, **kwargs)))
            else:
                self.loop.call_soon(functools.partial(cb, *args, **kwargs))

            # Clean already done callbacks
            done_cb = []
            for task in self.running:
                if task.done():
                    done_cb.append(task)

            self.running = [task for task in self.running if task not in done_cb]


def format_value(value):
    """Formats messages in a way that is compatible with the parser.

    Parameters
    ----------
    value
        The data to be formatted.

    Returns
    -------
    formatted_text : `str`
        A string with the escaped text.

    """

    if isinstance(value, str):
        if ' ' in value and not (value.startswith('\'') or value.startswith('"')):
            value = json.dumps(value)
    elif isinstance(value, bool):
        value = 'T' if value else 'F'
    elif isinstance(value, (tuple, list)):
        value = ','.join([format_value(item) for item in value])
    else:
        value = str(value)

    return value


def escape(value):
    """Escapes a text using `json.dumps`."""

    return json.dumps(value)


class CaseInsensitiveDict(collections.OrderedDict):
    """A dictionary that performs case-insensitive operations."""

    def __init__(self, values):

        self._lc = []

        collections.OrderedDict.__init__(self, values)

        self._lc = [key.lower() for key in values]
        assert len(set(self._lc)) == len(self._lc), 'the are duplicated items in the dict.'

    def __get_key__(self, key):
        """Returns the correct value of the key, regardless of its case."""

        try:
            idx = self._lc.index(key.lower())
        except ValueError:
            return key

        return list(self)[idx]

    def __getitem__(self, key):
        return collections.OrderedDict.__getitem__(self, self.__get_key__(key))

    def __setitem__(self, key, value):

        if key.lower() not in self._lc:
            self._lc.append(key.lower())
            collections.OrderedDict.__setitem__(self, key, value)
        else:
            collections.OrderedDict.__setitem__(self, self.__get_key__(key), value)

    def __contains__(self, key):
        return collections.OrderedDict.__contains__(self, self.__get_key__(key))

    def __eq__(self, key):
        return collections.OrderedDict.__eq__(self, self.__get_key__(key))


def cli_coro(f):
    """Decorator function that allows defining coroutines with click."""

    f = asyncio.coroutine(f)

    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(f(*args, **kwargs))

    return functools.update_wrapper(wrapper, f)


async def as_complete_failer(aws, on_fail_callback=None, **kwargs):
    """Similar to `~asyncio.as_complete` but cancels all the tasks
    if any of them returns `False`.

    Parameters
    ----------
    aws : list
        A list of awaitable objects. If not a list, it will be wrapped in one.
    on_fail_callback
        A function or coroutine to call if any of the tasks failed.
    kwargs : dict
        A dictionary of keywords to be passed to `~asyncio.as_complete`.

    Returns
    -------
    result_tuple : tuple
        A tuple in which the first element is `True` if all the tasks
        completed, `False` if any of them failed and the rest were cancelled.
        If `False`, the second element is `None` if no exceptions were caught
        during the execution of the tasks, otherwise it contains the error
        message. If `True`, the second element is always `None`.

    """

    if not isinstance(aws, (list, tuple)):
        aws = [aws]

    loop = kwargs.get('loop', asyncio.get_event_loop())

    tasks = [loop.create_task(aw) for aw in aws]

    failed = False
    error_message = None
    for next_completed in asyncio.as_completed(tasks, **kwargs):
        try:
            result = await next_completed
        except Exception as ee:
            error_message = str(ee)
            result = False

        if not result:
            failed = True
            break

    if failed:

        # Cancel tasks
        [task.cancel() for task in tasks]

        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*[task for task in tasks])

        if on_fail_callback:
            if asyncio.iscoroutinefunction(on_fail_callback):
                await on_fail_callback()
            else:
                on_fail_callback()

        return (False, error_message)

    return (True, None)


def log_reply(log, message_code, message, use_message_code=False):
    """Logs an actor message with the correct code."""

    code_dict = {'f': logging.ERROR,
                 'w': logging.WARNING,
                 'i': logging.INFO,
                 ':': logging.INFO,
                 'd': logging.DEBUG}

    if use_message_code:
        log.log(code_dict[message_code], message)
    else:
        # Sets the REPLY log level
        log_level_no = REPLY
        if log_level_no in logging._levelToName:
            log_level = log_level_no
        else:
            log_level = logging.DEBUG

        log.log(log_level, message)
