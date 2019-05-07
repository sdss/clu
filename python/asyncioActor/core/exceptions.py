#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Licensed under a 3-clause BSD license.
#
# @Author: Brian Cherinka
# @Date:   2017-12-05 12:01:21
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last Modified time: 2017-12-05 12:19:32

from __future__ import print_function, division, absolute_import


class CluError(Exception):
    """A custom core Clu exception"""

    def __init__(self, message=None):

        message = 'There has been an error' \
            if not message else message

        super(CluError, self).__init__(message)


class CluNotImplemented(CluError):
    """A custom exception for not yet implemented features."""

    def __init__(self, message=None):

        message = 'This feature is not implemented yet.' if not message else message

        super(CluNotImplemented, self).__init__(message)


class CommandError(CluError):
    """An error raised when a `Command` fails."""

    pass


class CluBaseWarning(Warning):
    """Base warning for Clu."""
    pass


class CluWarning(UserWarning, CluBaseWarning):
    """The primary warning class."""
    pass

class CluDeprecationWarning(CluBaseWarning):
    """A warning for deprecated features."""
    pass
