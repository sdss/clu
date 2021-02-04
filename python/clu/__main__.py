#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-20
# @Filename: __main__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import datetime
import json
import os

import click
import prompt_toolkit
import prompt_toolkit.styles
import pygments
import pygments.lexers
import pygments.styles
from prompt_toolkit import print_formatted_text as print
from prompt_toolkit.formatted_text import PygmentsTokens
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

import clu


loop = asyncio.get_event_loop()


style = prompt_toolkit.styles.style_from_pygments_cls(
    pygments.styles.get_style_by_name("solarized-dark")
)


color_codes = {
    ">": "lightblue",
    "i": "lightblue",
    "d": "gray",
    "w": "yellow",
    "e": "LightCoral",
    "f": "red",
    ":": "green",
}


class ShellClient(clu.AMQPClient):
    """A shell client."""

    indent = False
    show_time = True

    async def handle_reply(self, message):
        """Prints the formatted reply."""

        message = await super().handle_reply(message)

        if message is None:
            return

        message_info = message.info
        headers = message_info["headers"]

        message_code = headers.get("message_code", "")
        sender = headers.get("sender", "")

        message_code_esc = message_code if message_code != ">" else "&gt;"

        message_code_formatted = prompt_toolkit.formatted_text.HTML(
            f'<style font-weight="bold" '
            f'fg="{color_codes[message_code]}">{message_code_esc}</style>'
        )

        body = message.body

        indent = 4 if self.indent is True else None
        body_tokens = list(
            pygments.lex(
                json.dumps(body, indent=indent),
                lexer=pygments.lexers.JsonLexer(),  # type: ignore
            )
        )

        if self.show_time:
            time = datetime.datetime.utcnow().isoformat().split("T")[1]
            time = time[0:12]  # Milliseconds
            print(
                prompt_toolkit.formatted_text.HTML(f'<style fg="Gray">{time}</style> '),
                end="",
            )

        if sender:
            print(f"{sender} ", end="")

        if message_code:
            print(message_code_formatted, end="")
            print(" ", end="")

        if body:
            print(PygmentsTokens(body_tokens), end="", style=style)
        else:
            print()  # Newline


async def shell_client_prompt(
    url=None,
    user=None,
    password=None,
    host=None,
    port=None,
    indent=True,
    show_time=True,
):

    client = await ShellClient(
        "shell_client",
        url=url,
        user=user,
        password=password,
        host=host,
        port=port,
        log=None,
    ).start()
    client.indent = indent
    client.show_time = show_time

    history = FileHistory(os.path.expanduser("~/.clu_history"))

    session = prompt_toolkit.PromptSession("", history=history)

    while True:
        try:
            text = await session.prompt_async()
        except KeyboardInterrupt:
            break
        except EOFError:
            break
        else:
            text = text.strip()
            if text.startswith("quit"):
                break
            elif text == "":
                continue
            else:
                chunks = text.split()
                if len(chunks) < 2:
                    print(f"Invalid command {text!r}")
                    continue

                actor = chunks[0]
                command_string = " ".join(chunks[1:])

                await client.send_command(actor, command_string)


@click.command(name="clu")
@click.option("--url", type=str, help="AMQP RFC3986 formatted broker address.")
@click.option(
    "--user",
    "-U",
    type=str,
    show_default=True,
    default="guest",
    help="The AMQP username.",
)
@click.option(
    "--password",
    "-U",
    type=str,
    show_default=True,
    default="guest",
    help="The AMQP password.",
)
@click.option(
    "--host",
    "-H",
    type=str,
    show_default=True,
    default="localhost",
    help="The host running the AMQP server.",
)
@click.option(
    "--port",
    "-P",
    type=int,
    show_default=True,
    default=5672,
    help="The port on which the server is running",
)
@click.option(
    "--no-indent",
    "-n",
    is_flag=True,
    default=False,
    help="Do not indent the output JSONs.",
)
@click.option(
    "--no-time", "-t", is_flag=True, default=False, help="Do not show the message time."
)
def clu_cli(url, user, password, host, port, no_indent, no_time):
    """Runs the AMQP command line interpreter."""

    with patch_stdout():

        shell_task = loop.create_task(
            shell_client_prompt(
                url=url,
                user=user,
                password=password,
                host=host,
                port=port,
                indent=not no_indent,
                show_time=not no_time,
            )
        )
        loop.run_until_complete(shell_task)


def main():
    clu_cli(obj={})


if __name__ == "__main__":
    main()
