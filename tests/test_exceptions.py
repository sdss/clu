#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-09-11
# @Filename: test_exceptions.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import pytest

from clu.exceptions import CluNotImplemented


def test_clu_not_implemented():
    with pytest.raises(CluNotImplemented) as err:
        raise CluNotImplemented()

    assert str(err.value) == "This feature is not implemented yet."
