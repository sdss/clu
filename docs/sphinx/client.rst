
.. _clients:

Using clients
=============

Clients allow to establish a connection to the central passing system and interact with the actor pool programmatically. As a reminder, all actors are also clients.

Clients subclass from the `.BaseClient` class. Once a connection has been established, clients can send commands, await for them, and receive replies exactly in the same way as described in :ref:`actor-communication`. A minimal example of an `.AMQPClient` would be ::

    import asyncio
    from clu.client import AMQPClient

    async def main():

        client = AMQPClient(name="amqp_client", port=5672)
        await client.start()

        cmd = await client.send_command('archon', 'lvm status')
        if cmd.status.did_fail:
            raise RuntimeError('The command failed.')

        print('Command archon lvm status finished.')

    if __name__ == "__main__":
        asyncio.run(main())

For additional information about how to grab replies from the command, set callbacks, etc., refer to :ref:`actor-communication`.

Tron client
-----------

`.TronConnection` provides a client to the Tron message passign system. It works similarly to the `.AMQPClient` with the exception of the commands that need to be passed to initialise it. For example ::

    from clu.legacy.tron import TronConnection

    tron = TronConnection('program.user', 'localhost', port=6093)
    await tron.start()

Note that `.TronConnection.send_command` has some specific additional parameters, although most of them are not relevant for normal use.
