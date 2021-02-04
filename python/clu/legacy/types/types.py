"""
Type declarations for SDSS-3 keyword values

Refer to https://trac.sdss3.org/wiki/Ops/Types
"""

# type: ignore

# Created 30-Oct-2008 by David Kirkby (dkirkby@uci.edu)

import re
import textwrap

from . import html, pvt


class ValueTypeError(Exception):
    pass


class InvalidValueError(Exception):
    """
    Signals that an invalid value was detected during conversion from a string
    """

    pass


class Descriptive(object):
    """
    A self-describing type mixin

    Types that use this mixin are responsible for filling an array cls.descriptors
    of tuples (label,value) in their constructor.
    """

    def describe(self):
        """
        Returns a plain-text multi-line description

        The final newline character is omitted so that the return value
        can be printed. The description is indented with spaces assuming
        a fixed-width font.
        """
        text = ""
        for label, value in self.descriptors:
            pad = "\n" + " " * 14
            formatted = textwrap.fill(textwrap.dedent(value).strip(), width=66).replace(
                "\n", pad
            )
            text += "%12s: %s\n" % (label, formatted)
        return text[:-1]

    def describeAsHTML(self):
        """
        Returns a description packaged as an HTML fragment

        Uses the following CSS elements: div.vtype, div.descriptor,
        span.label, span.value
        """
        content = html.Div(className="vtype")
        for label, value in self.descriptors:
            content.append(
                html.Div(
                    html.Span(label, className="label"),
                    html.Span(value, className="value"),
                    className="type descriptor",
                )
            )
        return content


class ValueType(type, Descriptive):
    """
    A metaclass for types that represent an enumerated or numeric value
    """

    _nameSpec = re.compile("[A-Za-z][A-Za-z0-9_]*")
    _metaKeys = ("reprFmt", "strFmt", "invalid", "units", "help", "name")

    def __new__(cls, *args, **kwargs):
        """
        Allocates memory for a new ValueType class
        """

        def doRepr(self):
            if self.units:
                units = " " + self.units
            else:
                units = ""
            if self.reprFmt:
                return "%s(%s%s)" % (cls.__name__, self.reprFmt % self, units)
            else:
                return "%s(%s%s)" % (cls.__name__, cls.baseType.__repr__(self), units)

        def doStr(self):
            if self.strFmt:
                return self.strFmt % self
            elif self.reprFmt:
                return self.reprFmt % self
            else:
                return cls.baseType.__str__(self)

        # check for any invalid metadata keys
        for key in kwargs:
            if key not in ValueType._metaKeys and (
                not hasattr(cls, "customKeys") or key not in cls.customKeys
            ):
                raise ValueTypeError(
                    'invalid metadata key "%s" for %s' % (key, cls.__name__)
                )

        # force the invalid string, if present, to be lowercase
        if "invalid" in kwargs:
            kwargs["invalid"] = str(kwargs["invalid"]).lower()

        # check that the name string, if present, is a valid identifier
        if "name" in kwargs:
            matched = ValueType._nameSpec.match(kwargs["name"])
            if not matched or not matched.end() == len(kwargs["name"]):
                raise ValueTypeError("invalid type name: %s" % kwargs["name"])

        # check that any format strings provided are not circular
        if "reprFmt" in kwargs:
            fmt = kwargs["reprFmt"]
            if (fmt.find("%s") != -1) or (fmt.find("%r") != -1):
                raise ValueTypeError("reprFmt cannot contain %r or %s")
        if "strFmt" in kwargs:
            fmt = kwargs["strFmt"]
            if (fmt.find("%s") != -1) or (fmt.find("%r") != -1):
                raise ValueTypeError("strFmt cannot contain %r or %s")

        def get(name, default=None):
            return kwargs.get(name, cls.__dict__.get(name, default))

        dct = {
            "reprFmt": get("reprFmt"),
            "strFmt": get("strFmt"),
            "invalid": get("invalid"),
            "units": get("units"),
            "help": get("help"),
            "name": get("name"),
            "__repr__": doRepr,
            "__str__": doStr,
        }
        if cls == Bits:
            # leave special bit handling alone, since some code may rely on it
            def getNative(self):
                return int(self)

            dct["native"] = property(getNative)
        elif cls == Bool:
            # cls.baseType is int, not bool, because one cannot subclass bool
            def getNative(self):
                return bool(self)

            dct["native"] = property(getNative)
        elif hasattr(cls, "baseType"):

            def getNative(self):
                return cls.baseType(self)

            dct["native"] = property(getNative)
        else:
            print("WARNING: no baseType")

        if hasattr(cls, "new"):
            dct["__new__"] = cls.new
        if hasattr(cls, "init"):
            cls.init(dct, *args, **kwargs)
        return type.__new__(cls, cls.__name__, (cls.baseType,), dct)

    def addDescriptors(cls):
        if cls.units:
            cls.descriptors.append(("Units", cls.units))

    def __init__(cls, *args, **kwargs):
        """
        Initializes a new ValueType class
        """
        super(ValueType, cls).__init__(cls.__name__, (cls.baseType,), {})
        cls.descriptors = []
        if cls.name:
            cls.descriptors.append(("Name", cls.name))
        if cls.help:
            cls.descriptors.append(("Description", cls.help))
        cls.descriptors.append(
            ("Type", "%s (%s,%s)" % (cls.__name__, cls.baseType.__name__, cls.storage))
        )
        cls.addDescriptors()
        if cls.invalid:
            cls.descriptors.append(("Invalid", cls.invalid))

    def __mul__(self, amount):
        if isinstance(amount, int):
            return RepeatedValueType(self, amount, amount)
        elif not isinstance(amount, tuple):
            raise TypeError("Cannot multiply ValueType by type %r" % type(amount))
        if len(amount) == 0 or len(amount) > 2:
            raise ValueTypeError(
                "Repetions should be specified as *(min,) or *(min,max)"
            )
        minRepeat = amount[0]
        if len(amount) == 2:
            maxRepeat = amount[1]
        else:
            maxRepeat = None
        return RepeatedValueType(self, minRepeat, maxRepeat)

    def __repr__(self):
        return self.__name__

    def validate(self, value):
        if self.invalid and str(value).lower() == self.invalid:
            raise InvalidValueError
        return value


class RepeatedValueType(Descriptive):
    def __init__(self, vtype, minRepeat, maxRepeat):
        if not isinstance(vtype, ValueType):
            raise ValueTypeError("RepeatedValueType only works for a ValueType")
        self.vtype = vtype
        if not isinstance(minRepeat, int) or (
            maxRepeat and not isinstance(maxRepeat, int)
        ):
            raise ValueTypeError(
                "Expected integer min/max repetitions for RepeatedValueType"
            )
        self.minRepeat = minRepeat
        self.maxRepeat = maxRepeat
        if self.minRepeat < 0 or (self.maxRepeat and self.maxRepeat < self.minRepeat):
            raise ValueTypeError("Expected min <= max for RepeatedValueType")
        if self.minRepeat == 1:
            times = "once"
        else:
            times = "%d times" % self.minRepeat
        if self.minRepeat == self.maxRepeat:
            repeatText = times
        elif self.maxRepeat is None:
            repeatText = "at least " + times
        else:
            repeatText = "%d-%d times" % (self.minRepeat, self.maxRepeat)
        self.descriptors = [("Repeated", repeatText)]
        self.descriptors.extend(self.vtype.descriptors)

    def __repr__(self):
        if self.minRepeat == self.maxRepeat:
            return "%r*%d" % (self.vtype, self.minRepeat)
        elif self.maxRepeat is None:
            return "%r*(%d,)" % (self.vtype, self.minRepeat)
        else:
            return "%r*(%d,%d)" % (self.vtype, self.minRepeat, self.maxRepeat)


class CompoundValueType(Descriptive):
    """
    Represents a compound type consisting of a sequence of simple types

    A compound value is normally represented by a single object. By default,
    the wrapping object is a tuple containing the individual values but a
    custom object can be used via the 'wrapper' keyword which should provide
    a function (which might be a class constructor) that is called with the
    individual values and returns the wrapping object.
    """

    # a global flag to enable/disable the wrapping of compound values
    WrapEnable = True

    def __init__(self, *vtypes, **kwargs):
        self.vtypes = vtypes
        self.name = kwargs.get("name", None)
        self.help = kwargs.get("help", None)
        self.descriptors = []
        if self.name:
            self.descriptors.append(("Name", self.name))
        if self.help:
            self.descriptors.append(("Description", self.help))
        for index, vtype in enumerate(self.vtypes):
            self.descriptors.append(("Subtype-%d" % index, "-" * 40))
            self.descriptors.extend(vtype.descriptors)
        self.wrapper = kwargs.get("wrapper", None)

    def __repr__(self):
        return "%s%r" % (self.__class__.__name__, self.vtypes)


class PVT(CompoundValueType):
    """
    Represents a position-velocity-time compound type
    """

    def __init__(self, **kwargs):
        vtypes = (
            Float(name="position", units="deg"),
            Float(name="velocity", units="deg/s"),
            Double(name="time", units="MJD-secs(TAI)"),
        )
        if "wrapper" not in kwargs:
            # by default, use RO.PVT to wrap values of type PVT

            kwargs["wrapper"] = pvt.PVT
        CompoundValueType.__init__(self, *vtypes, **kwargs)


class Invalid(object):
    """
    Represents an invalid value
    """

    units = ""
    native = None

    def __repr__(self):
        return "(invalid)"

    def __eq__(self, other):
        """
        All Invalid instances are equal to each other and to None
        """
        return isinstance(other, Invalid) or other is None

    def __ne__(self, other):
        return not self.__eq__(other)


# a constant object representing an invalid value
InvalidValue = Invalid()


class Float(ValueType):
    baseType = float
    storage = "flt4"

    def new(cls, value):
        fvalue = float(cls.validate(value))
        # the limit value is float(340282346638528859811704183484516925440)
        # where 3402... is (2 - 2^(-23)) 2^127
        if abs(fvalue) > 3.4028234663852886e38 and abs(fvalue) != float("inf"):
            raise OverflowError("Invalid literal for Float: %r" % value)
        return float.__new__(cls, fvalue)


class Double(ValueType):
    baseType = float
    storage = "flt8"

    def new(cls, value):
        return float.__new__(cls, cls.validate(value))


class Int(ValueType):
    baseType = int
    storage = "int4"

    def new(cls, value):
        if isinstance(value, str):
            # base = 0 infers base from optional prefix (see PEP 3127)
            lvalue = int(cls.validate(value), 0)
        else:
            lvalue = int(cls.validate(value))
        if lvalue < -0x7FFFFFFF or lvalue > 0x7FFFFFFF:
            raise OverflowError("Invalid literal for Int: %r" % value)
        return int.__new__(cls, lvalue)


class Long(ValueType):
    baseType = int
    storage = "int8"

    def new(cls, value):
        if isinstance(value, str):
            # base = 0 infers base from optional prefix (see PEP 3127)
            return int.__new__(cls, cls.validate(value), 0)
        else:
            return int.__new__(cls, cls.validate(value))


class String(ValueType):
    baseType = str
    storage = "text"

    def new(cls, value):
        return str.__new__(cls, cls.validate(value))


class UInt(ValueType):
    baseType = int
    storage = "int4"

    def new(cls, value):
        if isinstance(value, str):
            # base = 0 infers base from optional prefix (see PEP 3127)
            lvalue = int(cls.validate(value), 0)
        else:
            lvalue = int(cls.validate(value))
        if lvalue < -0x7FFFFFFF or lvalue > 0xFFFFFFFF:
            raise OverflowError("Invalid literal for UInt: %r" % value)
        if lvalue < 0:
            # re-interpret a negative 32-bit value as its bit-equivalent unsigned value
            lvalue = 0x80000000 | (-lvalue)
        return int.__new__(cls, lvalue)


class Hex(UInt):
    """
    The Hex class has been deprecated and is scheduled for deletion (20-Jul-2009)
    """

    reprFmt = "0x%x"

    def new(cls, value):
        try:
            return int.__new__(cls, cls.validate(value), 16)
        except TypeError:
            return UInt.new(cls, value)


# Enumerated value type
class Enum(ValueType):

    baseType = str
    storage = "int2"
    customKeys = "labelHelp"

    @classmethod
    def init(cls, dct, *args, **kwargs):
        if not args:
            raise ValueTypeError("missing enum labels in ctor")
        # force each label to be interpreted as a string so, for example,
        # False->'False', 1->'1', 0xff->'255'
        strargs = [str(arg) for arg in args]
        dct["enumLabels"] = strargs
        dct["enumValues"] = dict(zip(args, range(len(strargs))))
        # look for optional per-label help text
        labelHelp = kwargs.get("labelHelp", None)
        if labelHelp and not len(labelHelp) == len(strargs):
            raise ValueTypeError("wrong number of enum label help strings provided")
        dct["labelHelp"] = labelHelp

        # provide a custom storage value helper since our storage type is int2
        # but our basetype is str
        def storageValue(self):
            return str(self.enumValues[self])

        dct["storageValue"] = storageValue

        # enumerated value comparisons are case insensitive
        def eqTest(self, other):
            return str(other).lower() == self.lower()

        def neTest(self, other):
            return str(other).lower() != self.lower()

        dct["__eq__"] = eqTest
        dct["__ne__"] = neTest

    def new(cls, value):
        """
        Initializes a new enumerated instance

        Value can either be an integer index or else a recognized label.
        """
        cls.validate(value)
        if isinstance(value, int):
            if value >= 0 and value < len(cls.enumLabels):
                return str.__new__(cls, cls.enumLabels[value])
            else:
                raise ValueError("Invalid index for Enum: %d" % value)
        value = str(value).lower()
        for label in cls.enumLabels:
            if value == label.lower():
                return str.__new__(cls, label)
        raise ValueError('Invalid label for Enum: "%s"' % value)

    def addDescriptors(cls):
        for index, label in enumerate(cls.enumLabels):
            description = label
            if cls.labelHelp:
                description += " (%s)" % cls.labelHelp[index]
            cls.descriptors.append(("Value-%d" % index, description))


# Boolean value type
class Bool(ValueType):

    baseType = int  # bool cannot be subclassed
    storage = "int2"

    @classmethod
    def init(cls, dct, *args, **kwargs):
        if not args or not len(args) == 2:
            raise ValueTypeError("missing true/false labels in ctor")
        # force the literal values to be interpreted as strings so, for example,
        # False->'False', 0->'0'
        dct["falseValue"] = str(args[0])
        dct["trueValue"] = str(args[1])

        def doStr(self):
            if self:
                return self.trueValue
            else:
                return self.falseValue

        dct["__str__"] = doStr
        if dct["strFmt"]:
            print("Bool: ignoring strFmt metadata")

    def new(cls, value):
        """
        Initializes a new boolean instance

        Value must be one of the true/false labels or else a True/False literal
        """
        cls.validate(value)
        # use (value == True) instead of (value is True) so that 0,1
        # can be used for False,True
        if value == True or value == cls.trueValue:  # noqa
            return int.__new__(cls, True)
        elif value == False or value == cls.falseValue:  # noqa
            return int.__new__(cls, False)
        else:
            raise ValueError("Invalid Bool value: %r" % value)

    def addDescriptors(cls):
        cls.descriptors.append(("False", cls.falseValue))
        cls.descriptors.append(("True", cls.trueValue))


# Bitfield value type
class Bits(UInt):

    fieldSpec = re.compile("([a-zA-Z0-9_]+)?(?::([0-9]+))?$")

    @staticmethod
    def binary(value, width):
        return "".join(
            [str((value >> shift) & 1) for shift in range(width - 1, -1, -1)]
        )

    @classmethod
    def init(cls, dct, *args, **kwargs):
        if not args:
            raise ValueTypeError("missing bitfield specs in ctor")
        offset = 0
        fields = {}
        specs = []
        for field in args:
            parsed = cls.fieldSpec.match(field)
            if not parsed or not parsed.end() == len(field):
                raise ValueTypeError("invalid bitfield spec: %s" % field)
            (name, width) = parsed.groups()
            width = int(width or 1)
            if name:
                if name == "native":
                    raise ValueTypeError("'native' is not an allowed bitfield name")
                specs.append((name, width))
                fields[name] = (offset, int((1 << width) - 1))
            offset += width
            if offset > 32:
                raise ValueTypeError("total bitfield length > 32")
        dct["width"] = offset
        dct["fieldSpecs"] = specs
        dct["bitFields"] = fields

        def getAttr(self, name):
            if name not in self.bitFields:
                raise AttributeError('no such bitfield "%s"' % name)
            (offset, mask) = self.bitFields[name]
            return (self >> offset) & mask

        dct["__getattr__"] = getAttr

        def setAttr(self, name, value):
            if name not in self.bitFields:
                raise AttributeError('no such bitfield "%s"' % name)
            (offset, mask) = self.bitFields[name]
            return self.__class__(
                (self & ~(mask << offset)) | ((value & mask) << offset)
            )

        dct["set"] = setAttr

        def doRepr(self):
            return "(%s)" % ",".join(
                [
                    "%s=%s" % (n, Bits.binary(getAttr(self, n), w))
                    for (n, w) in self.fieldSpecs
                ]
            )

        dct["__repr__"] = doRepr

        def bitsString(self):
            return Bits.binary(self, offset)

        dct["bitsString"] = bitsString
        # dct['__str__'] = doStr
        if dct["strFmt"]:
            print("Bits: ignoring strFmt metadata")

    def addDescriptors(cls):
        for index, (name, width) in enumerate(cls.fieldSpecs):
            offset, mask = cls.bitFields[name]
            shifted = Bits.binary(mask << offset, cls.width)
            cls.descriptors.append(("Field-%d" % index, "%s %s" % (shifted, name)))


class ByName(object):
    """
    Placeholder for type referred to by name
    """

    def __init__(self, name):
        self.name = name
