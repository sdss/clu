#!/usr/bin/env python
# encoding: utf-8
#
# @Author: José Sánchez-Gallego
# @Date: Jan 16, 2018
# @Filename: test_actor.py
# @License: BSD 3-Clause
# @Copyright: José Sánchez-Gallego


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import asyncio

from asyncioActor.actor import Actor


class TestActor(Actor):
    pass


actor = TestActor('asyncio_test_actor')

try:
    loop = asyncio.get_event_loop()
    loop.run_forever()
except KeyboardInterrupt:
    pass
