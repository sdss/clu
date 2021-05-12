import asyncio
from functools import wraps

import click
from daemonocle import DaemonCLI

from clu import AMQPActor
from clu.parsers.click import command_parser


def cli_coro(f):
    """Decorator function that allows defining coroutines with click."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(f(*args, **kwargs))

    return wrapper


@command_parser.command()
async def hello(command):
    return command.finish("Hello!")


@click.command(cls=DaemonCLI, daemon_params={"pid_file": "/var/tmp/myactor.pid"})
@cli_coro
async def main():

    actor = AMQPActor("myactor")  # Assuming RabbitMQ runs on localhost
    await actor.start()
    await actor.run_forever()


if __name__ == "__main__":
    main()
