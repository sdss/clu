import asyncio

from clu import AMQPActor, command_parser


@command_parser.command()
async def open(command):
    """Open the shutter."""

    command.info(text="Opening the shutter!")
    # Here we would implement the actual communication
    # with the shutter hardware.
    command.finish(shutter="open")

    return


@command_parser.command()
async def close(command):
    """Close the shutter."""

    command.info(text="Closing the shutter!")
    # Here we would implement the actual communication
    # with the shutter hardware.
    command.finish(shutter="closed")

    return


class ShutterActor(AMQPActor):
    def __init__(self):
        super().__init__(
            name="shutter_actor",
            user="guest",
            password="guest",
            host="localhost",
            port=5672,
            version="0.1.0",
        )


async def run_actor():
    actor = await ShutterActor().start()
    await actor.run_forever()


asyncio.run(run_actor())
