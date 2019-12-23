# -*- coding: utf-8 -*-
from setuptools import setup

package_dir = \
{'': 'python'}

packages = \
['clu', 'clu.legacy', 'clu.legacy.ply', 'clu.misc', 'clu.tests']

package_data = \
{'': ['*']}

install_requires = \
['Click>=7.0,<8.0',
 'aio_pika>=6.4.1,<7.0.0',
 'jsonschema>=3.0.1,<4.0.0',
 'numpy>=1.15.1,<2.0.0',
 'prompt-toolkit>=3.0.0,<4.0.0',
 'pygments>=2.2.0,<3.0.0',
 'ruamel.yaml>=0.15.61,<0.16.0']

extras_require = \
{'docs': ['Sphinx>=2.0,<3.0',
          'sphinxcontrib-trio==1.1.0',
          'semantic-version==2.8.0',
          'asynctest>=0.13.0,<0.14.0']}

setup_kwargs = {
    'name': 'sdss-clu',
    'version': '0.1.10a0',
    'description': 'A new protocol for SDSS actors.',
    'long_description': "`CLU <https://tron.fandom.com/wiki/Clu>`__\n==========================================\n\n|py| |Build Status| |docs|\n\n\n`CLU <https://tron.fandom.com/wiki/Clu>`_ implements a new protocol for SDSS actor while providing support for legacy-style actor.\n\n\nFeatures\n--------\n\n- Asynchronous API based on `asyncio <https://docs.python.org/3/library/asyncio.html>`_.\n- New-style actor with message passing based on `AMQP <https://www.amqp.org/>`_ and `RabbitMQ <https://rabbitmq.com>`_.\n- Legacy-style actor for TCP socket communication through ``Tron``.\n- Tools for device handling.\n- Messages are validated JSON strings.\n- `click <https://click.palletsprojects.com/en/7.x/>`__-enabled command parser.\n\n.. warning:: CLU is under active development and it must be considered in beta stage. The API is changing quickly and breaking changes are frequent.\n\n\nInstallation\n------------\n\n``CLU`` can be installed using ``pip`` as ::\n\n    pip install sdss-clu\n\nor from source ::\n\n    git clone https://github.org/sdss/clu\n    cd clu\n    python setup.py install\n\nIf you want to install it using `modules <http://modules.sourceforge.net/>`_ you can use `sdss_install <https://github.com/sdss/sdss_install>`_ ::\n\n    sdss_install clu\n\n\nQuick start\n-----------\n\nCreating a new actor with ``CLU`` is easy. To instantiate and run an actor you can simply do ::\n\n    import asyncio\n    from clu import Actor\n\n    async def main(loop):\n        actor = Actor('guest', 'localhost', loop=loop).run()\n\n\n    loop = asyncio.get_event_loop()\n    loop.create_task(main(loop))\n    loop.run_forever()\n\nNext, head to the `Getting started <https://clu.readthedocs.io/en/latest/getting-started.html>`_ section for more information about using actors.\n\n\nWhy a new messaging protocol for SDSS?\n--------------------------------------\n\nSay whatever you want about it, the `current SDSS message passing protocol <https://clu.readthedocs.io/en/latest/legacy.html>`_ based on ``Tron``, ``opscore``, and ``actorcore`` is stable and robust. So, why should we replace it? Here is a list of reasons:\n\n- It reinvents the wheel. Ok, in all honesty ``Tron`` and ``opscore`` were written when wheel were still not completely circular, but the truth is that nowadays there are more robust, standard, and better documented technologies out there for message passing.\n- We can remove the need for a central hub product by relying in open-source message brokers such as `RabbitMQ <https://rabbitmq.com>`__.\n- ``Tron`` and ``opscore`` are Python 2 and it's unclear the amount of effort that would be needed to convert them to Python 3.\n- While there is some documentation for ``Tron`` and ``opscore``, and the code is well written, it's also cumbersome and difficult to modify by people that didn't write it. It's ultimately non-maintainable.\n- The ``opsctore``/``actorkeys`` datamodel is custom-built and extremely difficult to maintain. Standard solutions such as JSON with a `JSON schema <https://json-schema.org/>`__ validator should be preferred.\n- `asyncio <https://docs.python.org/3/library/asyncio.html>`__ provides an asynchronous API that is cleaner and easier to code than using threads. It is also more readable and less convoluted than `twisted <https://twistedmatrix.com/trac/>`__ and it's a Python core library with very active development.\n- CLU uses `click <https://click.palletsprojects.com/en/7.x>`__ for parsing commands, providing a well-defined, easy to use parser.\n\n\n.. |Build Status| image:: https://travis-ci.org/sdss/clu.svg?branch=master\n    :alt: Build Status\n    :target: https://travis-ci.org/sdss/clu\n\n.. |Coverage Status| image:: https://codecov.io/gh/sdss/clu/branch/master/graph/badge.svg\n    :alt: Coverage Status\n    :scale: 100%\n    :target: https://codecov.io/gh/sdss/clu\n\n.. |py| image:: https://img.shields.io/badge/python-3.7%20|%203.8-blue\n    :alt: Python Versions\n    :target: https://docs.python.org/3/\n\n.. |docs| image:: https://readthedocs.org/projects/docs/badge/?version=latest\n    :alt: Documentation Status\n    :scale: 100%\n    :target: https://clu.readthedocs.io/en/latest/?badge=latest\n",
    'author': 'José Sánchez-Gallego',
    'author_email': 'gallegoj@uw.edu',
    'maintainer': None,
    'maintainer_email': None,
    'url': 'https://github.com/sdss/clu',
    'package_dir': package_dir,
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'extras_require': extras_require,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)

# This setup.py was autogenerated using poetry.
