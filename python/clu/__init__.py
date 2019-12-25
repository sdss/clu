#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-04-22
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

# flake8: noqa

import pkg_resources

from .actor import *
from .base import CommandStatus, as_complete_failer, escape, format_value
from .client import AMQPClient
from .command import *
from .device import *
from .exceptions import *
from .legacy import LegacyActor
from .parser import command_parser


try:
    __version__ = pkg_resources.get_distribution('sdss-clu').version
except pkg_resources.DistributionNotFound:
    __version__ = 'dev'

NAME = 'clu'
