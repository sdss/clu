# !usr/bin/env python
# -*- coding: utf-8 -*-
#
# Licensed under a 3-clause BSD license.
#
# @Author: Brian Cherinka
# @Date:   2017-12-05 12:01:21
# @Last modified by:   Brian Cherinka
# @Last Modified time: 2017-12-05 12:19:32

from __future__ import print_function, division, absolute_import


class AsyncioactorError(Exception):
    """A custom core Asyncioactor exception"""

    def __init__(self, message=None):

        message = 'There has been an error' \
            if not message else message

        super(AsyncioactorError, self).__init__(message)


class AsyncioactorNotImplemented(AsyncioactorError):
    """A custom exception for not yet implemented features."""

    def __init__(self, message=None):

        message = 'This feature is not implemented yet.' \
            if not message else message

        super(AsyncioactorNotImplemented, self).__init__(message)


class AsyncioactorApiError(AsyncioactorError):
    """A custom exception for API errors"""

    def __init__(self, message=None):
        if not message:
            message = 'Error with Http Response from Asyncioactor API'
        else:
            message = 'Http response error from Asyncioactor API. {0}'.format(message)

        super(AsyncioactorAPIError, self).__init__(message)


class AsyncioactorApiAuthError(AsyncioactorAPIError):
    """A custom exception for API authentication errors"""
    pass


class AsyncioactorMissingDependency(AsyncioactorError):
    """A custom exception for missing dependencies."""
    pass


class AsyncioactorWarning(Warning):
    """Base warning for Asyncioactor."""
    pass


class AsyncioactorUserWarning(UserWarning, AsyncioactorWarning):
    """The primary warning class."""
    pass


class AsyncioactorSkippedTestWarning(AsyncioactorUserWarning):
    """A warning for when a test is skipped."""
    pass


class AsyncioactorDeprecationWarning(AsyncioactorUserWarning):
    """A warning for deprecated features."""
    pass

