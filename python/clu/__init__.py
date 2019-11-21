#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-04-22
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

# flake8: noqa

import os
import warnings


try:
    import pkg_resources
    __version__ = pkg_resources.get_distribution('sdss-clu').version
except (pkg_resources.DistributionNotFound, ImportError):
    try:
        import toml
        poetry_config = toml.load(open(os.path.join(os.path.dirname(__file__),
                                                    '../../pyproject.toml')))
        __version__ = poetry_config['tool']['poetry']['version']
    except Exception:
        warnings.warn('cannot find clu version. Using 0.0.0.', UserWarning)
        __version__ = '0.0.0'


from .actor import *
from .base import CommandStatus, as_complete_failer, escape, format_value
from .client import AMQPClient
from .command import *
from .device import *
from .exceptions import *
from .legacy import LegacyActor
from .parser import command_parser


NAME = 'clu'
