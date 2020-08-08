#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-17
# @Filename: model.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import json
import pathlib

import jsonschema

from .tools import CallbackMixIn, CaseInsensitiveDict


__all__ = ['Reply', 'Property', 'BaseModel', 'Model', 'ModelSet']


class Reply(object):
    """A container for a `~aio_pika.IncomingMessage` that expands and decodes it.

    Parameters
    ----------
    message : aio_pika.IncomingMessage
        The message that contains the reply.
    ack : bool
        Whether to acknowledge the message.

    Attributes
    ----------
    is_valid : bool
        Whether the message is valid and correctly parsed.
    body : dict
        The body of the message, as a JSON dictionary.
    info : dict
        The info dictionary.
    headers : dict
        The headers of the message, decoded if they are bytes.
    message_code : str
        The message code.
    sender : str
        The name of the actor that sends the reply.
    command_id
        The command ID.

    """

    def __init__(self, message, ack=True):

        self.message = message

        self.is_valid = True

        self.body = None

        # Acknowledges receipt of message
        if ack:
            message.ack()

        self.info = message.info()

        self.headers = self.info['headers']
        for key in self.headers:
            if isinstance(self.headers[key], bytes):
                self.headers[key] = self.headers[key].decode()

        self.message_code = self.headers.get('message_code', None)
        if self.message_code is None:
            self.log.warning(f'received message without message_code: {message}')

        self.sender = self.headers.get('sender', None)
        if self.sender is None:
            self.log.warning(f'received message without sender: {message}')

        self.command_id = message.correlation_id

        command_id_header = self.headers.get('command_id', None)
        if command_id_header and command_id_header != self.command_id:
            self.log.error(f'mismatch between message '
                           f'correlation_id={self.command_id} '
                           f'and header command_id={command_id_header} '
                           f'in message {message}')
            self.is_valid = False
            return

        self.body = json.loads(self.message.body.decode())


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

    def to_json(self):
        """Returns a JSON-valid ``{key: value}`` dictionary."""

        return {self.name: self.value}


class BaseModel(CaseInsensitiveDict, CallbackMixIn):
    """A JSON-compliant model.

    Parameters
    ----------
    name : str
        The name of the model.
    callback
        A function or coroutine to call when the datamodel changes. The
        function is called with the instance of `BaseModel` and the key that
        changed.
    log : ~logging.Logger
        Where to log messages.

    """

    def __init__(self, name, callback=None, log=None):

        self.name = name

        self.callback = callback

        self.log = log

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

        return {key: self[key].to_json() for key in self}

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

    VALIDATOR = jsonschema.Draft7Validator

    def __init__(self, name, schema, **kwargs):

        self.schema = schema

        if not self.check_schema(schema, is_file=False):
            raise ValueError(f'schema {name!r} is invalid.')

        self.validator = self.VALIDATOR(self.schema)

        super().__init__(name, **kwargs)

        for name in self.schema['properties']:
            self[name] = Property(name, model=self)

    @staticmethod
    def check_schema(schema, is_file=False):
        """Checks whether a JSON schema is valid.

        Parameters
        ----------
        schema : str or dict
            The schema to check. It can be a JSON dictionary or the path to a
            file.
        is_file : bool
            Whether the input schema is a filepath or not.

        Returns
        -------
        result : `bool`
            Returns `True` if the schema is a valid JSON schema, `False`
            otherwise.

        """

        if is_file:
            schema = json.load(open(pathlib.Path(schema).expanduser(), 'r'))
        elif not is_file and isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except json.JSONDecodeError:
                raise ValueError('cannot parse input schema.')

        try:
            Model.VALIDATOR.check_schema(schema)
            return True
        except jsonschema.SchemaError:
            return False

    def update_model(self, instance):
        """Validates a new instance and updates the model."""

        try:
            self.validator.validate(instance)
        except jsonschema.exceptions.ValidationError:
            if self.log:
                self.log.error(f'model {self.name} cannot be updated. '
                               f'Failed validating instance {instance}.')
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
    raise_exception : bool
        Whether to raise an exception if any of the models cannot be loaded.
    kwargs
        Keyword arguments to be passed to `Model`.

    Example
    -------

        >>> model_set = ModelSet('~/my_models', model_names=['sop', 'guider'])
        >>> model_set['sop']
        <Model (name='sop')>

    """

    def __init__(self, model_path, model_names, raise_exception=True, **kwargs):

        dict.__init__(self, {})

        self.log = kwargs.get('log', None)

        self.model_path = pathlib.Path(model_path).expanduser()

        for name in model_names:

            try:

                schema_path = self.model_path / f'{name}.json'
                assert schema_path.exists(), f'model path {schema_path} does not exist.'

                schema = json.load(open(schema_path))

                self[name] = Model(name, schema, **kwargs)

            except Exception as ee:

                if not raise_exception:
                    if self.log:
                        self.log.warning(f'cannot load model for actor {name!r}: {ee}')
                    continue
                raise
