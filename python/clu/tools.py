#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-09-07
# @Filename: tools.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import collections
import contextlib
import enum
import functools
import json
import logging
import re


REPLY = 5  # REPLY logging level
WARNING_REGEX = r'^.*?\s*?(\w*?Warning): (.*)'


__ALL__ = ['CommandStatus', 'StatusMixIn', 'format_value', 'CallbackMixIn',
           'CaseInsensitiveDict', 'cli_coro', 'value', 'as_complete_failer',
           'log_reply', 'ActorHandler']


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
    def did_succeed(self):
        """Command finished with DONE status."""

        return self == self.DONE

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

        self.watcher = asyncio.Event()

        while self.status != value:
            await self.watcher.wait()
            if self.watcher is not None:
                self.watcher.clear()

        self.watcher = None


class CallbackMixIn(object):
    """A mixin for executing callbacks.

    Parameters
    ----------
    callbacks : list
        A list of functions or coroutines to be called.

    """

    def __init__(self, callbacks=[], loop=None):

        self._callbacks = []
        for cb in callbacks:
            self.register_callback(cb)

        self._running = []  # Running callbacks

        self.loop = loop or asyncio.get_event_loop()

    async def stop_callbacks(self):
        """Cancels any running callback task."""

        for cb in self._running:
            if not cb.done():
                cb.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            for cb in self._running:
                await cb

        self._running = []

    def register_callback(self, callback_func):
        """Adds a callback function or coroutine function."""

        assert callable(callback_func), 'callback_func must be a callable.'
        self._callbacks.append(callback_func)

    def remove_callback(self, callback_func):
        """Removes a callback function."""

        assert callback_func in self._callbacks, \
            'callback_func is not in the list of callbacks.'
        self._callbacks.remove(callback_func)

    def notify(self, *args):
        """Calls the callback functions with some arguments.

        Coroutine callbacks are scheduled as a task. Synchronous callbacks
        are scheduled with ``call_soon``.

        """

        if self._callbacks is None:
            return

        for cb in self._callbacks:
            if asyncio.iscoroutinefunction(cb):
                task = self.loop.create_task(cb(*args))
                self._running.append(task)
                # Auto-dispose of the task once it completes
                task.add_done_callback(self._running.remove)
            else:
                task = self.loop.call_soon(cb, *args)


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
                 'e': logging.ERROR,
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


class ActorHandler(logging.Handler):
    """A handler that outputs log messages as actor keywords.

    Parameters
    ----------
    actor
        The actor instance.
    level : int
        The level above which records will be output in the actor.
    keyword : str
        The keyword around which the messages will be output.
    code_mapping : dict
        A mapping of logging levels to actor codes. The values provided
        override the default mapping. For example, to make input log messages
        with info level be output as debug,
        ``code_mapping={logging.INFO: 'd'}``.
    filter_warnings : list
        A list of warning classes that will be issued to the actor. Subclasses
        of the filter warning are accepted, any other warnings will be ignored.

    """

    def __init__(self, actor, level=logging.ERROR, keyword='text',
                 code_mapping=None, filter_warnings=None):

        self.actor = actor
        self.keyword = keyword

        self.code_mapping = {logging.DEBUG: 'd',
                             logging.INFO: 'i',
                             logging.WARNING: 'w',
                             logging.ERROR: 'f'}

        if code_mapping:
            self.code_mapping.update(code_mapping)

        self.filter_warnings = filter_warnings

        super().__init__(level=level)

    def emit(self, record):
        """Emits the record."""

        message = record.getMessage()
        message_lines = message.splitlines()

        if record.exc_info:
            message_lines.append(f'{record.exc_info[0].__name__}: {record.exc_info[1]}')

        if record.levelno <= logging.DEBUG:
            code = self.code_mapping[logging.DEBUG]
        elif record.levelno <= logging.INFO:
            code = self.code_mapping[logging.INFO]
        elif record.levelno <= logging.WARNING:
            code = self.code_mapping[logging.WARNING]
            warning_category_groups = re.match(WARNING_REGEX, message)
            if warning_category_groups is not None:
                message_lines = self._filter_warning(warning_category_groups)
        elif record.levelno >= logging.ERROR:
            code = self.code_mapping[logging.ERROR]
        else:
            code = 'w'

        for line in message_lines:
            result = self.actor.write(code, message={self.keyword: line})

            if asyncio.iscoroutine(result):
                asyncio.create_task(result)

    def _filter_warning(self, warning_category_groups):

        warning_category, warning_text = warning_category_groups.groups()
        message_lines = [f'{warning_text} ({warning_category})']

        try:
            warning_class = eval(warning_category)
            if self.filter_warnings:
                for warning_filter in self.filter_warnings:
                    if isinstance(warning_class, warning_filter):
                        return message_lines
            return []
        except NameError:
            return message_lines
