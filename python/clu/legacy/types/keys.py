"""
Core classes for SDSS-3 keyword validation

Refer to https://trac.sdss3.org/wiki/Ops/Validation for details.
"""

# Created 18-Nov-2008 by David Kirkby (dkirkby@uci.edu)

import collections
import hashlib
import importlib
import sys
import textwrap

from . import html as utilHtml
from . import messages as protoMess
from . import types as protoTypes


class KeysError(Exception):
    pass


class Consumer(object):
    """
    Consumes parsed messages
    """

    # set debug True to generate detailed tracing of all the consume activity
    debug = False

    indent = 0

    def trace(self, what):
        if self.debug:
            print('%s%r << %r' % (' ' * Consumer.indent, self, what))
            Consumer.indent += 1

    def passed(self, what):
        if self.debug:
            Consumer.indent -= 1
            print('%sPASS >> %r' % (' ' * Consumer.indent, what))
        return True

    def failed(self, reason):
        if self.debug:
            Consumer.indent -= 1
            print('%sFAIL: %s' % (' ' * Consumer.indent, reason))
        return False

    def consume(self, what):
        raise NotImplementedError


class TypedValues(Consumer):
    """
    Consumes typed command or keyword values
    """

    def __init__(self, vtypes):
        self.vtypes = []
        self.minVals = 0
        self.maxVals = 0
        for vtype in vtypes:
            if isinstance(vtype, protoTypes.RepeatedValueType):
                if vtype.minRepeat != vtype.maxRepeat and vtype is not vtypes[-1]:
                    raise KeysError('Repetition range only allowed for last value type')
                self.minVals += vtype.minRepeat
                if self.maxVals is not None and vtype.maxRepeat is not None:
                    self.maxVals += vtype.maxRepeat
                else:
                    self.maxVals = None
                self.vtypes.append(vtype)
            elif isinstance(vtype, protoTypes.ValueType):
                self.minVals += 1
                self.maxVals += 1
                self.vtypes.append(vtype)
            elif isinstance(vtype, protoTypes.CompoundValueType):
                self.minVals += len(vtype.vtypes)
                self.maxVals += len(vtype.vtypes)
                self.vtypes.append(vtype)
            elif isinstance(vtype, protoTypes.ByName):
                self.vtypes.append(vtype)
            else:
                raise KeysError('Invalid value type: %r' % vtype)
        if self.maxVals == 0:
            self.descriptor = 'none'
        elif self.maxVals == self.minVals:
            self.descriptor = self.minVals
        elif self.maxVals is None:
            self.descriptor = '%d or more' % self.minVals
        else:
            self.descriptor = '%d-%d' % (self.minVals, self.maxVals)

    def __repr__(self):
        return 'Types%r' % self.vtypes

    def consume(self, values):
        self.trace(values)
        # remember the original values in case we need to restore them later
        self.originalValues = protoMess.Values(values)
        values[:] = []
        # try to convert each keyword to its expected type
        self.index = 0
        for typeToConsume in self.vtypes:
            if isinstance(typeToConsume, protoTypes.RepeatedValueType):
                vtype = typeToConsume.vtype
                offset = 0
                while offset < typeToConsume.minRepeat:
                    if not self.consumeNextValue(vtype, values):
                        values[:] = self.originalValues
                        return self.failed('expected repeated value type %r' % typeToConsume)
                    offset += 1
                while typeToConsume.maxRepeat is None or offset < typeToConsume.maxRepeat:
                    if not self.consumeNextValue(vtype, values):
                        break
                    offset += 1
            elif isinstance(typeToConsume, protoTypes.ValueType):
                if not self.consumeNextValue(typeToConsume, values):
                    values[:] = self.originalValues
                    return self.failed('expected value type %r' % typeToConsume)
            elif isinstance(typeToConsume, protoTypes.CompoundValueType):
                for vtype in typeToConsume.vtypes:
                    if not self.consumeNextValue(vtype, values):
                        values[:] = self.originalValues
                        return self.failed('expected compound value type %r' % typeToConsume)
                # Optionally replace the values with a reference to a single object
                # initialized with the values. The default object is a tuple.
                if protoTypes.CompoundValueType.WrapEnable:
                    size = len(typeToConsume.vtypes)
                    wrapped = tuple(values[-size:])
                    if typeToConsume.wrapper:
                        wrapped = typeToConsume.wrapper(*wrapped)
                    values[-size:] = [wrapped]
            else:
                raise KeysError('Unexpected typeToConsume: %r' % typeToConsume)
        if self.index != len(self.originalValues):
            values[:] = self.originalValues
            return self.failed('not all values consumed: %s' % values[self.index:])
        return self.passed(values)

    def consumeNextValue(self, valueType, values):
        try:
            string = self.originalValues[self.index]
            try:
                values.append(valueType(string))
            except protoTypes.InvalidValueError:
                values.append(protoTypes.InvalidValue)
            self.index += 1
            return True
        except (IndexError, ValueError, TypeError, OverflowError):
            return False

    def describeAsHTML(self):
        content = utilHtml.Div(
            utilHtml.Div(
                utilHtml.Span('Values', className='label'),
                utilHtml.Span(self.descriptor, className='value'),
                className='key descriptor'),
            className='vtypes')
        for vtype in self.vtypes:
            content.append(utilHtml.Div(utilHtml.Entity('nbsp'), className='separator'))
            content.extend(vtype.describeAsHTML().children)
        return content

    def describe(self):
        text = '%12s: %s\n' % ('Values', self.descriptor)
        for vtype in self.vtypes:
            extra = vtype.describe().replace('\n', '\n    ')
            text += '\n    %s\n' % extra
        return text


class Key(Consumer):
    """
    Base class for a command or reply keyword consumer

    Inputs:
    - name: keyword name
    - a list of one or more value types
    - help: an optional help string
    - doCache: is it reasonable to read this value from a cache?
        defaults to True only if the keyword can have values and you do not specify refreshCmd
    - refreshCmd: an optional command that can be sent to the actor to refresh this value
    """

    def __init__(self, name, *vtypes, **metadata):
        self.name = name
        self.typedValues = TypedValues(vtypes)
        self.help = metadata.get('help', None)
        self.refreshCmd = metadata.get('refreshCmd', None)
        defDoCache = (self.typedValues.maxVals != 0) and not self.refreshCmd
        self.doCache = bool(metadata.get('doCache', defDoCache))
        if 'unique' in metadata:
            self.unique = metadata.get('unique')

    def __repr__(self):
        return 'Key(%s)' % self.name

    def consume(self, keyword):
        self.trace(keyword)
        # perform a case-insensitive name matching
        if keyword.name.lower() != self.name.lower():
            return self.failed('keyword has wrong name')
        if not self.typedValues.consume(keyword.values):
            return self.failed('no match for keyword values')
        keyword.matched = True
        return self.passed(keyword)

    def create(self, *values):
        """
        Returns a new Keyword using this Key as a template

        Any keyword values must match the expected types or else this
        method returns None. The returned keyword will have typed
        values.
        """
        if len(values) == 1 and isinstance(values[0], list):
            values = values[0]
        keyword = protoMess.Keyword(self.name, values)
        if not self.consume(keyword):
            raise KeysError('value types do not match for keyword %s: %r' % (self.name, values))
        return keyword

    def describeAsHTML(self):
        content = utilHtml.Div(utilHtml.Div(self.name, className='keyname'), className='key')
        desc = utilHtml.Div(className='keydesc')
        content.append(desc)
        if self.help:
            desc.append(
                utilHtml.Div(
                    utilHtml.Span('Description', className='label'),
                    utilHtml.Span(self.help, className='value'),
                    className='key descriptor'))
        desc.extend(self.typedValues.describeAsHTML().children)
        return content

    def describe(self):
        text = '%12s: %s\n' % ('Keyword', self.name)
        if self.help:
            pad = '\n' + ' ' * 14
            formatted = textwrap.fill(
                textwrap.dedent(self.help).strip(), width=66).replace('\n', pad)
            text += '%12s: %s\n' % ('Description', formatted)
        text += self.typedValues.describe()
        return text


class KeysManager(object):

    keys = {}

    # These need to be classmethods, not static methods, so that
    # subclasses each access their own keys list.
    @classmethod
    def setKeys(cls, kdict):
        cls.keys = {}
        cls.addKeys(kdict)

    @classmethod
    def addKeys(cls, kdict):
        if not isinstance(kdict, KeysDictionary):
            raise KeysError('Cmd keys must be provided as a KeysDictionary')
        cls.keys[kdict.name] = kdict

    @classmethod
    def getKey(cls, name):
        for kdict in cls.keys.values():
            if name in kdict:
                return kdict[name]
        raise KeysError('No such registered keyword <%s>' % name)


class CmdKey(Consumer, KeysManager):
    """
    Consumes a command keyword
    """

    def __init__(self, key):
        self.key = key

    def __repr__(self):
        return 'CmdKey(%s)' % self.key.name

    def consume(self, where):
        self.trace(where)
        keyword = where.keyword()
        if not keyword:
            return self.failed('no keywords available to consume')
        if not self.key.consume(keyword):
            return self.failed('no match for command keyword')
        where.advance()
        return self.passed(where)


class RawKey(Consumer):
    """
    Consumes the special 'raw' keyword in a command
    """

    def consume(self, where):
        self.trace(where)
        keyword = where.keyword()
        if not keyword:
            return self.failed('no keywords available to consume')
        if not isinstance(keyword, protoMess.RawKeyword):
            return self.failed('no match for raw keyword')
        # no re-casting as a typed value needed here
        where.advance()
        return self.passed(where)


class KeysDictionaryError(KeysError):
    pass


class KeysDictionary(object):
    """
    A collection of Keys associated with a given name

    The dictionary name is typically the name of an actor. Contains a
    registry of all known KeysDictionaries, for use by the load method.
    """
    registry = {}

    def __init__(self, name, version, *keys):
        """
        Creates a new named keys dictionary

        Overwrites any existing dictionary with the same name. The
        version should be specified as a (major,minor) tuple of
        integers. Dictionary names must be lower case.
        """
        self.name = name
        try:
            (major, minor) = map(int, version)
        except (ValueError, TypeError):
            raise KeysDictionaryError(
                'Invalid version: expected (major,minor) tuple of integers, got %r' % version)
        self.version = version
        if not name == name.lower():
            raise KeysDictionaryError('Invalid name: must be lower case: %s' % name)
        KeysDictionary.registry[name] = self
        self.keys = collections.OrderedDict()
        self.namedTypes = {}
        for key in keys:
            self.add(key)

    def add(self, key):
        """
        Adds a key to the dictionary

        By default, the key is registered under key.name but this can be
        overridden by setting a key.unique attribute. Attempting to
        add a key using a name that is already assigned raises an
        exception.
        """
        if not isinstance(key, Key):
            raise KeysDictionaryError('KeysDictionary can only contain Keys')
        name = getattr(key, 'unique', key.name)
        if name.lower() in self.keys:
            raise KeysDictionaryError('KeysDictionary name is not unique: %s' % name)
        # look for named types used by the key
        localNames = {}
        for index, vtype in enumerate(key.typedValues.vtypes):
            vname = getattr(vtype, 'name', None)
            if isinstance(vtype, protoTypes.ByName):
                try:
                    key.typedValues.vtypes[index] = self.namedTypes[vname]
                except KeyError:
                    raise KeysDictionaryError('Unresolved type ByName("%s")' % vname)
            elif vname:
                localNames[vname] = vtype
        # add this key's local names to our dictionary (ByName can only refer to
        # types defined in a previously-defined type to ensure unique names)
        self.namedTypes.update(localNames)
        # add this key
        self.keys[name.lower()] = key

    def extend(self, keyList):
        """Adds all the keys in a list."""

        assert isinstance(keyList, (list, tuple)), 'keyList must be a list or tuple'

        for key in keyList:
            self.add(key)

    def __getitem__(self, name):
        return self.keys[name.lower()]

    def __contains__(self, name):
        return name.lower() in self.keys

    def describe(self):
        """
        Generates text describing all of our keys in alphabetical order
        """
        text = 'Keys Dictionary for "%s" version %r\n' % (self.name, self.version)
        for name in sorted(self.keys):
            text += '\n' + self.keys[name].describe()
        return text

    def describeAsHTML(self):
        """
        Generates HTML describing all of our keys in alphabetical order
        """
        content = utilHtml.Div(
            utilHtml.Div(
                utilHtml.Span(self.name, className='actorName'),
                utilHtml.Span('%d.%d' % self.version, className='actorVersion'),
                className='actorHeader'),
            className='actor')
        for name in sorted(self.keys):
            content.append(self.keys[name].describeAsHTML())
        return content

    @staticmethod
    def load(dictname, forceReload=False):
        """
        Loads a KeysDictionary by name, returning the result

        Uses an in-memory copy, if one is available, otherwise loads the
        dictionary from disk. Use forceReload to force the dictionary to
        be loaded from disk even if it is already in memory. Raises a
        KeysDictionaryError if a dictionary cannot be found for dictname.
        """
        if not forceReload and dictname in KeysDictionary.registry:
            return KeysDictionary.registry[dictname]
        # try to find a corresponding file on the import search path
        try:
            # get the path corresponding to the actorkeys package
            import actorkeys  # noqa
            keyspath = sys.modules['actorkeys'].__path__
        except ImportError:
            raise KeysDictionaryError('no actorkeys package found')
        try:
            # open the file corresponding to the requested keys dictionary
            modulespec = importlib.util.find_spec('actorkeys.' + dictname, keyspath)
            # create a global symbol table for evaluating the keys
            # dictionary expression
            symbols = {
                '__builtins__': __builtins__,
                'Key': Key,
                'KeysDictionary': KeysDictionary,
                'ByName': protoTypes.ByName,
            }
            for (name, value) in protoTypes.__dict__.items():
                if isinstance(value, type) and issubclass(value, (protoTypes.ValueType,
                                                                  protoTypes.CompoundValueType)):
                    symbols[name] = value
            # evaluate the keys dictionary as a python expression
            filedata = open(modulespec.origin).read()
            kdict = eval(filedata, symbols)
            # check that the dictionary filename and name match
            if not dictname == kdict.name:
                raise KeysDictionaryError('dictionary filename and name '
                                          'are different: %s, %s' %
                                          (modulespec.name, kdict.name))
            # do a checksum so that we can detect changes
            # independently of versioning
            kdict.checksum = hashlib.md5(filedata.encode()).hexdigest()
            return kdict
        except ImportError as e:
            raise KeysDictionaryError('no keys dictionary found '
                                      'for %s: %s' % (dictname, str(e)))
        except Exception as e:
            indent = '\n >> '
            description = indent + indent.join(str(e).split('\n'))
            raise KeysDictionaryError('badly formatted keys '
                                      'dictionary in %s:%s' % (dictname,
                                                               description))
