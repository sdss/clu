Keyword store
=============

Sometimes it is useful to keep a record of the keywords that our own actor has output. For example, our actor may be outputting the keyword ``guideRMS`` with a measurement of the RMS of the guide loop. After pointing the RMS will be large and will decrease as the acquisition algorithm finishes acquiring the field. We may want to introduce some logic to do some action once the RMS has reached a certain threshold and been there for at least to iteration of the guide loop. In this case, it would be useful to keep a record not only of the last value of ``guideRMS``, but its full history.

We can accomplish this by setting ``store=True`` when instantiating a new actor (note that this feature is disabled by default). Any keyword output through the actor will be stored in a `.KeywordStore` dictionary. ::

    >>> actor = JSONActor('my_actor', port=1111, store=True)
    >>> actor.write('i', text="¡Hola!")
    >>> actor.write('i', text="Adiós")
    >>> actor.store
    KeywordStore(list,
             {'text': [KeywordOutput(name='text', message_code='i', date=datetime.datetime(2022, 9, 1, 15, 0, 46, 729062), value='¡Hola!'),
               KeywordOutput(name='text', message_code='i', date=datetime.datetime(2022, 9, 1, 15, 1, 33, 115656), value='Adiós')]})
    >>> len(actor.store['text'])
    2
    >>> actor.store['text'][-1].value
    'Adiós'

For each keyword the `.KeywordStore` dictionary will keep a list of each time the keyword has been output with its value, message code, and date-time. We can get the last two values the keyword has been output ::

    >>> text_outputs = actor.store.tail('text', n=2)
    >>> print([to.value for to in text_outputs])
    ['¡Hola!', 'Adiós']

If you want to record only certain keywords you can do that by providing a list of keywords to filter on ::

    >>> actor = JSONActor('my_actor', port=1111, store=['error'])
    >>> actor.write('i', text="Salutations!")
    >>> actor.write('e', error="Oops")
    >>> len(actor.store['text'])
    0
    >>> len(actor.store['error'])
    1
    >>> actor.store['error'][0].value
    'Oops'

API
---

.. automodule:: clu.store
    :noindex:
