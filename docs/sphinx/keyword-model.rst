
.. _keyword-model:

The keyword model
=================

Each actor has an associated keyword model that must be defined in advance. The model determines the keywords that we can expect to receive from the actor and they data types. Based on that model a client or a different actor can keep track of the status of the actor and register callbacks to be executed when a keyword changes.

``CLU`` provides a uniform interface for defining keyword models regardless of the specific type of actor and its message broker.


JSON validation
---------------

New-style actors define their datamodels using a JSON file that support `validation <https://json-schema.org>`__.

For example, let's say we have an actor called ``guider`` that can return two keyword: ``text``, with a random string value, and ``fwhm`` which must be a float. The datamodel for such actor can be defined in a file ``guider.json`` as

.. code-block:: json

    {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "fwhm": {"type": "number"}
        },
        "additionalProperties": false
    }

Note the ``additionalProperties`` entry which prevents undefined keywords to be parsed.


The model set
-------------

To instantiate a model from a JSON schema we use the `.Model` class ::

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

    >>> model['fwhm']
    <Property (fwhm): None>
    >>> print(model['fwhm'].value)
    None

In general, it's convenient to group all the models that we'll be monitoring in a `.ModelSet`. The `.ModelSet` is instantiated with the path to a directory that contains one or more schema definitions as JSON, an we indicate which ones we want to load ::

    >>> from clu.model import ModelSet
    >>> model_set = ModelSet(client, actors=['sop', 'guider'])
    >>> list(model_set)
    ['sop', 'guider']
    >>> model_set['guider']
    <Model (guider)>

Where`` client`` is a client or actor that can send command. In the background, what happens is that `.ModelSet` commands each one of the actors to send their own schema as a string, parses it, and loads the model.


Defining the actor's own model
------------------------------

Each actor should know its own model, which is defined in a JSON file that lives in the same repository as the actor. When the actor is instantiate we can then do ::

    sop_actor = AMQPActor('sop', host='localhost', port=9999, schema='./sop_schema.json')

This will load the schema as a `.Model` into the ``AMQPActor.model`` attribute. Any reply the actor writes will be first validated against its own schema and if fails, the reply won't be emitted.

A number of keywords (``text``, ``help``, ``schema``, ``version``, and ``text``) are added automatically to all the schemas since they are used internally by CLU.


Using a data model with an actor or client
------------------------------------------

Frequently we have an actor or client that connects to the exchange or ``tron`` and we want to monitor a series of models, each one of them being updated by the replies received. When we instantiate a new actor or client we can pass ``model_path`` and ``model_names`` to automatically create a `.ModelSet` as we saw in the previous section ::

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
    >>> tron = TronConnection('localhost', 6093, model_names=['guider'])
    >>> await tron.start()
    >>> tron.models
    {'guider': <Model (guider)>}
    >>> tron.models['guider']
    <Model (guider)>
    >>> tron.models['guider']['fwhm']
    <TronKey (fwhm): []>
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

The initial value of the keyword is ``None`` but once a reply updates it, we can access its values ::

    >>> tron.models['guider']['fwhm'].value[0].name
    'expID'
    >>> tron.models['guider']['fwhm'].value[0]
    12345
    >>> tron.models['guider']['fwhm'].value[4]
    1.23

In practice, one can treat tron models the same way as other models, with the difference that the value of each keyword is always a list and one must know what each element represents.

Adding callbacks
----------------

One of the main advantages of having a self-updating model for an actor is that we can register callbacks to be executed when a keyword or model changes. We can register a callback directly to the model ::

    >>> client.models['guider'].register_callback(model_callback)

``model_callback`` can be either a function or a coroutine and is called when the model is updated. The function receives the `.Model` instance as the only argument.

More likely, we'll want to add callbacks to specific keywords, which is done as ::

    >>> client.models['guider']['fwhm'].register_callback(fwhm_callback)

In this case ``fwhm_callaback`` is only called if ``guider.fwhm`` is updated, and receives the `.Property` (or `.TronKey` in case of a legacy-style keyword) as the only argument.

Note that the callbacks are executed every time a reply that includes the model or keyword are received, even if the value of the keyword doesn't change.
