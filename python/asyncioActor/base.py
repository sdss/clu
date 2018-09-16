#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-09-07
# @Filename: base.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2018-09-07 13:03:34


from enum import Flag, auto


__ALL__ = ['StatusFlags', 'CallbackMixIn']


_MSG_CODE_DICT = dict(
    ready='i',
    running='i',
    cancelling='w',
    failing='w',
    cancelled='f',
    failed='f',
    debug='d',
    done=':')

_INV_MSG_CODE_DICT = dict((val, key) for key, val in _MSG_CODE_DICT.items())


class StatusFlags(Flag):

    DONE = auto()
    CANCELLED = auto()
    FAILED = auto()
    READY = auto()
    RUNNING = auto()
    CANCELLING = auto()
    FAILING = auto()

    ACTIVE_STATES = RUNNING | CANCELLING | FAILING
    FAILED_STATES = CANCELLED | FAILED
    FAILING_STATES = CANCELLING | FAILING
    DONE_STATES = DONE | FAILED_STATES
    ALL_STATES = READY | ACTIVE_STATES | DONE_STATES

    @property
    def is_combination(self):
        """Returns True if a flag is a combination."""

        if bin(self).count('1') > 1:
            return True
        return False

    @property
    def msg_code(self):
        """Returns the message code associated to this status."""

        name = self.name.lower()

        return _MSG_CODE_DICT[name]

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

        return self in self.FAILED_STATES


class CallbackMixIn(object):

    _callbacks = []

    def __init__(self, callback=None, call_now=False):

        if callback is not None:
            if isinstance(callback, (tuple, list)):
                for cb in callback:
                    self.add_callback(cb)
            else:
                self.add_callback(callback)

        if call_now:
            self.do_callbacks()

    def add_callback(self, cb):

        assert callable(cb), 'callback is not a callable'
        self._callbacks.append(cb)

    def remove_callback(self, cb):

        if cb not in self._callbacks:
            raise ValueError(f'function {cb} not in the list of callbacks.')

        self._callbacks.remove(cb)

    def do_callbacks(self):

        for cb in self._callbacks:
            cb(self)
