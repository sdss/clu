#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-09-07
# @Filename: tools.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import contextlib
import enum
import functools
import inspect
import json
import logging
import re

from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
)


__all__ = [
    "CommandStatus",
    "StatusMixIn",
    "format_value",
    "CallbackMixIn",
    "CaseInsensitiveDict",
    "cli_coro",
    "as_complete_failer",
    "log_reply",
    "ActorHandler",
]

REPLY = 5  # REPLY logging level
WARNING_REGEX = r"^.*?\s*?(\w*?Warning): (.*)"


class Maskbit(enum.Flag):
    """A maskbit enumeration. Intended for subclassing."""

    @property
    def active_bits(self) -> List[Maskbit]:
        """Returns a list of non-combination flags that match the value."""

        return [
            bit
            for bit in self.__class__  # type: ignore
            if ((bit.value & self.value) and bin(bit.value).count("1") == 1)
        ]


COMMAND_STATUS_TO_CODE: Dict[str, str] = {
    "DONE": ":",
    "CANCELLED": "f",
    "FAILED": "f",
    "TIMEDOUT": "f",
    "READY": "i",
    "RUNNING": ">",
    "CANCELLING": "w",
    "FAILING": "w",
    "DEBUG": "d",
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

        self.code: str | None
        if self.name and self.name.upper() in COMMAND_STATUS_TO_CODE:
            self.code = COMMAND_STATUS_TO_CODE[self.name.upper()]
        else:
            self.code = None

    @property
    def is_combination(self) -> bool:
        """Returns True if a flag is a combination."""

        if bin(self.value).count("1") > 1:
            return True
        return False

    @property
    def did_fail(self) -> bool:
        """Command failed or was cancelled."""

        return self in self.FAILED_STATES

    @property
    def did_succeed(self) -> bool:
        """Command finished with DONE status."""

        return self == self.DONE

    @property
    def is_active(self) -> bool:
        """Command is running, cancelling or failing."""

        return self in self.ACTIVE_STATES

    @property
    def is_done(self) -> bool:
        """Command is done (whether successfully or not)."""

        return self in self.DONE_STATES

    @property
    def is_failing(self) -> bool:
        """Command is being cancelled or is failing."""

        return self in self.FAILING_STATES

    @staticmethod
    def code_to_status(code, default: Optional[CommandStatus] = None) -> CommandStatus:
        """Returns the status associated with a code.

        If the code doesn't have an associated status, returns ``default``.
        ``default`` defaults to `.CommandStatus.RUNNING`.

        """

        statuses = {
            ":": CommandStatus.DONE,
            "f": CommandStatus.FAILED,
            "!": CommandStatus.FAILED,
            ">": CommandStatus.RUNNING,
        }

        return statuses.get(code, default or CommandStatus.RUNNING)


MaskbitType = TypeVar("MaskbitType", bound=Maskbit)


class StatusMixIn(Generic[MaskbitType]):
    """A mixin that provides status tracking with callbacks.

    Provides a status property that executes a list of callbacks when
    the status changes.

    Parameters
    ----------
    maskbit_flags
        A class containing the available statuses as a series of maskbit
        flags. Usually as subclass of `enum.Flag`.
    initial_status
        The initial status.
    callback_func
        The function to call if the status changes. It receives the status.
    call_now
        Whether the callback function should be called when initialising.

    Attributes
    ----------
    callbacks
        A list of the callback functions to call.
    """

    def __init__(
        self,
        maskbit_flags: Type[MaskbitType],
        initial_status: Optional[MaskbitType] = None,
        callback_func: Optional[Callable[[MaskbitType], Any]] = None,
        call_now: bool = False,
    ):

        self.flags = maskbit_flags
        self.callbacks: List[Callable[[MaskbitType], Any]] = []
        self._status: MaskbitType | None = initial_status
        self.watcher: Optional[asyncio.Event] = None

        if callback_func is not None:
            if isinstance(callback_func, (list, tuple)):
                self.callbacks = callback_func
            else:
                self.callbacks.append(callback_func)

        if call_now is True:
            self.do_callbacks()

    def do_callbacks(self):
        """Calls functions in ``callbacks``."""

        assert hasattr(self, "callbacks"), "missing callbacks attribute."

        loop = asyncio.get_event_loop()

        for func in self.callbacks:
            loop.call_soon(func, self.status)

    @property
    def status(self):
        """Returns the status."""

        return self._status

    @status.setter
    def status(self, value):
        """Sets the status."""

        if value != self._status:
            self._status = value
            self.do_callbacks()
            if self.watcher is not None:
                self.watcher.set()

    async def wait_for_status(self, value):
        """Awaits until the status matches ``value``."""

        if self.status == value:
            return

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
    callbacks
        A list of functions or coroutines to be called.
    """

    def __init__(
        self,
        callbacks: List[Callable[[Any], Any]] = [],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):

        self._callbacks = []
        for cb in callbacks:
            self.register_callback(cb)

        self._running = []  # Running callbacks

    async def stop_callbacks(self):
        """Cancels any running callback task."""

        for cb in self._running:
            if not cb.done():
                cb.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            for cb in self._running:
                await cb

        self._running = []

    def register_callback(self, callback_func: Callable[..., Any]):
        """Adds a callback function or coroutine function."""

        assert callable(callback_func), "callback_func must be a callable."
        self._callbacks.append(callback_func)

    def remove_callback(self, callback_func: Callable[..., Any]):
        """Removes a callback function."""

        assert (
            callback_func in self._callbacks
        ), "callback_func is not in the list of callbacks."
        self._callbacks.remove(callback_func)

    def notify(self, *args):
        """Calls the callback functions with some arguments.

        Coroutine callbacks are scheduled as a task. Synchronous callbacks
        are scheduled with ``call_soon``.

        """

        if self._callbacks is None:
            return

        for cb in self._callbacks:
            n_args = len(inspect.getfullargspec(cb).args)
            if asyncio.iscoroutinefunction(cb):
                task = asyncio.create_task(cb(*args[:n_args]))
                self._running.append(task)
                # Auto-dispose of the task once it completes
                task.add_done_callback(self._running.remove)
            else:
                # Check that the loop is running. There is a problem in which
                # self.loop may be set before there is a running loop so we
                # replace it with a properly running loop.
                task = asyncio.get_event_loop().call_soon(cb, *args[:n_args])


def dict_depth(d: dict) -> int:
    """Gets the depth of a dictionary."""
    if isinstance(d, dict):
        return 1 + (max(map(dict_depth, d.values())) if d else 0)
    return 0


def format_value(value: Any) -> str:
    """Formats messages in a way that is compatible with the parser.

    Parameters
    ----------
    value
        The data to be formatted.

    Returns
    -------
    formatted_text
        A string with the escaped text.
    """

    if isinstance(value, str):
        if " " in value and not (value.startswith("'") or value.startswith('"')):
            value = escape(value)
        # for char in ",/:_-":
        #     if char in value:
        #         value = escape(value)
        #         break
    elif isinstance(value, bool):
        value = "T" if value else "F"
    elif isinstance(value, (tuple, list)):
        value = ",".join([format_value(item) for item in value])
    elif isinstance(value, dict):
        if dict_depth(value) > 1:
            raise ValueError("Cannot format a dictionary with depth > 1.")
        value = format_value(list(value.values()))
    else:
        value = str(value)

    return value


def escape(value: Any):
    """Escapes a text using `json.dumps`."""

    return json.dumps(value)


T = TypeVar("T")


class CaseInsensitiveDict(Dict[str, T]):
    """A dictionary that performs case-insensitive operations."""

    def __init__(self, values: Any):

        self._lc = []

        dict.__init__(self, values)

        self._lc = [key.lower() for key in values]
        assert len(set(self._lc)) == len(
            self._lc
        ), "the are duplicated items in the dict."

    def __get_key__(self, key):
        """Returns the correct value of the key, regardless of its case."""

        try:
            idx = self._lc.index(key.lower())
        except ValueError:
            return key

        return list(self)[idx]

    def __getitem__(self, key):
        return dict.__getitem__(self, self.__get_key__(key))

    def __setitem__(self, key, value):

        if key.lower() not in self._lc:
            self._lc.append(key.lower())
            dict.__setitem__(self, key, value)
        else:
            dict.__setitem__(self, self.__get_key__(key), value)

    def __contains__(self, key):
        return dict.__contains__(self, self.__get_key__(key))

    def __eq__(self, key):
        return dict.__eq__(self, self.__get_key__(key))


def cli_coro(f):
    """Decorator function that allows defining coroutines with click."""

    f = asyncio.coroutine(f)

    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(f(*args, **kwargs))

    return functools.update_wrapper(wrapper, f)


async def as_complete_failer(
    aws: List[Coroutine],
    on_fail_callback: Optional[Callable] = None,
    **kwargs,
) -> Tuple[bool, str | None]:
    """Similar to `~asyncio.as_complete` but cancels all the tasks
    if any of them returns `False`.

    Parameters
    ----------
    aws
        A list of awaitable objects. If not a list, it will be wrapped in one.
    on_fail_callback
        A function or coroutine to call if any of the tasks failed.
    kwargs
        A dictionary of keywords to be passed to `~asyncio.as_complete`.

    Returns
    -------
    result_tuple
        A tuple in which the first element is `True` if all the tasks
        completed, `False` if any of them failed and the rest were cancelled.
        If `False`, the second element is `None` if no exceptions were caught
        during the execution of the tasks, otherwise it contains the error
        message. If `True`, the second element is always `None`.
    """

    if not isinstance(aws, (list, tuple)):
        aws = [aws]

    loop = kwargs.get("loop", asyncio.get_event_loop())

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

        with contextlib.suppress(BaseException):
            await asyncio.gather(*[task for task in tasks])

        if on_fail_callback:
            if asyncio.iscoroutinefunction(on_fail_callback):
                await on_fail_callback()
            else:
                on_fail_callback()

        return (False, error_message)

    return (True, None)


def log_reply(
    log: logging.Logger,
    message_code: str,
    message: str,
    use_message_code: bool = False,
):
    """Logs an actor message with the correct code."""

    code_dict = {
        "f": logging.ERROR,
        "e": logging.ERROR,
        "w": logging.WARNING,
        "i": logging.INFO,
        ":": logging.INFO,
        "d": logging.DEBUG,
    }

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


_ActorClass = TypeVar("_ActorClass")


class ActorHandler(logging.Handler):
    """A handler that outputs log messages as actor keywords.

    Parameters
    ----------
    actor
        The actor instance.
    level
        The level above which records will be output in the actor.
    keyword
        The keyword around which the messages will be output.
    code_mapping
        A mapping of logging levels to actor codes. The values provided
        override the default mapping. For example, to make input log messages
        with info level be output as debug,
        ``code_mapping={logging.INFO: 'd'}``.
    filter_warnings
        A list of warning classes that will be issued to the actor. Subclasses
        of the filter warning are accepted, any other warnings will be ignored.
    """

    def __init__(
        self,
        actor,
        level: int = logging.ERROR,
        keyword: str = "text",
        code_mapping: Optional[Dict[int, str]] = None,
        filter_warnings: Optional[List[Type[Warning]]] = None,
    ):

        self.actor = actor
        self.keyword = keyword

        self.code_mapping = {
            logging.DEBUG: "d",
            logging.INFO: "i",
            logging.WARNING: "w",
            logging.ERROR: "f",
        }

        if code_mapping:
            self.code_mapping.update(code_mapping)

        self.filter_warnings = filter_warnings

        super().__init__(level=level)

    def emit(self, record: logging.LogRecord):
        """Emits the record."""

        message = record.getMessage()
        message_lines = message.splitlines()

        if record.exc_info is not None and record.exc_info[0] is not None:
            message_lines.append(f"{record.exc_info[0].__name__}: {record.exc_info[1]}")

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
            code = "w"

        for line in message_lines:
            result = self.actor.write(code, message={self.keyword: line})

            if asyncio.iscoroutine(result):
                asyncio.create_task(result)

    def _filter_warning(self, warning_category_groups):

        warning_category, warning_text = warning_category_groups.groups()
        message_lines = [f"{warning_text} ({warning_category})"]

        try:
            if self.filter_warnings:
                for warning_filter in self.filter_warnings:
                    if warning_category == warning_filter.__name__:
                        return message_lines
            return []
        except NameError:
            return message_lines
