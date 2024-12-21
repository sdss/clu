#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-09-12
# @Filename: test_model.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import enum
import pathlib

import pytest
from pydantic import BaseModel

from clu.model import Model


def test_model_fails():
    with pytest.raises(ValueError):
        Model("test_model", "{1}")


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
        Model("test_model", INVALID_SCHEMA)

    assert str(err.value) == "schema 'test_model' is invalid."


def test_schema_no_type():
    with pytest.raises(ValueError) as err:
        Model("test_model", "{}")

    assert str(err.value) == "Schema must be of type object."


def test_schema_bad_type():
    with pytest.raises(ValueError) as err:
        Model("test_model", '{"type": "array"}')

    assert str(err.value) == "Schema must be of type object."


def test_schema_no_properties():
    with pytest.raises(ValueError) as err:
        Model("test_model", '{"type": "object"}')

    assert str(err.value) == "Schema must be of type object."


def test_schema_array():
    schema = """
    {
        "type": "object",
        "properties": { "myarray": { "type": "array" } }
    }
    """

    model = Model("test_model", schema)

    assert model.validate({"myarray": [1, 2, 3]})[0] is True
    assert model.validate({"myarray": (1, 2, 3)})[0] is True


def test_schema_pydantic():
    class TestEnum(enum.Enum):
        A = "a"
        B = "b"

    class TestSchema(BaseModel):
        key1: int
        key2: TestEnum

    schema = Model("test_model", TestSchema)
    assert isinstance(schema.schema, dict)

    assert schema.validate({"key1": 1, "key2": "a"})[0] is True
    assert schema.validate({"key1": 1, "key2": "c"})[0] is False


def test_schema_file(tmp_path: pathlib.Path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(
        '{"type": "object", "properties": { "key": { "type": "number" } }}'
    )

    schema = Model("test_model", schema_path)
    assert schema.validate({"key": 1})[0] is True


@pytest.mark.asyncio
async def test_model_update_dict():
    schema = """
    {
        "type": "object",
        "properties": { "prop": { "type": "object" } }
    }
    """

    model = Model("test_model", schema)

    model.update_model({"prop": {"subprop1": 1, "subprop2": 2}})
    assert model["prop"].value == {"subprop1": 1, "subprop2": 2}

    assert model["prop"].last_seen is not None
    assert model.last_seen is not None

    model.update_model({"prop": {"subprop2": 5}})
    assert model["prop"].value == {"subprop1": 1, "subprop2": 5}


@pytest.mark.asyncio
async def test_update_model_simulataneous(mocker):
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}

    model = Model("test_model", schema)

    # This callback will only receive the first argument, the model.
    cb = mocker.MagicMock()
    model.register_callback(cb)

    model.update_model({"text": "hi"})
    model.update_model({"text": "bye"})

    await asyncio.sleep(0.01)

    assert cb.call_args_list[0].args[0]["text"] == "hi"
    assert cb.call_args_list[1].args[0]["text"] == "bye"


async def test_update_model_key_not_in_schema():
    schema = """
    {
        "type": "object",
        "properties": { "prop": { "type": "object" } }
    }
    """

    model = Model("test_model", schema)

    model.update_model({"another_property": 5})

    assert "another_property" in model
    assert model["another_property"].value == 5
    assert model["another_property"].in_schema is False
