
.. _parser:

Command parsing
===============

The term "command" is somewhat overused and employed to represent several related concept. A "command" can refer to:

- The *string* that is received by an actor indicating that it must perform a certain task.
- A *command parser* is the code that interprets the command string and executed a certain function.
- The callback function called by the command parser is also called a command.
- When a command is received by the actor, an instance of `.Command` is used to store the the command string and to keep track of its status. We refer to this object as an *actor-side command* or *actor command*.
- When a command is sent from a client to the actor, the same `.Command` class is used to track its status. While the class is the same, these commands cannot write to the users (since clients can't) but are aware of the replies that they receive from the actor being commanded. We refer to these commands as *client-side command* or *client command* and its specific features are described in more detail in :ref:`actor-communication`.

When an actor received a command string via its communication channel, it creates a `.Command` object with information about the string, the commander, the command id, and other parameters specific to the type of actor. The `.Command` is then processed by `~.BaseActor.parse_command`, which determines the command callback to execute. At that point the `status <.CommandStatus>` of the `.Command` is set to `~.CommandStatus.RUNNING`.

The command callback performs whatever tasks it must *in a non-blocking way*, allowing other commands to be processed in parallel. When the command callback finishes or fails, it marks the status of the command `~.CommandStatus.DONE` or `~.CommandStatus.FAILED`.

A `.Command` is a `~asyncio.Future` and can be awaited. The Future returns once the command is done, failed, or cancelled. For example ::

    # A client asks the guider actor to update
    # its status. send_command returns the Command.
    >>> command = await client.send_command('guider', 'status')

    # await command, which tells the event loop to do
    # something else until the command is done.
    >>> await command

    # Check if the command completed successfully
    >>> command.is_done
    True


.. _click-parser:

The Click parser
----------------

`.BaseActor` is parser-sceptic and does not implement any specific command parser. We'll see :ref:`below <override-parser>` how to define your own parser. The default parser in CLU, which is used in `.AMQPActor`, `.JSONActor`, and `.LegacyActor`, is implemented in `.ClickParser`. `.ClickParser` uses `click <https://click.palletsprojects.com/en/7.x/>`__ to define callbacks with complicated argument and options, and to parse the command string into calling one of those callbacks. The result is that it's very simple to define new command callbacks as long as one understands the basics of click.

Let's see a minimal example of a `.LegacyActor` that implements two commands ::

    import click

    from clu import LegacyActor
    from clu.parser import command_parser

    class CameraActor(LegacyActor):
        pass

    @command_parser.command()
    async def status(command):
        command.write('i', text='I am fine!')
        return command.finish()


    @command_parser.command()
    @click.argument('EXPTIME', type=float)
    @click.option('--imagetype', type=click.Choice(['science', 'bias'],
                  default='science', help='The type of image')
    async def expose(command, exptime, imagetype):
        ...

``command_parser`` is the predefined `.CluGroup` that serves as the parent for all the commands in an actor. By default it only includes the ``help`` and ``ping`` commands. Here we have added a ``status`` command that doesn't accept any argument or option. When the actor receives the command ``status`` it call the status callback, which writes ``text="I am fine!"``, marks the command done, and exists. Note that all the callbacks receive the `.Command` as the first argument.

The second command, ``exposure`` requires a mandatory argument, the exposure time, and an optional one, the image type, which must be one of the two valid options.

Note that the callbacks can be normal functions or coroutines.

Help and ping
^^^^^^^^^^^^^

The default ``command_parser`` includes two commands, ``ping``, which just responds with a ``'Pong'`` text if the actor is alive and ``help``. ``help`` takes advantage of the internal help click builder to automatically generate documentation for your command parser. As long as you document your command and options `as any other click CLI <https://click.palletsprojects.com/en/7.x/documentation/>`__, when the actor received the command ``help`` it will output a series of lines with the full documentation. You can also do ``expose --help`` to receive the help string for the ``expose`` command.

Creating groups
^^^^^^^^^^^^^^^

Same as click, it is possible to create `groups <https://click.palletsprojects.com/en/7.x/commands/>`__ of commands. This is useful to organise multiple subcommand that serve a similar purpose ::

    @command_parser.group()
    def camera(command):
        pass

    @camera.command()
    async def camera_command_1(command):
        pass

    @camera.command()
    async def camera_command_2(command):
        pass

To invoke ``camera-command-2`` (note that underscores are, by default, converted to dashes by click) we would need to send the command string ``camera camera-command-2``.

.. warning:: CLU groups must be normal function (no coroutines). This is a limitation that will be removed in the future.

Invoking other commands
^^^^^^^^^^^^^^^^^^^^^^^

Sometimes one needs to call a command from another command. This can be accomplished by creating a child command. Say that, while exposing, we want to output the status of the camera ::

    @command_parser.command()
    @click.argument('EXPTIME', type=float)
    @click.option('--imagetype', type=click.Choice(['science', 'bias'],
                default='science', help='The type of image')
    async def expose(command, exptime, imagetype):
        ...
        await clu.Command('status', parent=command).parse()
        ...

Here we are creating a new `.Command` with ``command`` as parent. `.Command.parse` automatically parses the command and executes the ``status`` callback.

Passing arguments to a command
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For convenience, sometimes we want to pass an argument to all the command callbacks in addition to the `.Command` instance. For example, our camera actor may need to interact with a ``camera_system`` object that allows to perform operations on the camera hardware. We can do that at the time of defining the new actor ::

    class CameraActor(LegacyActor):

        def __init__(self, camera_system, *args, **kwargs):
            self.parser_args = [camera_system]
            super().__init__(*args, **kwargs)

By setting ``parser_args`` we ensure that every command callback will receive the ``camera_system`` object after the command instance, and before any click-defined argument or option.

Creating a click command parser from scratch
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Normally one does not need to create its own parent command parser, but there may be cases in which we want to do it, for example if the package we're working implements more than one actor and the command could be mixed up. To define a completely new command parser do ::

    import click
    from clu.parser import CluGroup

    @click.group(cls=CluGroup)
    def my_command_parser(command):
        pass

    class CameraActor(LegacyActor):
        parser = my_command_parser

Now you can add commands and groups to ``my_command_parser`` as above.

Cancellable commands
^^^^^^^^^^^^^^^^^^^^

It's possible to pass a ``cancellable=True`` parameter to the ``CluCommand.command()`` decorator (note that this is not a standard Click parameters) as in ::

    @command_parser.command(cancellable=True)
    async def cancellable_command(command):
        ...

If ``cancellable=True``, a new option ``--stop`` will be added to the command. When the command is called the first time it will run normally. If during the execution of the command we call ``cancellable-command --stop``, the first instance will be cancelled where it stands.

If while an instance of ``cancellable-command`` is running we invoke another (without ``--stop``), the second command will fail to start, i.e., ``cancellable=True`` implies command uniqueness.


.. _json-parser:

JSON parser
-----------

Another available parser is `.JSONParser`, which assumes the command is a JSON string that can be deserialised into a dictionary. This is useful for actors to which we want to send complex arguments (for example a dictionary or a serialised object) which would be complicated using the Click parser. The downside is that the resulting parser is not user-friendly. Because of this, the JSON parser is best indicated for actors that will only be addressed programmatically and not over a command line interface. As such, they make for a good parser for devices that are controlled by a low-level actor.

There are no ready-to-use actors that implement the JSON parser, but it's trivial to create one from a base actor. For example, using `.AMQPBaseActor` ::

    async def command1(command, payload):
        return command.finish()

    class AMQPJSONActor(JSONParser, AMQPBaseActor):
        callbacks = {"command1": command1}

Note that the order of the imports is important. `.JSONParser` should be listed before the base actor to make sure that `.BaseActor.parse_command` is overridden. It's also possible to subclass from `.TCPBaseActor` or `.BaseLegacyActor` to use a TCP transport.

The callbacks for the parser must be coroutines that accept the command as the first arguments and a payload (a dictionary with the deserialised JSON string) as the second one. The mapping of command "verb" to callback is defined in the ``callbacks`` attribute.

The command strings sent to the actor must be a JSON string that contains at least a keyword ``command`` with the callback to be called. The ``command`` is unpacked and the corresponding callback is called with the `.Command` object and the rest of the payload. Callbacks are scheduled as tasks. For example, sending a command to an instance of ``AMQPJSONActor`` with the command string ::

    '{ "command": "command1", "option1": 1, "data": [1, 2, 3] }'

will result in ``command1`` being scheduled with the payload ``{'option1': 1, 'data': [1, 2, 3]}``.


.. _override-parser:

Building your own parser
------------------------

Implementing your command parser is simple. One just needs to override the `.BaseActor.parse_command` method with its own machinery to parse the command and execute callbacks. For example ::

    class MyParser():

        def parse_command(self, command):

            # Set the command as running.
            command.set_status(command.status.RUNNING)

            # The command string is in command.body
            self.do_some_smart_parsing(command.body)

            ...

    class MyActor(MyParser, BaseActor):

        def start(self):
            pass

        def new_command(self, command_string):
            command = Command(command_string=command_string)
            return self.parse_command(command)

When ``MyActor`` receives a new command via its communication channel, it will wrap it into a `.Command` and send it to ``MyParser.parse_command``. ``parse_command`` is a normal function and must process the new command and execute the callback in a non-blocking way, for example by creating a new asyncio task. Note that the order of the subclasses in ``MyActor`` is important, the custom parser class must be the first subclass since we want ``parse_command`` to override `.BaseActor.parse_command`.

Of course, this is a *very* minimal example and things are more complicated in reality. For a relatively minimal but complete example of implementing a new actor with a parser, see the source code for `ClickParser <https://github.com/sdss/clu/blob/81f8a8bee783b15658a5a7348fad41b590698938/python/clu/parser.py#L256>`__ and `JSONActor <https://github.com/sdss/clu/blob/81f8a8bee783b15658a5a7348fad41b590698938/python/clu/actor.py#L147>`__.

Tasks
-----

`.AMQPActor` accepts a special type of callback called *tasks*.  Tasks are simple coroutines that receive a Python dictionary as a payload and execute some code internally. They don't provide command tracking or replies to clients (although they can broadcast messages). The advantage of tasks is that they are programmatically simple to define and command as they don't require formatting the arguments as a command string. In that sense they behave a bit like `.JSONActor` commands.

To define a task, we simply write a coroutine that accepts a single argument, a dictionary payload ::

    async def my_task(payload: dict[str, Any]):
        actor = payload['__actor__']
        actor.write('w', text="Executing my-task.")
        ...

and then add it as a `task handler <.AMQPActor.add_task_handler>` to the actor ::

    amqp_actor.add_task_handler('my-task', my_task)

Note that the actor itself is added to the payload as ``__actor__`` and can be retrived by the task callback to broadcast messages or otherwise access actor attributes.

Now we can execute the task, from an AMQP client ::

    amqp_client.send_task('remote-actor', 'my-task', {'value': 1})

Tasks as scheduled to run in the background, and errors are not retrived or otherwise communicated to the user (except via broadcasts, if the task handler does so).

API
---

.. autoclass:: clu.parsers.click.ClickParser
    :noindex:
.. autoclass:: clu.parsers.click.CluCommand
    :noindex:
.. autoclass:: clu.parsers.click.CluGroup
    :noindex:
.. autofunction:: clu.parsers.click.timeout
    :noindex:
.. autofunction:: clu.parsers.click.timeout
    :noindex:
.. autofunction:: clu.parsers.click.cancel_command
    :noindex:
.. autofunction:: clu.parsers.click.get_running_tasks
    :noindex:
.. autofunction:: clu.parsers.click.get_current_command_name
    :noindex:

.. autoclass:: clu.parsers.json.JSONParser
    :noindex:
