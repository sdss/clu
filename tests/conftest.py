#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-26
# @Filename: conftest.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import os
from pytest_rabbitmq import factories


# If CI is true we are in a GitHub workflow and need to use the Ubuntu paths.
if 'CI' in os.environ and os.environ['CI'] == 'true':
    ctl = ' /usr/lib/rabbitmq/bin/rabbitmqctl'
    server = ' /usr/lib/rabbitmq/bin/rabbitmq-server'
else:
    ctl = server = None


rabbitmq_proc = factories.rabbitmq_proc(ctl=ctl, server=server, port=None)
rabbitmq = factories.rabbitmq('rabbitmq_proc')
