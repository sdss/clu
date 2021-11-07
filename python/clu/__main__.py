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
import uuid

import aio_pika
import click
import prompt_toolkit
import pygments
import pygments.lexers
from prompt_toolkit import print_formatted_text as print
from prompt_toolkit.formatted_text import PygmentsTokens
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import style_from_pygments_cls
from pygments.styles import STYLE_MAP, get_style_by_name

import clu


style_name = "solarized-dark" if "solarized-dark" in STYLE_MAP else "default"
style = style_from_pygments_cls(get_style_by_name(style_name))  # type: ignore


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
    ignore_broadcasts = False

    async def handle_reply(self, message: aio_pika.IncomingMessage):
        """Prints the formatted reply."""

        reply = await super().handle_reply(message)

        if reply is None:
            return

        commander_id = reply.info["headers"].get("commander_id", None)
        if commander_id:
            commander_id = commander_id.split(".")[0]

        routing_key = message.routing_key
        is_broadcast = routing_key == "reply.broadcast" or reply.command_id is None

        if commander_id and commander_id != self.name and not is_broadcast:
            return

        if self.ignore_broadcasts and is_broadcast:
            return

        message_info = reply.info
        headers = message_info["headers"]

        message_code = headers.get("message_code", "")
        sender = headers.get("sender", "")

        message_code_esc = message_code if message_code != ">" else "&gt;"

        message_code_formatted = prompt_toolkit.formatted_text.HTML(
            f'<style font-weight="bold" '
            f'fg="{color_codes[message_code]}">{message_code_esc}</style>'
        )

        body = reply.body

        indent = 4 if self.indent is True else None
        body_tokens = list(
            pygments.lex(
                json.dumps(body, indent=indent),
                lexer=pygments.lexers.JsonLexer(),  # type: ignore
            )
        )

        print_chunks = []

        if self.show_time:
            time = datetime.datetime.utcnow().isoformat().split("T")[1]
            time = time[0:12]  # Milliseconds
            print_chunks.append(
                prompt_toolkit.formatted_text.HTML(f'<style fg="Gray">{time}</style>'),
            )

        if sender:
            print_chunks.append(f"{sender}")

        if message_code:
            print_chunks.append(message_code_formatted)

        if body:
            print_chunks.append(PygmentsTokens(body_tokens))
            print(*print_chunks, style=style, end="")
        else:
            print(*print_chunks)  # Newline


async def shell_client_prompt(
    url=None,
    user=None,
    password=None,
    host=None,
    port=None,
    indent=True,
    show_time=True,
    ignore_broadcasts=False,
):

    # Give each client a unique name to ensure the queues are unique.
    uid = str(uuid.uuid4()).split("-")[0]

    client = await ShellClient(
        f"shell_client_{uid}",
        url=url,
        user=user,
        password=password,
        host=host,
        port=port,
        log=None,
    ).start()

    client.indent = indent
    client.show_time = show_time
    client.ignore_broadcasts = ignore_broadcasts

    history = FileHistory(os.path.expanduser("~/.clu_history"))

    session = prompt_toolkit.PromptSession("", history=history)

    while True:
        with patch_stdout():
            try:
                text = await session.prompt_async("")
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
    "-P",
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
    "-p",
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
    "--ignore-broadcasts",
    "-b",
    is_flag=True,
    default=False,
    help="Only show replies to client commands.",
)
@click.option(
    "--no-time",
    "-t",
    is_flag=True,
    default=False,
    help="Do not show the message time.",
)
def clu_cli(url, user, password, host, port, no_indent, no_time, ignore_broadcasts):
    """Runs the AMQP command line interpreter."""

    shell_task = asyncio.get_event_loop().create_task(
        shell_client_prompt(
            url=url,
            user=user,
            password=password,
            host=host,
            port=port,
            indent=not no_indent,
            show_time=not no_time,
            ignore_broadcasts=ignore_broadcasts,
        )
    )
    asyncio.get_event_loop().run_until_complete(shell_task)


def main():
    clu_cli(obj={})


if __name__ == "__main__":
    main()
