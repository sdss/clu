
.. _keyword-model:

The keyword model
=================

Each actor has an associated keyword model defined in advance. The model determines the keywords that we can expect to receive from the actor and their data types. Based on that model a client or a different actor can keep track of the status of the actor and register callbacks to be executed when a keyword changes.

``CLU`` provides a uniform interface for defining keyword models regardless of the specific type of actor and its message broker.


JSON schema
-----------

Actors define their keyword datamodels using a `JSON-Schema <https://json-schema.org>`__ file. For example, let's say we have an actor called ``guider`` that can return two keywords: ``text``, with a random string value, and ``fwhm`` which must be a float. The schema for such actor can be defined in a file ``guider.json`` as

.. code-block:: json

    {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "fwhm": {"type": "number"}
        },
        "additionalProperties": false
    }

Note the ``additionalProperties`` entry which prevents undefined keywords to be output. Refer to the JSON-Schema documentation for details on how to define properties.

To associate this schema with an actor, we initiate or subclass the actor with it ::

    actor = AMQPActor('my_actor', user='user`', schema='guider.json')

or ::

    class MyActor(AMQPActor):

        schema = 'guider.json'

        ...

When the schema is present, the `write <.BaseActor.write>` method will validate the desired output against the schema and, if it does not match, will prevent the message from being output.

The following keywords are added automatically to all schemas and should not be overridden unless you know what you are doing since they are internally used by CLU: ``text``, ``help``, ``schema``, ``version``, ``text``, ``error``, ``yourUserID``, ``UserInfo``, ``num_users``.

Properties/keywords are case-sensitive.


The actor model
---------------

When an actor is instantited with a keyword schema as seen above, it creates a `.Model` of its own datamodel, used both to validate replies and also to keep track of the current state of the actor. We can instantiate a `.Model` manually from the actor schema ::

    >>> from clu.model import Model
    >>> model = Model('guider', open('guider.json', 'r').read())

If the schema is invalid an error is raised. We can now validate a reply with a set of keywords ::

    >>> model.validator.validate({'text': 'Some text here.'})
    >>> model.validator.validate({'text': 1})
    ValidationError: 1 is not of type 'string'

    Failed validating 'type' in schema['properties']['text']:
        {'type': 'string'}

    On instance['text']:
        1

When we instantiate the model we create a dictionary with the current values of each of the keywords. Each keyword is represented by a `.Property` instance. The values are set to ``None`` on initialisation ::

    >>> actor.model['fwhm']
    <Property (fwhm): None>
    >>> print(actor.model['fwhm'].value)
    None

When the actor outputs keywords as part of a reply, the values of the actor own model are update, so it's always possible to know the status of the actor. ::

    >>> actor.write('i', message={'fwhm': 1.2})
    >>> actor.model['fwhm']
    <Property (fwhm): 1.2>
    >>> print(actor.model['fwhm'].value)
    1.2


The model of other actors
-------------------------

Frequently we have an actor or client that connects to the exchange or ``tron`` and we want to monitor the status of a group of actors connected to the same message broker. When we instantiate a new actor or client we can pass a list of actor names as part of the ``models`` argument. This will create a `.ModelSet` (a mapping of actor name to `.Model`) with the models for each one of the actors ::

    >>> from clu.client import AMQPClient
    >>> client = AMQPClient('my_client', host='localhost', port=5672, models=['sop', 'guider'])
    >>> await client.start()

The models can be accessed via the ``models`` attribute. From now on, when the client or actor receives a reply from ``sop`` or ``guider``, the keywords will be validated against the schema and, if valid, the values of the model will be updated. For example ::

    # Send a command to guider asking it to report the status.
    >>> cmd = await client.send_command('guider', 'status')
    # Wait until the command is done
    >>> await cmd
    # Check the value of the FWHM
    >>> print(client.models['guider']['fwhm'].value)
    1.1


Tron models
-----------

The keyword models used by legacy actors are different (of course) in that they are not defined as JSON schemas but as `actorkeys <https://github.com/sdss/actorkeys>`__ instead. To avoid depending on ``opscore`` and other Python 2 products, ``CLU`` includes a Python 3-ready set of routines to read the actorkeys datamodel and parse the replies using it. The only requisite is that ``actorkeys`` must be in the ``PYTHONPATH`` and be importable by ``CLU``.

We can create a connection to ``tron`` and request that the client keeps track of the ``guider`` actor model ::

    >>> from clu.legacy.tron import TronConnection
    >>> tron = TronConnection('localhost', 6093, models=['guider'])
    >>> await tron.start()
    >>> tron.models
    {'guider': <Model (guider)>}
    >>> tron.models['guider']
    <Model (guider)>
    >>> tron.models['guider']['fwhm']
    <TronKey (fwhm): [572, nan, 0, 0, nan]>
    >>> tron.models['guider']['fwhm'].value
    [572, nan, 0, 0, nan]
    >>> tron.models['guider']['fwhm'].name
    'fwhm'
    >>> tron.models['guider']['fwhm'].key
    Key(fwhm)
    >>> type(tron.models['guider']['fwhm'].key)
    clu.legacy.keys.Key

Note that the key in this case is an ``opscore`` ``Key`` object, which contains information about the keyword model. All keys are composed of a list of values. In the case of the ``fwhm``, the keyword returns  ::

    >>> tron.models['guider']['fwhm'].key.typedValues.vtpyes
    Types[Int, Float, Int, Int, Float]
    >>> [vtype.name for vtype in tron.models['guider']['fwhm'].key.typedValues.vtypes]
    ['expID', 'tmean', 'nKept', 'nReject', 'mean']

We can also access the ``keyword`` attribute which contains the last emitted keyword as an ``opscore`` ``Keyword`` object ::

    >>> tron.models['guider']['fwhm'].keyword.values
    [Int(568), Float(nan arcsec), Int(0), Int(0), Float(nan arcsec)]
    >>> [value.name for value in tron.models['guider']["fwhm"].keyword.values]
    ['expID', 'tmean', 'nKept', 'nReject', 'mean']

If you are only interested int he list of value, the simplest is to used the ``value`` attribute to access a list of values as builtin Python types ::

    >>> tron.models['guider']['fwhm'].value
    [572, nan, 0, 0, nan]
    >>> type(tron.models['guider']['fwhm'].value[0])
    int

In practice, one can treat tron models the same way as other models, with the difference that the ``value`` of each keyword is always a list and one must know what each element represents.

.. note::
    Previous to CLU 0.7.4, ``TronKey.keyword`` did not exists and ``TronKey.key`` actually contained the ``Keyword`` object. CLU 0.7.4 introduces a breaking change to clarify the nomenclature and make it more consistent with ``opscore``.


.. _keyword-model-callbacks:

Adding callbacks
----------------

One of the main advantages of having a self-updating model for an actor is that we can register callbacks to be executed when a keyword or model changes. We can register a callback directly to the model ::

    >>> def model_callback(model, key): print(key)
    >>> client.models['guider'].register_callback(model_callback)

``model_callback`` can be either a function or a coroutine and is called when the model is updated. The function receives the `.Model` instance as the first argument and the modified `.Property` as the second (`.TronModel` and `.TronKey` in the case of a Tron model).

More likely, we'll want to add callbacks to specific keywords, which is done as ::

    >>> client.models['guider']['fwhm'].register_callback(fwhm_callback)

In this case ``fwhm_callaback`` is only called if ``guider.fwhm`` is updated, and receives the `.Property` (or `.TronKey` in case of a legacy-style keyword) as the only argument.

Note that the callbacks are executed every time a reply that includes the model or keyword are received, even if the value of the keyword doesn't change.


Retriving schema information
----------------------------

The :ref:`click-parser` includes two commands that allow a user or piece of code to retrieve information about another actor's schema. Calling ``get_schema`` on an actor will return a JSON string with the JSON-Schema for that actor. For example, a client can access the schema of a remote actor as ::

    cmd = await client.send_command('actor', 'get_schema')
    await cmd
    if cmd.status.did_fail:
        raise CluError(f"Failed getting schema for actor.")
    else:
        schema = json.loads(cmd.replies[-1].body["schema"])

Sometimes one is just interested in knowing the expected format of a keyword that is output by an actor. In that case the ``keyword`` command prints a user-friendly message with that information ::

    >>> actor keyword version
    i text="version = {      "
    i text="    type: string "
    i text="}                "

The ``keyword`` command is not indicated for programmatic access to the schema (use ``get_schema`` instead).
