#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-17
# @Filename: model.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import json
import pathlib
import warnings

import jsonschema

from .exceptions import CluError, CluWarning
from .tools import CallbackMixIn, CaseInsensitiveDict


__all__ = ['Property', 'BaseModel', 'Model', 'ModelSet']


class Property(CallbackMixIn):
    """A model property with callbacks.

    Parameters
    ----------
    name
        The name of the property.
    value
        The value of the property.
    model : BaseModel
        The parent model.
    callback
        The function or coroutine that will be called if the value of the key
        if updated. The callback is called with the instance of `Property`
        as the only argument. Note that the callback will be scheduled even
        if the value does not change.

    """

    def __init__(self, name, value=None, model=None, callback=None):

        self.name = name
        self._value = value

        self.model = model

        CallbackMixIn.__init__(self, [callback] if callback else [])

    def __repr__(self):
        return f'<{self.__class__.__name__!s} ({self.name}): {self.value}>'

    def __str__(self):
        return str(self.value)

    @property
    def value(self):
        """The value associated to the key."""

        return self._value

    @value.setter
    def value(self, new_value):
        """Sets the value of the key and schedules the callback."""

        self._value = new_value
        self.notify(self)

    def flatten(self):
        """Returns a dictionary with the name and value of the property."""

        return {self.name: self.value}


class BaseModel(CaseInsensitiveDict, CallbackMixIn):
    """A JSON-compliant model.

    Parameters
    ----------
    name : str
        The name of the model.
    callback
        A function or coroutine to call when the datamodel changes. The
        function is called with the instance of `.BaseModel` and the key that
        changed.

    """

    def __init__(self, name, callback=None, log=None):

        self.name = name

        CaseInsensitiveDict.__init__(self, {})
        CallbackMixIn.__init__(self, [callback] if callback else [])

    def __repr__(self):
        return f'<Model ({self.name})>'

    def __str__(self):
        return str(self.flatten())

    def flatten(self):
        """Returns a dictionary of values.

        Return a dictionary in which the `Property` instances are replaced
        with their values.

        """

        return {key: prop.value for key, prop in self.items()}

    def jsonify(self):
        """Returns a JSON string with the model."""

        return json.dumps(self.flatten())


class Model(BaseModel):
    """A model with JSON validation.

    In addition to the parameters in `.BaseModel`, the following parameters
    are accepted:

    Parameters
    ----------
    schema : dict
        A valid JSON schema, to be used for validation.
    is_file : bool
        Whether the input schema is a filepath or a dictionary.

    """

    VALIDATOR = jsonschema.Draft7Validator

    def __init__(self, name, schema, is_file=False, **kwargs):

        if is_file:
            schema = open(pathlib.Path(schema).expanduser(), 'r').read()

        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except json.JSONDecodeError:
                raise ValueError('cannot parse input schema.')

        self.schema = schema

        if not self.check_schema(self.schema):
            raise ValueError(f'schema {name!r} is invalid.')

        self.validator = self.VALIDATOR(self.schema)

        if ('type' not in self.schema or self.schema['type'] != 'object' or
                'properties' not in self.schema):
            raise ValueError('Schema must be of type object.')

        # All models must have these keys.
        props = self.schema['properties']
        for default_prop in ['text', 'error', 'schema', 'version']:
            if default_prop not in props:
                props[default_prop] = {'type': 'string'}
        if 'help' not in props:
            props['help'] = {'type': 'array'}

        super().__init__(name, **kwargs)

        for name in props:
            self[name] = Property(name, model=self)

    @staticmethod
    def check_schema(schema):
        """Checks whether a JSON schema is valid.

        Parameters
        ----------
        schema : dict
            The schema to check as a dictionary.

        Returns
        -------
        result : `bool`
            Returns `True` if the schema is a valid JSON schema, `False`
            otherwise.

        """

        try:
            Model.VALIDATOR.check_schema(schema)
            return True
        except jsonschema.SchemaError:
            return False

    def update_model(self, instance):
        """Validates a new instance and updates the model."""

        try:
            self.validator.validate(instance)
        except jsonschema.exceptions.ValidationError as err:
            return False, err

        for key, value in instance.items():
            if key in self:
                self[key].value = value

        self.notify(self)

        return True, None


class ModelSet(dict):
    """A dictionary of `.Model` instances.

    Given a list of ``actors``, queries each of the actors to return their
    own schemas, which are then parsed and loaded as `.Model` instances.
    Since obtaining the schema require sending a command to the actor, that
    process happens when the coroutine `.load_schemas` is awaited, which
    should usually occur when the client is started.

    Parameters
    ----------
    client : .BaseClient
        A client with a connection to the actors to monitor.
    actors : list
        A list of actor models whose schemas will be loaded.
    get_schema_command : str
        The command to send to the actor to get it to return its own schema.
    raise_exception : bool
        Whether to raise an exception if any of the models cannot be loaded.
    kwargs
        Keyword arguments to be passed to `Model`.

    Example
    -------

        >>> model_set = ModelSet(client, actors=['sop', 'guider'])
        >>> model_set['sop']
        <Model (name='sop')>

    """

    def __init__(self, client, actors=None, get_schema_command='get_schema',
                 raise_exception=True, **kwargs):

        dict.__init__(self, {})

        self.client = client
        self.actors = actors

        self.__raise_exception = raise_exception
        self.__get_schema = get_schema_command
        self.__kwargs = kwargs

    async def load_schemas(self, actors=None):
        """Loads the actor schames."""

        actors = actors or self.actors or []
        schema = None

        for actor in actors:

            try:

                cmd = await self.client.send_command(actor, self.__get_schema)
                await cmd

                if cmd.status.did_fail:
                    raise CluError(f'Failed getting schema for {actor}.')
                else:
                    for reply in cmd.replies:
                        if 'schema' in reply.body:
                            schema = json.loads(reply.body['schema'])
                            break
                    if schema is None:
                        raise CluError(f'{actor} did not reply with a model.')

                self[actor] = Model(actor, schema, **self.__kwargs)

            except Exception as err:

                if not self.__raise_exception:
                    warnings.warn(f'Cannot load model {actor!r}. {err}',
                                  CluWarning)
                    continue
                raise
