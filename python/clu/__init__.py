#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-04-22
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

# flake8: noqa

import logging

from sdsstools import get_package_version

from .actor import *
from .base import *
from .client import *
from .command import *
from .device import *
from .exceptions import *
from .legacy import LegacyActor
from .parser import ClickParser, command_parser
from .tools import (
    REPLY,
    ActorHandler,
    CommandStatus,
    as_complete_failer,
    escape,
    format_value,
)

# Add REPLY level to logging
logging.addLevelName(REPLY, "REPLY")
logging.Logger.REPLY = lambda self, message, *args, **kws: self._log(  # type: ignore
    REPLY, message, *args, **kws
)


NAME = "sdss-clu"
__version__ = get_package_version(__file__, "sdss-clu", pep_440=True)
