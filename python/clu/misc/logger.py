#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2017-10-11
# @Filename: logger.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import copy
import datetime
import logging
import os
import re
import shutil
import sys
import traceback
import warnings
from logging.handlers import TimedRotatingFileHandler

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import get_lexer_by_name

from .color_print import color_text


__all__ = ['get_logger']


WARNING_REGEX = r'^.*?\s*?(\w*?Warning): (.*)'


# Adds custom log level for actor replies
REPLY = 5
logging.addLevelName(REPLY, 'REPLY')
logging.Logger.REPLY = lambda self, message, *args, **kws: self._log(REPLY, message, *args, **kws)


def get_exception_formatted(tp, value, tb):
    """Adds colours to tracebacks."""

    tbtext = ''.join(traceback.format_exception(tp, value, tb))
    lexer = get_lexer_by_name('pytb', stripall=True)
    formatter = TerminalFormatter()
    return highlight(tbtext, lexer, formatter)


def colored_formatter(record):
    """Prints log messages with colours."""

    colours = {'info': 'blue',
               'debug': 'magenta',
               'warning': 'yellow',
               'critical': 'red',
               'error': 'red'}

    levelname = record.levelname.lower()

    if levelname.lower() in colours:
        levelname_color = colours[levelname]
        header = color_text('[{}]: '.format(levelname.upper()),
                            levelname_color)
    else:
        header = f'[{levelname}]'

    message = record.getMessage()

    if levelname == 'warning':
        warning_category_groups = re.match(WARNING_REGEX, message)
        if warning_category_groups is not None:
            warning_category, warning_text = warning_category_groups.groups()

            warning_category_colour = color_text('({})'.format(warning_category), 'cyan')
            message = '{} {}'.format(color_text(warning_text, ''), warning_category_colour)

    sys.__stdout__.write('{}{}\n'.format(header, message))
    sys.__stdout__.flush()

    if record.exc_info:
        sys.__stdout__.write(get_exception_formatted(*sys.exc_info()))
        sys.__stdout__.flush()

    return


class ActorHandler(logging.Handler):
    """An actor that outputs log messages to an actor.

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

    """

    def __init__(self, actor, level=logging.ERROR, keyword='text',
                 code_mapping=None):

        self.actor = actor
        self.keyword = keyword

        self.code_mapping = {logging.DEBUG: 'd',
                             logging.INFO: 'i',
                             logging.WARNING: 'w',
                             logging.ERROR: 'f'}

        if code_mapping:
            self.code_mapping.update(code_mapping)

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
                warning_category, warning_text = warning_category_groups.groups()
                message_lines = [f'{warning_text} ({warning_category})']
        elif record.levelno >= logging.ERROR:
            code = self.code_mapping[logging.ERROR]
        else:
            code = 'w'

        for line in message_lines:
            self.actor.write(code, message={self.keyword: line})


class SDSSFormatter(logging.Formatter):
    """Custom `Formatter <logging.Formatter>`."""

    base_fmt = '%(asctime)s - %(levelname)s - %(message)s'
    ansi_escape = re.compile(r'\x1b[^m]*m')

    def __init__(self, fmt=base_fmt):
        logging.Formatter.__init__(self, fmt)

    def format(self, record):

        # Copy the record so that any modifications we make do not
        # affect how the record is displayed in other handlers.
        record_cp = copy.copy(record)

        record_cp.msg = self.ansi_escape.sub('', record_cp.msg)

        # The format of a warnings redirected with warnings.captureWarnings
        # has the format <path>: <category>: message\n  <some-other-stuff>.
        # We reorganise that into a cleaner message. For some reason in this
        # case the message is in record.args instead of in record.msg.
        if record_cp.levelno == logging.WARNING and len(record_cp.args) > 0:
            match = re.match(r'^(.*?):\s*?(\w*?Warning): (.*)', record_cp.args[0])
            if match:
                message = '{1} - {2} [{0}]'.format(*match.groups())
                record_cp.args = tuple([message] + list(record_cp.args[1:]))

        return logging.Formatter.format(self, record_cp)


class SDSSLogger(logging.Logger):
    """Custom logging system.

    Parameters
    ----------
    name : str
        The name of the logger.
    log_level : int
        The initial logging level for the console handler.
    capture_warnings : bool
        Whether to capture warnings and redirect them to the log.

    """

    def __init__(self, name):

        super(SDSSLogger, self).__init__(name)

    def init(self, log_level=logging.INFO, capture_warnings=True):

        # Set levels
        self.setLevel(REPLY)

        # Sets the console handler
        self.sh = logging.StreamHandler()
        self.sh.emit = colored_formatter
        self.addHandler(self.sh)
        self.sh.setLevel(log_level)

        # Placeholders for the file handler.
        self.fh = None
        self.log_filename = None

        # Catches exceptions
        sys.excepthook = self._catch_exceptions

        self.warnings_logger = None

        if capture_warnings:
            self.capture_warnings()

    def _catch_exceptions(self, exctype, value, tb):
        """Catches all exceptions and logs them."""

        self.error(get_exception_formatted(exctype, value, tb))

    def capture_warnings(self):
        """Capture warnings.

        When `logging.captureWarnings` is `True`, all the warnings are
        redirected to a logger called ``py.warnings``. We add our handlers
        to the warning logger.

        """

        logging.captureWarnings(True)

        self.warnings_logger = logging.getLogger('py.warnings')

        # Only enable the sh handler if none is attached to the warnings
        # logger yet. Prevents duplicated prints of the warnings.
        for handler in self.warnings_logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                return

        self.warnings_logger.addHandler(self.sh)

    def save_log(self, path):
        shutil.copyfile(self.log_filename, os.path.expanduser(path))

    def start_file_logger(self, log_file_path, log_level=REPLY):
        """Start file logging."""

        log_file_path = os.path.expandvars(os.path.expanduser(log_file_path))
        logdir = os.path.dirname(log_file_path)

        try:

            if not os.path.exists(logdir):
                os.makedirs(logdir)

            if os.path.exists(log_file_path):
                strtime = datetime.datetime.utcnow().strftime('%Y-%m-%d_%H:%M:%S')
                shutil.move(log_file_path, log_file_path + '.' + strtime)

            self.fh = TimedRotatingFileHandler(
                str(log_file_path), when='midnight', utc=True)

            self.fh.suffix = '%Y-%m-%d_%H:%M:%S'

        except (IOError, OSError) as ee:

            warnings.warn('log file {0!r} could not be opened for '
                          'writing: {1}'.format(log_file_path, ee),
                          RuntimeWarning)

        else:

            self.fh.setFormatter(SDSSFormatter())
            self.addHandler(self.fh)
            self.fh.setLevel(log_level)

            if self.warnings_logger:
                self.warnings_logger.addHandler(self.fh)

            self.log_filename = log_file_path

    def asyncio_exception_handler(self, loop, context):
        """Handle an uncaught exception and reports it."""

        exception = context.get('exception', None)
        if exception is None:
            exception_name = 'UnknownException'
        else:
            exception_name = exception.__class__.__name__

        message = context['message'].splitlines()
        for line in message:
            self.error(f'{exception_name}: {line}')

        if exception:
            for line in exception.args:
                self.error(f'{exception_name}: {line}')

    def set_level(self, level):
        """Sets levels for both sh and (if initialised) fh."""

        self.sh.setLevel(level)

        if self.fh:
            self.fh.setLevel(level)


def get_logger(name, **kwargs):
    """Gets a new logger."""

    orig_logger = logging.getLoggerClass()

    logging.setLoggerClass(SDSSLogger)

    log = logging.getLogger(name)
    log.init(**kwargs)

    logging.setLoggerClass(orig_logger)

    return log
