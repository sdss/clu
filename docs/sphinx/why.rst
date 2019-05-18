Why a new messaging protocol for SDSS?
--------------------------------------

Say whatever you want about it, the current SDSS message passing protocol based on ``Tron``, ``opscore``, and ``actorcore`` is stable and robust. So, why should we replace it? Here is a list of reasons:

- It reinvents the wheel. Ok, in all honesty ``Tron`` and ``opscore`` were written when wheel were still not completely circular, but the truth is that nowadays there are more robust, standard, and better documented technologies out there for message passing.
- We can remove the need for a central hub product by relying in open-source message brokers such as `RabbitMQ <https://rabbitmq.com>`__.
- ``Tron`` and ``opscore`` are Python 2 and it's unclear the amount of effort that would be needed to convert them to Python 3.
- While there is some documentation for ``Tron`` and ``opscore``, and the code is well written, it's also cumbersome and difficult to modify by people that didn't write it. It's ultimately non-maintainable.
- The ``opsctore``/``actorkeys`` datamodel is custom-built and extremely difficult to maintain. Standard solutions such as JSON with a `JSON schema <https://json-schema.org/>`__ validator should be preferred.
- `asyncio <https://docs.python.org/3/library/asyncio.html>`__ provides an asynchronous API that is cleaner and easier to code than using threads. It is also more readable and less convoluted than `twisted <https://twistedmatrix.com/trac/>`__ and it's a Python core library with very active development.
