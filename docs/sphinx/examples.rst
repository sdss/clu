
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


`tron_connection.py <examples/tron_connection.py>`__
------------------------------------------------------

A connection to tron that listens to the keywords from the guider actor and reports the FWHM.

.. literalinclude:: examples/tron_connection.py
   :language: python
