#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-26
# @Filename: conftest.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import os

import pytest
from pytest_rabbitmq import factories

from clu import AMQPActor


RMQ_PORT = 8888


# If CI is true we are in a GitHub workflow and need to use the Ubuntu paths.
# For now we are only testing Linux in CI so these are the paths where apt-get
# installs rabbitmq-server on Ubuntu 20.04. If we add more architectures we'd
# need to set some environment variable in the workflow YAML file with the
# value of runner.os and then reference it here.
# If ctl or server are None, the values are taken from pyproject.toml:pytest.
if 'CI' in os.environ and os.environ['CI'] == 'true':
    ctl = '/usr/lib/rabbitmq/bin/rabbitmqctl'
    server = '/usr/lib/rabbitmq/bin/rabbitmq-server'
else:
    ctl = server = None


rabbitmq_proc = factories.rabbitmq_proc(ctl=ctl, server=server, port=RMQ_PORT)
rabbitmq = factories.rabbitmq('rabbitmq_proc')


@pytest.fixture
async def amqp_actor(rabbitmq, event_loop):

    actor = AMQPActor(name='amqp_actor', port=RMQ_PORT)
    await actor.start()

    yield actor

    await actor.shutdown()
