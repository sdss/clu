#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-06
# @Filename: parser.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import re
import shlex
import time

from typing import Any, List, TypeVar

import click
from click.decorators import group, pass_obj

from sdsstools.logger import SDSSLogger

from clu.command import Command

from .. import actor


__all__ = [
    "CluCommand",
    "CluGroup",
    "command_parser",
    "ClickParser",
    "timeout",
    "unique",
    "get_running_tasks",
]


def coroutine(fn):
    """Create a coroutine. Avoids deprecation of asyncio.coroutine in 3.10."""

    if inspect.iscoroutinefunction(fn):
        return fn

    @functools.wraps(fn)
    async def _wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return _wrapper


class CluCommand(click.Command):
    """Override :py:class:`click.Command` to pass the actor and command."""

    def __init__(self, *args, context_settings=None, **kwargs):

        # Unless told otherwise, set ignore_unknown_options=True to prevent
        # negative numbers to be considered as options. See #40.
        if context_settings is None or "ignore_unknown_options" not in context_settings:
            context_settings = context_settings or {}
            context_settings["ignore_unknown_options"] = True

        self.cancellable = kwargs.pop("cancellable", False)

        if self.cancellable is True:
            kwargs["params"].append(
                click.Option(
                    ["--stop"],
                    is_flag=True,
                    help="Stops the execution of the command.",
                )
            )

        self.full_path = None

        super().__init__(
            *args,
            context_settings=context_settings,
            **kwargs,
        )

    def done_callback(self, task, exception_handler=None):
        """Checks if the command task has been successfully done."""

        ctx = task.ctx

        command = ctx.obj["parser_args"][0]

        if exception_handler and task.exception():
            exception_handler(command, task.exception())

    async def _schedule_callback(self, ctx, timeout=None):
        """Schedules the callback as a task with a timeout."""

        parser_args = ctx.obj.get("parser_args", [])
        command = parser_args[0] if len(parser_args) > 0 else None

        callback_task = asyncio.create_task(
            ctx.invoke(self.callback, *parser_args, **ctx.params)
        )

        try:
            await asyncio.wait_for(callback_task, timeout=timeout)
        except asyncio.TimeoutError:
            if command:
                command.set_status(
                    command.status.TIMEDOUT,
                    f"Command timed out after {timeout} seconds.",
                )
            return False
        except asyncio.CancelledError:
            if command:
                command.set_status(
                    command.status.CANCELLED,
                    "This command has been cancelled.",
                )
            return False

        return True

    def invoke(self, ctx):
        """As :py:class:`click.Command.invoke` but passes the actor and command."""

        if self.callback is not None:

            with ctx:

                loop = asyncio.get_event_loop()

                self.full_path = ctx.command_path.replace(" ", "_")

                if self.cancellable and self._cancel_command(ctx):
                    return

                # Makes sure the callback is a coroutine
                if not asyncio.iscoroutinefunction(self.callback):
                    self.callback = coroutine(self.callback)

                # Check to see if there is a timeout value in the callback.
                # If so, schedules a task to be cancelled after timeout.
                timeout = getattr(self.callback, "timeout", None)

                log = ctx.obj.pop("log", None)

                # Defines the done callback function.
                exception_handler = ctx.obj.pop("exception_handler", None)
                done_callback = functools.partial(
                    self.done_callback, exception_handler=exception_handler
                )

                # Launches callback scheduler and adds the done callback
                ctx.task = loop.create_task(
                    self._schedule_callback(ctx, timeout=timeout)
                )

                ctx.task._command_name = self.full_path  # type: ignore For PY<38
                ctx.task._date = time.time()  # type: ignore

                ctx.task.add_done_callback(done_callback)

                # Add some attributes to the task because it's
                # what will be passed to done_callback
                ctx.task.ctx = ctx  # type: ignore
                ctx.task.log = log  # type: ignore

            return ctx

    def _cancel_command(self, ctx):
        """Stops a cancellable command."""

        parser_args = ctx.obj.get("parser_args", [])
        if len(parser_args) == 0:  # The Command should always be there.
            return

        command = parser_args[0]
        stopping = "stop" in ctx.params and ctx.params.pop("stop") is True

        running_tasks = get_running_tasks(self.full_path)

        if not stopping:
            if running_tasks is not None:
                command.fail(f"Another command {self.full_path} is already running.")
                return True
            else:
                return False

        if running_tasks is None:
            command.fail(error=f"Cannot find running command {self.full_path}.")
            return False
        else:
            # Cancel the oldest running one (although there should only be one)
            running_tasks[0].cancel()

            command.finish(text="Command has been scheduled for cancellation.")
            return True


class CluGroup(click.Group):
    """Override :py:class:`click.Group`.

    Makes all child commands instances of `.CluCommand`.

    """

    def command(self, *args, **kwargs):
        """Override :py:class:`click.Group` to use `.CluCommand` by default."""

        if "cls" in kwargs:
            pass
        else:
            kwargs["cls"] = CluCommand

        def decorator(f):
            cmd = click.decorators.command(*args, **kwargs)(f)
            self.add_command(cmd)
            return cmd

        return decorator

    def parse_args(self, ctx, args):  # pragma: no cover

        # Copy this method so that we can turn off the printing of the
        # usage before ctx.exit()
        if not args and self.no_args_is_help and not ctx.resilient_parsing:
            ctx.exit()

        rest = click.Command.parse_args(self, ctx, args)
        if self.chain:
            ctx.protected_args = rest
            ctx.args = []
        elif rest:
            ctx.protected_args, ctx.args = rest[:1], rest[1:]

        return ctx.args

    def group(self, *args, **kwargs):
        """Creates a new group inheriting from this class."""

        if "cls" not in kwargs:
            kwargs["cls"] = self.__class__

        def decorator(f):
            assert not asyncio.iscoroutinefunction(f), "groups cannot be coroutines."
            cmd = group(*args, **kwargs)(f)
            self.add_command(cmd)
            return cmd

        return decorator


async def coro_helper(f, *args, **kwargs):
    if asyncio.iscoroutinefunction(f):
        return await f(*args, **kwargs)
    else:
        return f(*args, **kwargs)


def timeout(seconds: float):
    """A decorator to timeout the command after a number of ``seconds``."""

    def decorator(f):

        # This is a bit of a hack but we cannot access the context here so
        # we add the timeout directly to the callback function.
        f.timeout = seconds

        @functools.wraps(f)
        async def wrapper(*args, **kwargs):
            return await coro_helper(f, *args, **kwargs)

        return functools.update_wrapper(wrapper, f)

    return decorator


def get_running_tasks(cmd_name) -> list[asyncio.Task] | None:
    """Returns the list of tasks for a given command name, sorted by start date."""

    all_tasks = [(t, getattr(t, "_command_name", None)) for t in asyncio.all_tasks()]

    # Sort by date but exclude potential tasks without our added _date
    matching = [t[0] for t in all_tasks if t[1] == cmd_name]
    matching_dated = [(m, getattr(m, "_date")) for m in matching if hasattr(m, "_date")]

    if len(matching) == 0:
        return None

    return [m[0] for m in sorted(matching_dated, key=lambda x: x[1])]


def unique():
    """Allow the execution of only one of these commands at a time."""

    def decorator(f):
        @functools.wraps(f)
        async def new_func(command, *args, **kwargs):

            ctx = click.get_current_context()

            subcmd = ctx.invoked_subcommand or ""
            name = (ctx.command_path + " " + subcmd).replace(" ", "_")

            tasks = get_running_tasks(name)

            # Fails if there are two tasks with the same name, the current one and
            # an already running one.
            if tasks is not None and len(tasks) > 1:
                return command.fail(
                    error=f"Another command with name {name} is already running."
                )

            return await f(command, *args, **kwargs)

        return functools.update_wrapper(new_func, f)

    return decorator


def pass_args():
    """Thing wrapper around pass_obj to pass the command and parser_args."""

    def decorator(f):
        @functools.wraps(f)
        @pass_obj
        def new_func(obj, *args, **kwargs):
            return f(*obj["parser_args"], *args, **kwargs)

        return functools.update_wrapper(new_func, f)

    return decorator


@click.group(cls=CluGroup)
def command_parser(*args):
    pass


@command_parser.command()
def ping(*args):
    """Pings the actor."""

    command = args[0]
    command.set_status(command.status.DONE, "Pong.")

    return


@command_parser.command()
def version(*args):
    """Reports the version."""

    command = args[0]
    command.set_status(command.status.DONE, version=command.actor.version)

    return


@command_parser.command(cls=CluCommand, name="get_schema")
def get_schema(*args):
    """Returns the schema of the actor as a JSON schema."""

    command = args[0]

    if command.actor.model is None:
        return command.fail(error="The actor does not know its own schema.")

    return command.finish(schema=json.dumps(command.actor.model.schema))


@command_parser.command(name="help")
@click.argument("PARSER-COMMAND", type=str, required=False)
@click.pass_context
def help_(ctx, *args, parser_command):
    """Shows the help."""

    command = args[0]

    # The parser_command arrives wrapped in quotes to make sure is a single
    # value. Strip it and unpack it in as many groups and commands as needed.
    parser_command = parser_command.strip('"').split()

    help_lines = ""
    command_name = args[0].actor.name  # Actor name

    # Gets the help lines for the command group or for a specific command.
    if len(parser_command) > 0:

        ctx_commands = ctx.command.commands

        for ii in range(len(parser_command)):
            ctx_command_name = parser_command[ii]
            command_name += f" {ctx_command_name}"
            if ctx_command_name not in ctx_commands:
                return command.fail(error=f"command {ctx_command_name} not found.")
            ctx_command = ctx_commands[ctx_command_name]
            if ii == len(parser_command) - 1:
                # This is the last element in the command list
                # so we want to actually output this help lines.
                help_lines = ctx_command.get_help(ctx)
            else:
                ctx_commands = ctx_command.commands

    else:

        help_lines: str = ctx.get_help()

    message = []
    for line in help_lines.splitlines():
        # Remove the parser name.
        match = re.match(r"^Usage: ([A-Za-z-_]+)", line)
        if match:
            line = line.replace(match.groups()[0], command_name)

        message.append(line)

    if isinstance(command.actor, (actor.AMQPActor, actor.JSONActor)):
        return command.finish(help=message)
    else:
        for line in message:
            command.warning(help=line)
        return command.finish()


@command_parser.command(name="keyword")
@click.argument("KEYWORD", type=str, required=True)
def keyword(command, *args, keyword):
    """Prints human-readable information about a keyword."""

    model = command.actor.model
    if model is None or model.schema is None:
        return command.fail(error="Actor does not have a data model.")

    if keyword not in model.schema["properties"]:
        return command.fail(error=f"Keyword {keyword!r} is not part of the data model.")

    schema = model.schema["properties"][keyword]

    lines = json.dumps(schema, indent=2).splitlines()[1:]
    max_length = max([len(line) for line in lines])

    command.info(text=f"{keyword} = {{".ljust(max_length, " "))
    for line in lines:
        command.info(text=line.replace('"', "").ljust(max_length, " "))

    command.finish()


T = TypeVar("T", bound=Command)


class ClickParser:
    """A command parser that uses Click at its base."""

    #: list: Arguments to be passed to each command in the parser.
    #: Note that the command is always passed first.
    parser_args: List[Any] = []
    parser = command_parser

    #: dict: Parameters to be set in the context object.
    context_obj = {}

    # For type hints
    log: SDSSLogger
    name: str

    def parse_command(self, command: T) -> T:
        """Parses a user command using the Click internals."""

        # This will pass the command as the first argument for each command.
        # If self.parser_args is defined, those arguments will be passed next.
        parser_args = [command]
        parser_args += self.parser_args

        # Empty command. Just finish the command.
        if not command.body:
            command.done()
            return command

        assert command.status
        command.set_status(command.status.RUNNING)

        # If the command contains the --help flag,
        # redirects it to the help command.
        if "--help" in command.body and command.body != "--help":
            command.body = "help " + command.body
            command.body = command.body.replace(" --help", "")

        if command.body != "--help" and not command.body.startswith("help"):
            command_args = shlex.split(command.body)
        elif command.body == "--help":
            command_args = ["help", '""']
        else:
            command_args = ["help", '"{}"'.format(command.body[5:])]

        # We call the command with a custom context to get around
        # the default handling of exceptions in Click. This will force
        # exceptions to be raised instead of redirected to the stdout.
        # See http://click.palletsprojects.com/en/7.x/exceptions/
        obj = {
            "parser_args": parser_args,
            "log": self.log,
            "exception_handler": self._handle_command_exception,
        }
        obj.update(self.context_obj)
        ctx = self.parser.make_context(
            f"{self.name}-command-parser",
            command_args,
            obj=obj,
        )

        # Makes sure this is the global context. This solves problems when
        # the actor have been started from inside an existing context,
        # for example when it's called from a CLI click application.
        click.globals.push_context(ctx)

        try:
            self.parser.invoke(ctx)
        except Exception as exc:
            self._handle_command_exception(command, exc)

        return command

    def _handle_command_exception(self, command, exception):
        """Handles an exception during parsing or execution of a command."""

        try:

            raise exception

        except (click.ClickException) as ee:

            ctx = command.ctx
            message = ""

            # If this is a command that cannot be parsed.
            if not hasattr(ee, "message") and ctx:
                message = f"{ee.__class__.__name__}:\n{ctx.get_help()}"
            else:
                message = f"{ee.__class__.__name__}: {ee.format_message()}"

            if isinstance(command.actor, (actor.AMQPActor, actor.JSONActor)):
                command.warning(help=message.splitlines())
            else:
                lines = message.splitlines()
                for line in lines:
                    command.warning(help=line)

            msg = f"Command {command.body!r} failed."

            if not command.status.is_done:
                command.fail(error=msg)
            else:
                command.write("e", error=msg)

        except (click.exceptions.Exit, click.exceptions.Abort):

            if not command.status.is_done:
                command.fail(error=f"Command {command.body!r} was aborted.")

        except Exception as err:

            msg = (
                f"Command {command.body!r} failed because of an uncaught "
                f"error '{err.__class__.__name__}: {str(err)}'. See "
                f"traceback in the log for more information."
            )

            if command.status.is_done:
                command.write("i", text=msg)
            else:
                command.fail(error=msg)

            log = self.log or command.ctx.obj.get("log", None)
            if log:
                log.exception(f"Command {command.body!r} failed with error:")
