#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2017-12-05
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)


__all__ = ['CluError', 'CluNotImplemented', 'CluWarning',
           'CluDeprecationWarning', 'CommandError', 'CommandParserError']


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


class CommandParserError(CluError):
    """An error raised when parsing a command fails."""

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
