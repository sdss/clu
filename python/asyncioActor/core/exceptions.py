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


class AsyncioActorError(Exception):
    """A custom core AsyncioActor exception"""

    def __init__(self, message=None):

        message = 'There has been an error' \
            if not message else message

        super(AsyncioActorError, self).__init__(message)


class AsyncioActorNotImplemented(AsyncioActorError):
    """A custom exception for not yet implemented features."""

    def __init__(self, message=None):

        message = 'This feature is not implemented yet.' \
            if not message else message

        super(AsyncioActorNotImplemented, self).__init__(message)


class CommandError(AsyncioActorError):
    """An error raised when a `Command` fails."""

    pass


class AsyncioActorAPIError(AsyncioActorError):
    """A custom exception for API errors"""

    def __init__(self, message=None):
        if not message:
            message = 'Error with Http Response from AsyncioActor API'
        else:
            message = 'Http response error from AsyncioActor API. {0}'.format(message)

        super(AsyncioActorAPIError, self).__init__(message)


class AsyncioActorApiAuthError(AsyncioActorAPIError):
    """A custom exception for API authentication errors"""
    pass


class AsyncioActorMissingDependency(AsyncioActorError):
    """A custom exception for missing dependencies."""
    pass


class AsyncioActorBaseWarning(Warning):
    """Base warning for AsyncioActor."""
    pass


class AsyncioActorWarning(UserWarning, AsyncioActorBaseWarning):
    """The primary warning class."""
    pass


class AsyncioActorSkippedTestWarning(AsyncioActorBaseWarning):
    """A warning for when a test is skipped."""
    pass


class AsyncioActorDeprecationWarning(AsyncioActorBaseWarning):
    """A warning for deprecated features."""
    pass
