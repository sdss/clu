
.. _api:

API Reference
=============

Base classes
------------

.. autoclass:: clu.base.BaseClient
.. autoclass:: clu.base.BaseActor
.. autoclass:: clu.base.Reply


Client
------

.. automodule:: clu.client


Actor
-----

.. autoclass:: clu.actor.AMQPBaseActor
.. autoclass:: clu.actor.AMQPActor
.. autoclass:: clu.actor.TCPBaseActor
.. autoclass:: clu.actor.JSONActor


Command
-------

.. automodule:: clu.command


Legacy
------

.. automodule:: clu.legacy.actor
    :members: LegacyActor

.. automodule:: clu.legacy.tron
    :members: TronCommander, TronModel, TronKey


Maskbits
--------

.. autoclass:: clu.tools.Maskbit

.. autoclass:: clu.tools.CommandStatus
    :undoc-members:
    :member-order: bysource


MixIns
------

.. autoclass:: clu.tools.StatusMixIn
.. autoclass:: clu.tools.CaseInsensitiveDict


Model
-----

.. automodule:: clu.model


Store
-----

.. automodule:: clu.store


Parser
------

.. autoclass:: clu.parsers.click.ClickParser
.. autoclass:: clu.parsers.click.CluCommand
.. autoclass:: clu.parsers.click.CluGroup

.. autofunction:: clu.parsers.click.timeout
.. autofunction:: clu.parsers.click.cancel_command
.. autofunction:: clu.parsers.click.get_running_tasks
.. autofunction:: clu.parsers.click.get_current_command_name

.. autoclass:: clu.parsers.json.JSONParser


Sockets
-------

.. automodule:: clu.protocol
    :member-order: bysource

.. automodule:: clu.device


Tools
-----

.. autofunction:: clu.escape
.. autoclass:: clu.tools.ActorHandler
.. autoclass:: clu.tools.CallbackMixIn


.. _api-testing:

Testing
-------

.. automodule:: clu.testing
    :members: setup_test_actor, MockReplyList, MockReply
