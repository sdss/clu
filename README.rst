`CLU <https://tron.fandom.com/wiki/Clu>`__
==========================================

|Build Status| |Coverage Status| |py37|


`CLU <https://tron.fandom.com/wiki/Clu>`_ implements a new protocol for SDSS actor while providing support for legacy-style actor.


Features
--------

- Asynchronous API based on `asyncio <https://docs.python.org/3/library/asyncio.html>`_.
- New-style `actor <clu.actor.Actor>` with message passing based on `AMQP <https://www.amqp.org/>`_ and `RabbitMQ <https://rabbitmq.com>`_.
- Legacy-style `actor <clu.legacy.actor.LegacyActor>` for TCP socket communication through `Tron <clu.legacy.tron.TronConnection>`.
- Tools for device handling.
- Messages are validated JSON strings.
- `click <https://click.palletsprojects.com/en/7.x/>`__-enabled command parser.

.. warning:: CLU is under active development and it must be considered in beta stage. The API is changing quickly and breaking changes are frequent.


Installation
------------

``CLU`` can be installed using ``pip`` as ::

    pip install sdss-clu

or from source ::

    git clone https://github.org/sdss/clu
    cd clu
    python setup.py install

If you want to install it using `modules <http://modules.sourceforge.net/>`_ you can use `sdss_install <https://github.com/sdss/sdss_install>`_ ::

    sdss_install clu


Quick start
-----------

Creating a new actor with ``CLU`` is easy. To instantiate and run a legacy-style actor you can simply do ::

    import asyncio
    from clu import LegacyActor

    async def main(loop):
        actor = LegacyActor('localhost', 9999, 'localhost, loop=loop).run()


    loop = asyncio.get_event_loop()
    loop.create_task(main(loop))
    loop.run_forever()

and can connect to the actor on ``localhost:9999``. Next, head to the :ref:`getting-started` section for more information about using actors.


Why a new messaging protocol for SDSS?
--------------------------------------

Say whatever you want about it, the :ref:`current SDSS message passing protocol <legacy-actors>` based on ``Tron``, ``opscore``, and ``actorcore`` is stable and robust. So, why should we replace it? Here is a list of reasons:

- It reinvents the wheel. Ok, in all honesty ``Tron`` and ``opscore`` were written when wheel were still not completely circular, but the truth is that nowadays there are more robust, standard, and better documented technologies out there for message passing.
- We can remove the need for a central hub product by relying in open-source message brokers such as `RabbitMQ <https://rabbitmq.com>`__.
- ``Tron`` and ``opscore`` are Python 2 and it's unclear the amount of effort that would be needed to convert them to Python 3.
- While there is some documentation for ``Tron`` and ``opscore``, and the code is well written, it's also cumbersome and difficult to modify by people that didn't write it. It's ultimately non-maintainable.
- The ``opsctore``/``actorkeys`` datamodel is custom-built and extremely difficult to maintain. Standard solutions such as JSON with a `JSON schema <https://json-schema.org/>`__ validator should be preferred.
- `asyncio <https://docs.python.org/3/library/asyncio.html>`__ provides an asynchronous API that is cleaner and easier to code than using threads. It is also more readable and less convoluted than `twisted <https://twistedmatrix.com/trac/>`__ and it's a Python core library with very active development.
- CLU uses `click <https://click.palletsprojects.com/en/7.x>`__ for parsing commands, providing a well-defined, easy to use parser.


.. |Build Status| image:: https://img.shields.io/travis/rtfd/readthedocs.org.svg?style=flat
    :alt: Build Status
    :target: https://travis-ci.org/sdss/clu

.. |Coverage Status| image:: https://codecov.io/gh/sdss/clu/branch/master/graph/badge.svg
    :alt: Coverage Status
    :scale: 100%
    :target: https://codecov.io/gh/sdss/clu

.. |py37| image:: https://img.shields.io/badge/python-3.7-blue.svg
    :alt: Python 3.7
    :target: https://docs.python.org/3/
