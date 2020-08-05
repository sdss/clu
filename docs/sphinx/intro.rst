|Build Status| |Coverage Status| |docs| |py37|


`CLU <https://tron.fandom.com/wiki/Clu>`_ implements a new protocol for SDSS actor while providing support for legacy-style actor. The current version is |clu_version|.


Features
--------

- Asynchronous API based on `asyncio <https://docs.python.org/3/library/asyncio.html>`_.
- New-style `actor <clu.actor.AMQPActor>` with message passing based on `AMQP <https://www.amqp.org/>`_ and `RabbitMQ <https://rabbitmq.com>`_.
- Legacy-style `actor <clu.legacy.actor.LegacyActor>` for TCP socket communication through `Tron <cl.legacy.tron.TronConnection>`.
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
    pip install .

If you want to install it using `modules <http://modules.sourceforge.net/>`_ you can use `sdss_install <https://github.com/sdss/sdss_install>`_ ::

    sdss_install clu


Quick start
-----------

Creating a new actor with ``CLU`` is easy. To instantiate and run an actor you can simply do ::

    import asyncio
    from clu import AMQPActor

    async def main(loop):
        actor = AMQPActor('guest', 'localhost', loop=loop).run()


    loop = asyncio.get_event_loop()
    loop.create_task(main(loop))
    loop.run_forever()

Next, head to the :ref:`getting-started` section for more information about using actors.


.. include:: why.rst


.. |Build Status| image:: https://travis-ci.org/sdss/clu.svg?branch=master
    :alt: Build Status
    :target: https://travis-ci.org/sdss/clu

.. |Coverage Status| image:: https://codecov.io/gh/sdss/clu/branch/master/graph/badge.svg
    :alt: Coverage Status
    :target: https://codecov.io/gh/sdss/clu

.. |py37| image:: https://img.shields.io/badge/python-3.7-blue.svg
    :alt: Python 3.7
    :target: https://docs.python.org/3/

.. |docs| image:: https://readthedocs.org/projects/docs/badge/?version=latest
    :alt: Documentation Status
    :target: https://clu.readthedocs.io/en/latest/?badge=latest
