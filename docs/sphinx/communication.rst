
.. _actor-communication:

Actor communication
===================

While isolated actors are useful in many cases, a message passing system excels at allowing communication with other actors. As we have seen in :ref:`keyword-model`, an actor can "subscribe" to the model of a different actor and even register callbacks to perform actions when the model changes.

This is often not enough. Frequently we don't want to wait until a given keyword is output by another actor, instead wishing to trigger the update ourselves, or we want the actor to perform a certain task. An example of this may be as follows: imagine that we have two actors; ``CameraActor`` is responsible for exposing a given camera and reading its buffer, while ``ShutterActor`` handles the external shutter of the camera. To take an exposure, ``CameraActor`` needs to start expsing and then immediately tell ``ShutterActor`` to open the shutter; at the end of the exposure we'll need to command ``ShutterActor`` again to close the shutter.

To achieve this we take advantage of the fact that all actors are also clients that can command other actors via the `~.BaseClient.send_command` method. Let's write a quick version of ``ShutterActor`` ::

    @command_parser.command()
    async def open(command):
        """Open the shutter."""

        command.info(text='Opening the shutter!')
        # Here we would implement the actual communication with the shutter hardware.
        command.finish(shutter='open')

        return

    @command_parser.command()
    async def close(command):
        """Close the shutter."""

        command.info(text='Closing the shutter!')
        ...
        command.finish(shutter='closed')

        return

    class ShutterActor(AMQPActor):
        name = 'shutter_actor'
        ...  # Skipped for brevity.

Now let's see how a ``CameraActor`` would talk to ``ShutterActor`` ::

    @command_parser.command()
    @click.argument('EXPTIME', type=float)
    async def expose(command, exptime):
        """Exposes the camera."""

        command.info(text='Starting the exposure.')

        ... # Here we talk to the camera to initiate the exposure.

        # Use command to access the actor and command the shutter
        shutter_cmd = await command.actor.send_command('shutter_actor', 'open')

        await shutter_cmd  # Block until the command is done (finished or failed)
        if shutter_cmd.status.did_fail:
            ...  # Do cleanup
            return command.fail(text="Shutter failed to open")

        await asyncio.sleep(exptime)

        # Close the shutter. Note the double await.
        await (await command.actor.send_command('shutter_actor', 'close'))

        ...  # Finish exposure, read buffer, etc.

        return command.finish(text='Exposure done!')

    class CameraActor(AMQPActor):
        ...  # Skipped for brevity.

We called ``open`` and ``close`` in ``ShutterActor`` using `~.BaseClient.send_command`. In this case we assume that ``send_command`` is implemented such that it receives the name of the actor to command as the first argument, and the command string as the second one. This is standard but different clients (and thus the actors that derive from them) may have slightly different implementations. For example, see the details for `.AMQPClient.send_command` and `.TronConnection.send_command`. Note that for `.LegacyActor` we need to use `~.TronConnection.send_command` from the `.TronConnection`. ``send_command`` returns a `.Command` object that can be awaited until it completes.

Finally, this same approach can be used not only for an actor to command a different actor, but also for a client to command an actor (and in fact `~.BaseClient.send_command` is implemented as an abstract class of `.BaseClient`)

An extended version of this :ref:`example <communicating-example>` can be found in the :ref:`examples` section.

Accessing replies
-----------------

When we command ``ShutterActor`` to open the shutter, it completes the command and outputs the keyword ``shutter="open"``. In some cases we may want to not only know that the command has finished, but also access the replies that command output. One way to do this is to subscribe the commanding actor to the datamodel of the commanded actor and check the model after the command finishes, or to :ref:`register callbacks <keyword-model-callbacks>` against the model of the commanded actor.

Another way is to access the command `~.BaseCommand.replies` attribute. ``replies`` lists all the replies the remote actor has output as a response to the command. The format of the replies varies depending on the actor. For `.AMQPClient` and `.AMQPActor`, it consists of a list of `.AMQPReply` objects in the order in which they were output. We can use this to retrieve the value of the ``shutter`` keyword after the command finishes ::

    shutter_cmd = await command.actor.send_command("shutter_actor", "open")
    await shutter_cmd

    # Report status of the shutter
    replies = shutter_cmd.replies

    # Use replies[-1] because we know the shutter keyword is output
    # just as the command finishes.
    shutter_status = replies[-1].body["shutter"]
    if shutter_status not in ["open", "closed"]:
        return command.fail(text=f"Unknown shutter status {shutter_status!r}.")

    command.info(f"Shutter is now {shutter_status!r}.")

For `.TronConnection`, the returned replies are of the old ``opscore`` type ``Reply``, which is not well documented. In general, it's possible to access the keywords via ``reply.keywords``. For more details, check the code directly `here <https://github.com/sdss/clu/blob/5c8bcfa5d4cdfaaac09ffb259d236e4fd52e1ace/python/clu/legacy/types/messages.py#L436>`__.
