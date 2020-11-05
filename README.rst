`CLU <https://tron.fandom.com/wiki/Clu>`__
==========================================

|py| |pypi| |Build Status| |docs| |Coverage Status|


`CLU <https://tron.fandom.com/wiki/Clu>`_ implements a new protocol for SDSS actor while providing support for legacy-style actor.


Features
--------

- Asynchronous API based on `asyncio <https://docs.python.org/3/library/asyncio.html>`_.
- New-style actor with message passing based on `AMQP <https://www.amqp.org/>`_ and `RabbitMQ <https://rabbitmq.com>`_.
- Legacy-style actor for TCP socket communication via `tron <https://github.com/sdss/tron>`__.
- Tools for device handling.
- Messages are validated JSON strings.
- `click <https://click.palletsprojects.com/en/7.x/>`__-enabled command parser.


Installation
------------

``CLU`` can be installed using ``pip`` as

.. code-block:: console

    pip install sdss-clu

or from source

.. code-block:: console

    git clone https://github.com/sdss/clu
    cd clu
    pip install .


Development
^^^^^^^^^^^

``clu`` uses `poetry <http://poetry.eustace.io/>`__ for dependency management and packaging. To work with an editable install it's recommended that you setup ``poetry`` and install ``clu`` in a virtual environment by doing

.. code-block:: console

    poetry install

Pip does not support editable installs with PEP-517 yet. That means that running ``pip install -e .`` will fail because ``poetry`` doesn't use a ``setup.py`` file. As a workaround, you can use the ``create_setup.py`` file to generate a temporary ``setup.py`` file. To install ``clu`` in editable mode without ``poetry``, do

.. code-block:: console

    pip install --pre poetry
    python create_setup.py
    pip install -e .


Quick start
-----------

Creating a new actor with ``CLU`` is easy. To instantiate and run an actor you can simply do

.. code-block:: python

    import asyncio
    from clu import AMQPActor

    async def main(loop):
        actor = await Actor('my_actor').start()
        await actor.run_forever()

    asyncio.run(main(loop))

Next, head to the `Getting started <https://clu.readthedocs.io/en/latest/getting-started.html>`__ section for more information about using actors. More examples are available `here <https://clu.readthedocs.io/en/latest/examples.html>`__.


Why a new messaging protocol for SDSS?
--------------------------------------

Say whatever you want about it, the `current SDSS message passing protocol <https://clu.readthedocs.io/en/latest/legacy.html>`_ based on ``Tron``, ``opscore``, and ``actorcore`` is stable and robust. So, why should we replace it? Here is a list of reasons:

- It reinvents the wheel. Ok, in all honesty ``Tron`` and ``opscore`` were written when wheel were still not completely circular, but the truth is that nowadays there are more robust, standard, and better documented technologies out there for message passing.
- We can remove the need for a central hub product by relying in open-source message brokers such as `RabbitMQ <https://rabbitmq.com>`__.
- ``Tron`` and ``opscore`` are Python 2 and it's unclear the amount of effort that would be needed to convert them to Python 3.
- While there is some documentation for ``Tron`` and ``opscore``, and the code is well written, it's also cumbersome and difficult to modify by people that didn't write it. It's ultimately non-maintainable.
- The ``opsctore``/``actorkeys`` datamodel is custom-built and extremely difficult to maintain. Standard solutions such as JSON with a `JSON schema <https://json-schema.org/>`__ validator should be preferred.
- `asyncio <https://docs.python.org/3/library/asyncio.html>`__ provides an asynchronous API that is cleaner and easier to code than using threads. It is also more readable and less convoluted than `twisted <https://twistedmatrix.com/trac/>`__ and it's a Python core library with very active development.
- CLU uses `click <https://click.palletsprojects.com/en/7.x>`__ for parsing commands, providing a well-defined, easy to use parser.


.. |Build Status| image:: https://img.shields.io/github/workflow/status/sdss/clu/Test
    :alt: Build Status
    :target: https://github.com/sdss/clu/actions

.. |Coverage Status| image:: https://codecov.io/gh/sdss/clu/branch/main/graph/badge.svg
    :alt: Coverage Status
    :target: https://codecov.io/gh/sdss/clu

.. |py| image:: https://img.shields.io/badge/python-3.7%20|%203.8-blue
    :alt: Python Versions
    :target: https://docs.python.org/3/

.. |docs| image:: https://readthedocs.org/projects/docs/badge/?version=latest
    :alt: Documentation Status
    :target: https://clu.readthedocs.io/en/latest/?badge=latest

.. |pypi| image:: https://badge.fury.io/py/sdss-clu.svg
    :alt: PyPI version
    :target: https://badge.fury.io/py/sdss-clu
