
.. _api:

API Reference
=============

Client
------

.. automodule:: clu.client


Actor
-----

.. autoclass:: clu.actor.BaseActor
.. autoclass:: clu.actor.Actor

.. automodule:: clu.device


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

.. autoclass:: clu.base.Maskbit

.. autoclass:: clu.base.CommandStatus
    :undoc-members:
    :member-order: bysource


MixIns
------

.. autoclass:: clu.base.StatusMixIn
.. autoclass:: clu.base.CaseInsensitiveDict


Model
-----

.. automodule:: clu.model


Parser
------

.. autoclass:: clu.parser.CluCommand
.. autoclass:: clu.parser.CluGroup

.. autofunction:: clu.parser.timeout


Sockets
-------

.. automodule:: clu.protocol


Tools
-----

.. autofunction:: clu.escape


Testing
-------

.. automodule:: clu.testing
    :members: setup_test_actor, MockReplyList, MockReply, TestCommand
