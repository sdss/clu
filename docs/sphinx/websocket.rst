Websocket servers
=================

A frequent use-case for CLU is wanting to connect a webapp to the actor system. While it's possible to write a webapp with a server-side component (e.g., using `Next.js <https://nextjs.org>`__) that connects to the RabbitMQ exchange, that still requires a significant re-developement.

CLU provides a simple websocket pass-through server that runs on the server side and provides access to websocket clients. Since websocket clients are allowed on client-side webapps, there is no need for a server-side webapp component and the only requirement is that the websocket server port must be exposed on the server.

The simplest example of a websocket server is ::

    import asyncio
    from clu.websocket import WebsocketServer

    async def main():
        ws = await WebsocketServer().start()

        # Run forever
        await asyncio.Future()

    if __name__ == "__main__":
        asyncio.run(main())

This will create a websocket server on port 9876. A client connected to it will receive all messages originating on the AMQP exchange, for example ::

    {
        "headers": {"command_id": "uoiu-7987", "commander_id": "amqp-client-b5821fc64fc9.lvmecp", "internal": false, "message_code": "d", "sender": "lvmecp"},
        "exchange": "sdss_exchange",
        "message_id": "2fd4ae6ca62b462585b873ba35ba2d18",
        "routing_key": "reply.amqp-client-b5821fc64fc9.lvmecp",
        "timestamp": "2023-05-25T19:25:05",
        "body": {"dome_status": "0x10", "dome_status_labels": "POSITION_UNKNOWN"}
    }

The websocket client can send a command to the actor system by writing a JSON-valid string with the format ::

    {
        "consumer": "actor",
        "command_string": "ping",
        "command_id": "id-1234",
    }

where ``consumer`` is the actor to which we are sending the command, ``command_string`` is the command to execute, and ``command_id`` is a string identifier for the command. ``command_id`` is not required (if not provided an auto-generated one will be assigned) but strongly required to be able to track the completion of the command. Note that tracking the command replies and status is left to the websocket user.

The CLI provides a simple way to start a websocket server by running ``clu websocket``. Check ``clu websocket --help`` for options.

.. warning::
    Using the `.WebsocketServer` or ``clu websocket`` requires having the `websockets <https://websockets.readthedocs.io/en/stable/index.html>`__ library available, which is installed with the ``websocket`` extra: ``pip install sdss-clu[websocket]``.

API
---

.. automodule:: clu.websocket
    :members: WebsocketServer
    :noindex:
