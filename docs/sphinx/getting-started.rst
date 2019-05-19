
.. _getting-started:

Getting started with CLU
========================

Introduction
------------

In this section we provide a quick introduction to CLU. We assume that you are comfortable with asynchronous programming and `asyncio`_. Here we won't dive into the internal details of how messages are routed and the messaging protocol but we make use of standard messaging jargon such as consumer or exchanges. If you are not familiar with those concepts, the `RabbitMQ tutorial <https://www.rabbitmq.com/getstarted.html>`_ is a good starting place.

We'll begin by defining what an *actor* is: and actor is a piece of software that performs a well defined task (control a CCD camera, interface with a database) and is a *server* that receives *commands* and replies with a series of *keywords*. Let's go over each one of those concepts:

- A *server* means that the actor provides a certain functionality for a series of *clients*, which can be users or other actors. In this case, *server* also means that the actor is part of a network and is able to communicate with the clients via a well-defined protocol. We often refer to the actor as a *consumer* and the clients that command it as *commanders* or *producers*.
- A *command* is an instruction that the actor receives to do a specific task. It must comply with a previously defined schema. In general, commands are formed by a *verb*, which indicates the task to perform, and series of mandatory *arguments* and optional *parameters*. Before it can be understood by the actor, a commands needs to be *parsed*.
- In most cases, when an actor carries out a command, it needs to output some information back to commander. This is done via pairs of *keywords* with an associated values. The keywords and values need to conform with a *model* for the given actor.

We will expand on these concepts in following sections.


Running an actor
----------------

A new actor can be created by simply instantiating the `.Actor` class ::

    from clu import Actor
    my_actor = Actor('my_actor', 'guest', 'localhost', version='0.1.0')

This will create the instance but will not start the actor yet. For that you need to ``await`` the coroutine `~.Actor.run` ::

    await my_actor.run()

which will create the connection to RabbitMQ, set up the exchanges and queues, and get the actor ready to receive commands. Note that awaiting `~.Actor.run` does not block the event loop so you will need to run the loop forever. A simple implementation is ::

    import asyncio
    from clu import Actor

    def main(loop):
        # run() returns the actor so we can declare and run the actor more compactly.
        my_actor = await Actor('my_actor', 'guest', 'localhost',
                               version='0.1.0', loop=loop).run()

    loop = asyncio.get_event_loop()
    loop.create_task(main(loop))
    loop.run_forever()

Frequently you will end up subclassing `.Actor`, for example if you want to start a new :ref:`device <devices>`. That's relatively straightforward to do ::

    from clu import Actor, Device

    class MyActor(Actor):

        def __init__(self, *args, device_host, device_port, **kwargs):

            super().__init__(*args, **kwargs)

            self.device = Device(device_host, device_port,
                                 callback=self.process_device)

        async def run():

            await self.device.start()
            await super().run()

        async def process_device(self, line):

            # Here we do something with the line received
            # from the device.

            return

In these examples we have used the new-style `.Actor` class, but it's trivial to replace it with the legacy actor class `.LegacyActor`. The parameters to start a `.LegacyActor` are the same with the exception that we pass the hostname and port where the actor will be serving, and we can provide the ``tron_host`` and ``tron_port`` to connect to an instance of ``Tron``. We'll talk more about legacy actor in a :ref:`following section <legacy-actors>`.

Configuration files
~~~~~~~~~~~~~~~~~~~

In general the parameters to start a new actor are stored in a configuration file. We can instantiate a new actor from it with the `~.Actor.from_config` classmethod ::

    actor = Actor.from_config('~/config_files/actor.yaml')

The parameter passed to `~.Actor.from_config` must be a YAML file with the configuration. If the configuration file has a section called ``actor``, that subsection will be used. Alternatively, a dictionary with the configuration already parsed can be passed to `~.Actor.from_config`. The parameter names in the configuration files must be the same as those of the arguments and keyword arguments used to instantiate `.Actor`. The following is an example of a valid configuration file

    .. code:: yaml

        actor:
            name: jaeger
            user: guest
            host: 127.0.0.1
            version: 0.2.0dev
            log_dir: /data/logs/actors/jaeger

The behaviour for `.LegacyActor` is the same but note that the parameters for tron must be grouped under its own subsection

    .. code:: yaml

        actor:
            name: jaeger
            host: 127.0.0.1
            port: 19990
            version: 0.2.0dev
            tron:
                host: 127.0.0.1
                port: 6093
                models: ['tcc']
            log_dir: /data/logs/actors/jaeger

Overriding `~.Actor.from_config` when subclassing the actor can be a bit tricky if you have added new parameters. Here is an example of how to correctly do so ::

    class JaegerActor(clu.LegacyActor):

        def __init__(self, fps, *args, **kwargs):

            self.fps = fps

            super().__init__(*args, **kwargs)

        @classmethod
        def from_config(cls, config, fps):

            return super().from_config(config, fps)

Note that the new argument ``fps`` must be the *first* argument in ``__init__``.

The logger
~~~~~~~~~~

When an actor gets instantiated, a new logger is attached. The path to the file logger defaults to ``/data/logs/actors/<name>/<name>.log`` where ``<name>`` is the actor name, although this can be changed via the ``log_dir`` parameter. The file log rotates at midnight UTC or when a new instance of the logger is created. The logger name is ``actor:<name>``.

The logger provides a few niceties, such as coloured console output and exception traceback formatting. It also captures the warnings issues with the ``warnings`` module.



Defining commands
-----------------

The command parser
~~~~~~~~~~~~~~~~~~

Timing out commands
~~~~~~~~~~~~~~~~~~~

The command status
~~~~~~~~~~~~~~~~~~


Commanding other actors
-----------------------


The keyword model
-----------------

Validating keywords
~~~~~~~~~~~~~~~~~~~


.. _devices:

Devices
-------


.. _asyncio: https://docs.python.org/3/library/asyncio.html
