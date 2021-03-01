import asyncio

import click

from clu import AMQPActor, command_parser


@command_parser.command()
@click.argument("EXPTIME", type=float)
async def expose(command, exptime):
    """Exposes the camera."""

    command.info(text="Starting the exposure.")

    # Here we talk to the camera to initiate the exposure.

    # Use command to access the actor and command the shutter
    shutter_cmd = await command.actor.send_command("shutter_actor", "open")

    await shutter_cmd  # Block until the command is done (finished or failed)
    if shutter_cmd.status.did_fail:
        # Do cleanup
        return command.fail(text="Shutter failed to open")

    # Report status of the shutter
    replies = shutter_cmd.replies
    shutter_status = replies[-1].body["shutter"]
    if shutter_status not in ["open", "closed"]:
        return command.fail(text=f"Unknown shutter status {shutter_status!r}.")

    command.info(f"Shutter is now {shutter_status!r}.")

    # Sleep until the exposure is complete.
    await asyncio.sleep(exptime)

    # Close the shutter. Note the double await.
    await (await command.actor.send_command("shutter_actor", "close"))

    # Finish exposure, read buffer, etc.

    return command.finish(text="Exposure done!")


class CameraActor(AMQPActor):
    def __init__(self):
        super().__init__(
            name="camera_actor",
            user="guest",
            password="guest",
            host="localhost",
            port=5672,
            version="0.1.0",
        )


async def run_actor():
    actor = await CameraActor().start()
    await actor.run_forever()


asyncio.run(run_actor())
