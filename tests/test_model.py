#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-09-12
# @Filename: test_model.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import pytest

from clu.model import Model


def test_model_fails():

    with pytest.raises(ValueError):
        Model('test_model', '{1}')


def test_schema_validation_fails():

    INVALID_SCHEMA = """
{
    "title": "my json api",
    "description": "my json api",
    "type": "object",
    "properties": {
        "my_api_response": {
           "type": "object",
            "properties": {
                "MailboxInfo": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ADSyncLinkEnabled": {
                                "type": "any"
                            }
                        }
                    }
                }
            }
        }
    },
    "required": ["response"]
}
"""

    with pytest.raises(ValueError) as err:
        Model('test_model', INVALID_SCHEMA)

    assert str(err.value) == 'schema \'test_model\' is invalid.'


def test_schema_no_type():

    with pytest.raises(ValueError) as err:
        Model('test_model', '{}')

    assert str(err.value) == 'Schema must be of type object.'


def test_schema_bad_type():

    with pytest.raises(ValueError) as err:
        Model('test_model', '{"type": "array"}')

    assert str(err.value) == 'Schema must be of type object.'


def test_schema_no_properties():

    with pytest.raises(ValueError) as err:
        Model('test_model', '{"type": "object"}')

    assert str(err.value) == 'Schema must be of type object.'
