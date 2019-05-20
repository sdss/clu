
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


.. _running-actor:

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

In these examples we have used the new-style `.Actor` class, but it's trivial to replace it with the legacy actor class `.LegacyActor`. The parameters to start a `.LegacyActor` are the same with the exception that we pass the hostname and port where the actor will be serving, and we can provide the ``tron_host`` and ``tron_port`` to connect to an instance of ``Tron``. We'll talk more about legacy actor in a :ref:`following section <legacy-actors>`.

.. note::
    Right now it is assumed that the AMQP client can connect to the server without a password. This may change in the future.

Configuration files
~~~~~~~~~~~~~~~~~~~

In general the parameters to start a new actor are stored in a configuration file. We can instantiate a new actor from it with the `~.Actor.from_config` classmethod ::

    actor = Actor.from_config('~/config_files/actor.yaml')

The parameter passed to `~.Actor.from_config` must be a YAML file with the configuration. If the configuration file has a section called ``actor``, that subsection will be used. Alternatively, a dictionary with the configuration already parsed can be passed to `~.Actor.from_config`. The parameter names in the configuration files must be the same as those of the arguments and keyword arguments used to instantiate `.Actor`. The following is an example of a valid configuration file

    .. code:: yaml

        {
         actor:
             name: jaeger
             user: guest
             host: 127.0.0.1
             version: 0.2.0dev
             log_dir: /data/logs/actors/jaeger
        }

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

It is possible to pass your own `~logging.Logger` instance to the actor via the ``log`` parameter, or set ``log=False`` to disable logging.


Defining commands
-----------------

When the actor receives a new command via a queue (new-style actor) or socket (legacy actor), it is parsed and a `.Command` object is created to track its status and completion. Then the *command function* that matches the parsed command is called with the `.Command` instance and the appropriate parameters. It may sound a bit confusing that a command can be the string received from commander, the instance of `.Command` used to keep track of its completion, and the function that executes the command task, but there are historical reasons to keep this nomenclature and in most cases it's obvious from the context to which one we are referring.

Ultimately the whole process of receiving a command string, parsing it, creating a `.Command` instance, and calling the command function happens internally and the user does not need to worry about it unless you're planning to `create your own parser <override-parser>`_. Let's see a very simple example of a command that is always available, ``ping`` ::

    @command_parser.command()
    def ping(command):
        """Pings the actor."""

        command.write(text='Pong')
        command.set_status(command.status.DONE)

        return

We'll worry about what ``@command_parser.command()`` means later. For now lets focus on the function. ``ping()`` gets called when the parser receives the ``ping`` string. The function always receives a `.Command` instance as the first argument, followed by other arguments or parameters the command accepts (none for ``ping``). In this case the command function simply replies with the keyword ``text`` set to ``'Pong'`` and then marks the status as `~.CommandStatus.DONE`. This is an easy way of knowing if the actor is running and alive.

The command parser
~~~~~~~~~~~~~~~~~~

So, what was that weird decorator wrapping the command function? CLU uses `click <https://click.palletsprojects.com/en/7.x/>`_ as its default command parser. If you're not familiar with that package you should go and read their `documentation <click>`_ since you'll need it to define new commands.

The entry point for all commands is the ``command_parser`` `group <https://click.palletsprojects.com/en/7.x/commands/>`_. Any command added to ``command_parser`` will become an actor command. Let's add a simple status command that accepts an optional flag ``--verbose`` ::

    import click
    from clu import command_parser

    @command_parser.command()
    @click.option('--verbose', is_flag=True, help='outputs extra information')
    def status(command, verbose=False):
        """Returns the status."""

        command.write(text='Everything is ok.')

        if verbose:
            command.write(text='Some extra information.')

        command.set_status(command.status.DONE)

        return

We'll talk about some advanced features of the parser in :ref:`parser`.


The help command
````````````````

By default, the command set comes with a ``help`` command that outputs the usage of the available commands. As long as you document your commands and options correctly (see `the relevant section in the click documentation <https://click.palletsprojects.com/en/7.x/documentation/>`_) the usage is autogenerated. For example, in a legacy style actor, if you send the command ``help`` the output will be something like ::

    0 1 w text="Usage: COMMAND [ARGS]..."
    0 1 w text=""
    0 1 w text="Options:"
    0 1 w text="  --help  Show this message and exit."
    0 1 w text=""
    0 1 w text="Commands:"
    0 1 w text="  goto   Sends a positioner to a given (alpha, beta) position."
    0 1 w text="  help   Shows the help."
    0 1 w text="  ping   Pings the actor."

Timing out commands
```````````````````

Sometimes you want your command to timeout after a certain amount of time if it has not completed. You can achieve that with the `~.parser.timeout` decorator ::

    from clu.parser import timeout

    @command_parser.command()
    @timeout(10)
    def my_command(command):
        """A command that timeouts after 10 seconds."""

        ...

The command status
~~~~~~~~~~~~~~~~~~

You can access and modify the status of a `.Command` instance via the `~.BaseCommand.status` property. Statuses must be values of the `.CommandStatus` enumeration. They can also be set as a string. You can change the status of a command by doing ::

    command.status = CommandStatus.DONE

or via the `~.BaseCommand.set_status` method, which also allows you to set a message ::

    command.set_status('FAILED', message={'text': 'this command failed'})

When a command string is parsed and the command function called, the command is set to `~.CommandStatus.RUNNING`. Any time a command status changed, a reply is send to the command with the message code associated with the status. A command should always successfully be `~.CommandStatus.DONE` or set to one of the various `~.CommandStatus.FAILED_STATES`. `.Command` instances are also `Futures <asyncio.Future>` and their result is set when the command is done (successfully or not).

Sometimes it's necessary to wait until a command has reached a certain status before doing something else. This can be accomplished with the `~.StatusMixIn.wait_for_status` method ::

    # Wait until command has been cancelled
    await command.wait_for_status(CommandStatus.CANCELLED)

Replying to the commander
~~~~~~~~~~~~~~~~~~~~~~~~~

One of the most frequent tasks the command needs to do is to reply to the commander with a series of keywords and values. This is done by using the `~.BaseCommand.write` method ::

    command.write(message_code='i', message={'lamp_on': True, 'ffs': 'closed'})

In this case we are outputting two keywords, ``lamp_on`` and ``ffs``, the first with a boolean value and the second with a string. The first parameter, ``mesage_code``, indicates the typo of message and must be:

.. _message-codes:

- ``d`` for a *debug* message.
- ``i`` for an *info* message.
- ``w`` for a *warning* message.
- ``f`` for a message that accompanies to a failed command.
- ``:`` for a message that accompanies to a successfully done command.

All the commands are output in the same way regardless of the message code. We will talk more about the reply format in following sections.

It is also possible to call `~.BaseCommand.write` with keywords in the form of parameters. The following command is equivalent to the previous example ::

    command.write('i', lamp_on=True, ffs='closed')

By default the command will reply only to the commander, but in some cases we want to broadcast a message to *all* the clients in the actor network. This is useful for status commands or :ref:`internal periodic commands <periodic-command-pattern>`. In that case with can pass a ``broadcast=True`` to  `~.BaseCommand.write`.


Commanding other actors
-----------------------

Frequently one of our commands requires commanding a different actor and waiting for it to complete ::

    external_command = my_command.actor.send_command('actor2', 'goto ra=100 dec=20')

In this case our command, ``my_command``, is commanding ``actor2`` and sending it the command string ``goto ra=100 dec=20``. Note that the returned ``external_command`` is itself a `.Command` instance and as such a `~asyncio.Future`. We can wait until the command is done ::

    # Block until external_command is done
    await external_command

    # Do something else
    ...


The keyword model
-----------------

Validating keywords
~~~~~~~~~~~~~~~~~~~


.. _devices:

Devices
-------

A `.Device` provides a TCP socket to a remote server and a way of handling messages from it. Devices are usually small pieces of hardware that do not need a dedicated actor and that have a limited command set. For example, a telescope control actor can have multiple devices (mirror actuators, lamps, flat field screens), each one of them behind a terminal server.

Devices are usually instantiated and started with the actor by subclassing `.Actor` or `.LegacyActor`, which is quite straightforward to do ::

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

We can write to the device via the `.Device.write` method. The callback passed to the `.Device` must be a coroutine that handles each line received from the actor.

It is possible, in principle, to connect directly to another legacy actor using a device (as long as the actor accepts multiple connections) and handle the commands and replies directly. This is strongly discouraged since it contravenes the :ref:`legacy protocol <opscore-protocol>`; all communication to and from other legacy actors must happen through ``Tron``.


.. _asyncio: https://docs.python.org/3/library/asyncio.html
