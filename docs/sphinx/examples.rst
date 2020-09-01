
.. _examples:

Examples
========

`hello_actor.py <examples/hello_actor.py>`__
--------------------------------------------

A legacy-style actor with a simple command that says hello to the user. To test it, run the actor code, open a telnet terminal as ``telnet localhost 9999``, and write ``say-hello John``.

.. literalinclude:: examples/hello_actor.py
   :language: python


`hello_actor_amqp.py <examples/hello_actor_amqp.py>`__
------------------------------------------------------

The same actor that greets you but using the `.AMQPActor`. Note that the code is identical except the subclassing and the parameters needed to start the connection to RabbitMQ. This allows to transition an actor from legacy to AMQP with minimal changes.

.. literalinclude:: examples/hello_actor_amqp.py
   :language: python

To test this code you can use the ``clu`` CLI command from a shell terminal. This creates a very simple interactive interface. In this case you need to indicate the name of the actor before the command string, so that the client knows to what AMQP queue to direct it.

.. code-block:: console

   $ clu
   hello_actor say-hello Lucy!
   hello_actor i
   hello_actor i {
      "text": "Hi Lucy!!"
   }
   hello_actor :
   hello_actor ping
   hello_actor i
   hello_actor : {
      "text": "Pong."
   }


`hello_actor_schema.py <examples/hello_actor_schema.py>`__
------------------------------------------------------

Let's continue expanding our example. Now we define the same greeter actor but we provide it with a schema. We also add a command, ``say-goodbye``, that outputs a keyword that is not in the actor schema.

.. literalinclude:: examples/hello_actor_schema.py
   :language: python

The schema file is :download:`hello_actor.json <examples/hello_actor.json>`

.. literalinclude:: examples/hello_actor.json
   :language: json

If you run the code and try to invoke the ``say-goodbye`` command, you'll get an error because it's trying to use an invalid keyword

.. code-block:: console

   hello_actor say-goodbye
   hello_actor i
   hello_actor i {
   "error": "Failed validating the reply: Additional properties are not allowed ('invalid_key' was unexpected)\n\nFailed validating 'additionalProperties' in schema:\n    {'additionalProperties': False,\n     'properties': {'error': {'type': 'string'},\n                    'schema': {'type': 'string'},\n                    'text': {'type': 'string'}},\n     'type': 'object'}\n\nOn instance:\n    {'invalid_key': 'Bye!'}"
   }
   hello_actor :

Note that in the JSON schema we included the parameter ``"additionalProperties": false``. That is the line that actually enforces that outputting undefined keywords breaks the validation. Otherwise the schema will accept other undefined keywords but will still validate the type and format of those specified in the schema.


`tron_connection.py <examples/tron_connection.py>`__
------------------------------------------------------

A connection to tron that listens to the keywords from the guider actor and reports the FWHM.

.. literalinclude:: examples/tron_connection.py
   :language: python


`jaeger_actor.py <examples/jaeger_actor.py>`__
----------------------------------------------

The following code shows the real implementation of the `jaeger actor <https://github.com/sdss/jaeger>`__. There are a few interesting things to note.

- First, this actor receives an ``fps`` object when it gets initialised, which allows the actor to command the associated hardware. The ``fps`` gets added to ``self.parser_args`` and it's passed to each command callback along with the command (and any arguments and options defined for the command).

- Second, this actor sets its version to match that of the library that is wrapping. This is a good design choice to make sure that the version of the actor reports the library tag used.

- Third, the actor adds an `.ActorHandler` to the jaeger library log. Any log message above level ``INFO`` will be output to the actor as a reply. If, for example, there were an exception in the library, the traceback would be reported to the user that is connected to the actor.

- Finally, we implement a `.TimedCommand`, which executes the command ``ieb status`` every 60 seconds without input from the user.

.. literalinclude:: examples/jaeger_actor.py
   :language: python
