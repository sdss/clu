#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-17
# @Filename: model.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)
#
# @Last modified by: José Sánchez-Gallego (gallegoj@uw.edu)
# @Last modified time: 2019-05-17 18:31:06

import json
import pathlib

import jsonschema

from .base import CallbackScheduler, CaseInsensitiveDict


__all__ = ['Property', 'BaseModel', 'Model']


class Property(object):
    """A model property with callbacks.

    Parameters
    ----------
    key
        The property to be represented.
    model : BaseModel
        The parent model.
    callback
        The function or coroutine that will be called if the value of the key
        if modified. The callback is called with the instance of `BaseProperty`
        as the only argument. Note that the callback will be scheduled even
        if the new value is the same as the previous one.

    """

    def __init__(self, key, model=None, callback=None):

        self.key = key
        self._value = None

        self.model = model

        self.scheduler = CallbackScheduler()
        self.callback = callback

    def __repr__(self):
        return f'<{self.__class__.__name__!s} ({self.key}): {self.value}>'

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

        if self.callback:
            self.scheduler.add_callback(self.callback, self)


class BaseModel(CaseInsensitiveDict):
    """A JSON-compliant model.

    Parameters
    ----------
    name : str
        The name of the model.
    callback
        A function or coroutine to call when the datamodel changes. The
        function is called with the instance of `BaseModel` as the only
        parameter. If the callback is a coroutine, it is scheduled as a task.
    log : ~logging.Logger
        Where to log messages.

    """

    def __init__(self, name, callback=None, log=None):

        self.name = name

        self.callback = callback
        self.scheduler = CallbackScheduler()

        self.log = log

        CaseInsensitiveDict.__init__(self, {})

    def __repr__(self):
        return f'Model ({self.name}):\n\t {str(dict(self))}'

    def flatten(self):
        """Returns a dictionary of values.

        Return a dictionary in which the `TronKey` instances are replaced
        with their values.

        """

        return {key: self[key].value for key in self}

    def jsonify(self):
        """Returns a JSON string with the model."""

        return json.dumps(self.unkey())


class Model(BaseModel):
    """A model with JSON validation.

    In addition to the parameters in `.BaseModel`, the following parameters
    are accepted:

    Parameters
    ----------
    schema : dict
        A valid JSON schema, to be used for validation.

    """

    def __init__(self, name, schema, **kwargs):

        self.schema = schema

        self.validator = jsonschema.Draft3Validator(self.schema)
        self.validator.check_schema(self.schema)

        super().__init__(name, **kwargs)

        for key in self.schema['properties']:
            self[key] = Property(key, model=self)

    def update_model(self, instance):
        """Validates a new instance and updates the model."""

        try:
            self.validator.validate(instance)
        except jsonschema.exceptions.ValidationError:
            if self.log:
                self.log.error(f'model cannot be updated. '
                               f'Failed validating {instance}.')
            return False

        for key, value in instance.items():
            self[key].value = value

        if self.callback:
            self.scheduler.add_callback(self.callback, self)

        return True


class ModelSet(dict):
    """A dictionary of `Model` instances from files.

    Reads model schemas from files and creates a dictionary of `Model`
    instances.

    Parameters
    ----------
    model_path : str or pathlib.Path
        The path to the directory containing the schema files. Each schema
        file must be named as the model and have extension ``.json``
        (e.g., ``sop.json``).
    model_names : list
        A list of models whose schemas will be loaded.
    kwargs
        Keyword arguments to be passed to `Model`.

    Example
    -------
    ::
        >>> model_set = ModelSet('~/my_models', model_names=['sop', 'guider'])
        >>> model_set['sop']
        Model([('test', <Property (text): None>), ...

    """

    def __init__(self, model_path, model_names, **kwargs):

        dict.__init__(self, {})

        self.model_path = pathlib.Path(model_path).expanduser()

        for name in model_names:
            schema_path = self.model_path / f'{name}.json'
            assert schema_path.exists()

            schema = json.load(open(schema_path))

            self[name] = Model(name, schema, **kwargs)
