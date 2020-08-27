#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-08-26
# @Filename: conftest.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from pytest_rabbitmq import factories

rabbitmq_proc = factories.rabbitmq_proc(port=None)
rabbitmq = factories.rabbitmq('rabbitmq_proc')
