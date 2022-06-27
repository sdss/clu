#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-17
# @Filename: model.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import json
import pathlib
import warnings
from copy import copy
from os import PathLike
from time import time

from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, cast

import jsonschema
import jsonschema.exceptions
import jsonschema.validators

import clu.base

from .exceptions import CluError, CluWarning
from .tools import CallbackMixIn, CaseInsensitiveDict


__all__ = ["Property", "BaseModel", "Model", "ModelSet"]


SchemaType = Union[Dict[str, Any], PathLike, str]

DEFAULT_SCHEMA = {
    "text": {"type": "string"},
    "schema": {"type": "string"},
    "version": {"type": "string"},
    "help": {
        "oneOf": [
            {"type": "array", "items": {"type": "string"}},
            {"type": "string"},
        ]
    },
    "error": {
        "oneOf": [
            {"type": "array", "items": {"type": "string"}},
            {"type": "string"},
            {
                "type": "object",
                "properties": {
                    "exception_module": {"type": "string"},
                    "exception_type": {"type": "string"},
                    "exception_message": {"type": "string"},
                },
            },
        ]
    },
    "yourUserID": {"type": "integer"},
    "UserInfo": {
        "type": "array",
        "items": [{"type": "integer"}, {"type": "string"}],
    },
    "num_users": {"type": "integer"},
}


class Property(CallbackMixIn):
    """A model property with callbacks.

    Parameters
    ----------
    name
        The name of the property.
    value
        The value of the property.
    model
        The parent model.
    callback
        The function or coroutine that will be called if the value of the key
        if updated. The callback is called with the instance of `Property`
        as the only argument. Note that the callback will be scheduled even
        if the value does not change.
    """

    def __init__(
        self,
        name: str,
        value: Optional[Any] = None,
        model: Optional[Any] = None,
        callback: Optional[Callable[[Any], Any]] = None,
    ):

        self.name = name
        self._value = value
        self.last_seen: float | None = None

        self.model = model
        self.in_schema: bool = True

        CallbackMixIn.__init__(self, [callback] if callback else [])

    def __repr__(self):
        return f"<{self.__class__.__name__!s} ({self.name}): {self.value}>"

    def __str__(self):
        return str(self.value)

    @property
    def value(self) -> Any:
        """The value associated to the key."""

        return self._value

    @value.setter
    def value(self, new_value: Any):
        """Sets the value of the key and schedules the callback."""

        self._value = new_value
        self.last_seen = time()
        self.notify(self.copy())

    def copy(self):
        """Returns a copy of self."""

        return copy(self)

    def flatten(self) -> Dict[str, Any]:
        """Returns a dictionary with the name and value of the property."""

        return {self.name: self.value}


T = TypeVar("T", bound=Property)


class BaseModel(CaseInsensitiveDict[T], CallbackMixIn):
    """A JSON-compliant model.

    Parameters
    ----------
    name
        The name of the model.
    callback
        A function or coroutine to call when the datamodel changes. The
        function is called with the flattened instance of `.BaseModel`
        and the key that changed.

    """

    def __init__(self, name: str, callback: Optional[Callable[[Any], Any]] = None):

        self.name = name
        self.last_seen = None

        CaseInsensitiveDict.__init__(self, {})
        CallbackMixIn.__init__(self, [callback] if callback else [])

    def __repr__(self):
        return f"<Model ({self.name})>"

    def __str__(self):
        return str(self.flatten())

    def flatten(self) -> Dict[str, Any]:
        """Returns a dictionary of values.

        Return a dictionary in which the `Property` instances are replaced
        with their values.
        """

        return {key: prop.value for key, prop in self.items()}

    def jsonify(self) -> str:
        """Returns a JSON string with the model."""

        return json.dumps(self.flatten())


class Model(BaseModel[Property]):
    """A model with JSON validation.

    In addition to the parameters in `.BaseModel`, the following parameters
    are accepted:

    Parameters
    ----------
    schema
        A valid JSON schema, to be used for validation.
    is_file
        Whether the input schema is a filepath or a dictionary.
    additional_properties
        Whether to allow additional properties in the schema, other than the
        ones defined by the schema. This parameter only is used if
        ``schema=None`` or if ``additionalProperties`` is not defined in
        the schema.
    kwargs
        Additional parameters to pass to `.BaseModel` on initialisation.

    """

    VALIDATOR = jsonschema.Draft7Validator

    def __init__(
        self,
        name: str,
        schema: SchemaType,
        is_file: bool = False,
        additional_properties: bool = False,
        **kwargs,
    ):

        if is_file:
            schema = cast(PathLike, schema)
            schema = open(pathlib.Path(schema).expanduser(), "r").read()

        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except json.JSONDecodeError:
                raise ValueError("cannot parse input schema.")

        self.schema = cast("Dict[str, Any]", schema)

        if not self.check_schema(self.schema):
            raise ValueError(f"schema {name!r} is invalid.")

        if (
            "type" not in self.schema
            or self.schema["type"] != "object"
            or "properties" not in self.schema
        ):
            raise ValueError("Schema must be of type object.")

        # All models must have these keys.
        for prop in DEFAULT_SCHEMA:
            if prop not in self.schema["properties"]:
                self.schema["properties"][prop] = DEFAULT_SCHEMA[prop]

        if "additionalProperties" not in self.schema:
            self.schema["additionalProperties"] = additional_properties

        type_checker = self.VALIDATOR.TYPE_CHECKER.redefine(
            "array", lambda checker, instance: isinstance(instance, (list, tuple))
        )
        self.VALIDATOR = jsonschema.validators.extend(
            self.VALIDATOR,
            type_checker=type_checker,
        )
        self.validator = self.VALIDATOR(self.schema)

        self._lock = asyncio.Lock()

        super().__init__(name, **kwargs)

        for name in self.schema["properties"]:
            self[name] = Property(name, model=self)

    @staticmethod
    def check_schema(schema: Dict[str, Any]) -> bool:
        """Checks whether a JSON schema is valid.

        Parameters
        ----------
        schema
            The schema to check as a dictionary.

        Returns
        -------
        result
            Returns `True` if the schema is a valid JSON schema, `False`
            otherwise.
        """

        try:
            Model.VALIDATOR.check_schema(schema)
            return True
        except jsonschema.SchemaError:
            return False

    def validate(self, instance: Dict[str, Any], update_model: bool = True):
        """Validates a new instance."""

        try:
            self.validator.validate(instance)
        except jsonschema.exceptions.ValidationError as err:
            return False, err

        if update_model:
            self.update_model(instance)

        return True, None

    def update_model(self, instance: Dict[str, Any]):
        """Validates a new instance and updates the model."""

        self.last_seen = time()

        for key, value in instance.items():
            if (
                key in self
                and isinstance(self[key].value, dict)
                and isinstance(value, dict)
            ):
                # Copy previous value and update it but then assign it to
                # force the callback in the property.
                new_value = self[key].value.copy()
                new_value.update(value)
                self[key].value = new_value
            else:
                # The enforcement of the schema is on the actor side. In
                # addition, there may be legal properties that we have not
                # considered, e.g., patternProperties. If the key is not
                # in the Model, we add it as a new property.
                if key not in self:
                    self[key] = Property(key, model=self)
                    self[key].in_schema = False

                self[key].value = value

            self.notify(self.flatten().copy(), self[key].copy())


class ModelSet(dict):
    """A dictionary of `.Model` instances.

    Given a list of ``actors``, queries each of the actors to return their
    own schemas, which are then parsed and loaded as `.Model` instances.
    Since obtaining the schema require sending a command to the actor, that
    process happens when the coroutine `.load_schemas` is awaited, which
    should usually occur when the client is started.

    Parameters
    ----------
    client
        A client with a connection to the actors to monitor.
    actors
        A list of actor models whose schemas will be loaded.
    get_schema_command
        The command to send to the actor to get it to return its own schema.
    raise_exception
        Whether to raise an exception if any of the models cannot be loaded.
    kwargs
        Keyword arguments to be passed to `Model`.

    Example
    -------

        >>> model_set = ModelSet(client, actors=['sop', 'guider'])
        >>> model_set['sop']
        <Model (name='sop')>

    """

    def __init__(
        self,
        client: clu.base.BaseClient,
        actors: List[str] = [],
        get_schema_command: str = "get_schema",
        raise_exception: bool = True,
        **kwargs,
    ):

        dict.__init__(self, {})

        self.client = client
        self.actors = actors

        self.__raise_exception = raise_exception
        self.__get_schema_command = get_schema_command
        self.__kwargs = kwargs

    async def load_schemas(self, actors: Optional[List[str]] = None):
        """Loads the actor schames."""

        actors = actors or self.actors or []
        schema = None

        for actor in actors:

            try:

                cmd = await self.client.send_command(actor, self.__get_schema_command)
                await cmd

                if cmd.status.did_fail:
                    raise CluError(f"Failed getting schema for {actor}.")
                else:
                    for reply in cmd.replies:
                        if "schema" in reply.message:
                            schema = json.loads(reply.message["schema"])
                            break
                    if schema is None:
                        raise CluError(f"{actor} did not reply with a model.")

                self[actor] = Model(actor, schema, **self.__kwargs)

            except Exception as err:

                if not self.__raise_exception:
                    warnings.warn(f"Cannot load model {actor!r}. {err}", CluWarning)
                    continue
                raise
