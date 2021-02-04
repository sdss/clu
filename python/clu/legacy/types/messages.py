"""
Message classes for SDSS-3 command and reply protocols

Refer to https://trac.sdss3.org/wiki/Ops/Messages for details.
"""

# type: ignore

# Created 10-Oct-2008 by David Kirkby (dkirkby@uci.edu)

import re

from . import types


class MessageError(Exception):
    pass


class Canonized(object):
    """
    Represents an object with a standard string representations

    The canonical string representation is used to define semantic
    equality via the __eq__ and __ne__ operators. The tokenized string
    representation defines grammatical equality.
    """

    def canonical(self):
        raise NotImplementedError

    def tokenized(self):
        raise NotImplementedError

    def __eq__(self, other):
        return isinstance(other, Canonized) and self.canonical() == other.canonical()

    def __ne__(self, other):
        return not isinstance(other, Canonized) or self.canonical() != other.canonical()


class Values(list, Canonized):
    """
    Represents the values associated with a command or keyword
    """

    # keyword or cmd values that do not match this pattern are quoted in canonical form
    unquoted = re.compile(r'[^"\'\s=,][^\s=,]*$')

    def canonical(self):
        """
        Returns the canonical string representation of a list of values

        Should not be used for the value associated with the "raw"
        keyword. A canonical value is quoted if it begins with a single
        or double quote or contains a comma, equals sign, or any inline
        white space. A single value is always quoted. A canonical string
        is, by definition, invariant under parsing.
        """
        result = ""
        for (comma, value) in enumerate(self):
            if comma:
                result += ","
            if isinstance(value, float):
                # use repr to capture the full precision
                value = repr(float(value))
            elif not isinstance(value, str):
                value = str(value)
            if self.unquoted.match(value) and (comma or len(self) > 1):
                # a lone value must be quoted so it is not confused with a keyword name
                result += value
            else:
                # only double quotes need to be escaped
                result += '"%s"' % value.decode("string_escape").replace('"', '\\"')
        return result

    def tokenized(self):
        """
        Returns the parse token representation of a list of values

        Should not be used for the value associated with the "raw"
        keyword. Does not distinguish between quoted and unquoted
        values. A tokenized string is invariant under parsing.
        """
        result = ""
        for (comma, value) in enumerate(self):
            if comma:
                result += ","
            result += "123"
        return result


class Keyword(Canonized):
    """
    Represents a keyword and its values
    """

    def __init__(self, name, values=None):
        """
        Creates a new keyword instance

        The "raw" keyword name (case insensitive) is reserved and must
        not be used. No checks are performed on the characters used in
        the name (the parser has normally already done this).
        """
        if name.lower() == "raw":
            raise MessageError('keyword "%s" is reserved' % name)
        self.name = name
        self.values = Values(values or [])
        self.matched = False

    def canonical(self):
        """
        Returns the canonical string representation of this keyword

        Two keywords with identical canonical strings are equivalent.
        The canonical form of a keyword name is all lower case. A
        canonical string is, by definition, invariant under parsing.
        """
        result = self.name.lower()
        if self.values and len(self.values) > 0:
            result += "=%s" % self.values.canonical()
        return result

    def tokenized(self):
        """
        Returns the parse token representation of a keyword

        Two keywords with identical tokenized strings have the same
        basic grammar. A tokenized string is invariant under parsing.
        """
        result = "KEY"
        if self.values and len(self.values) > 0:
            result += "=%s" % self.values.tokenized()
        return result

    def clone(self):
        """
        Returns a clone of this object
        """
        new = Keyword(self.name, self.values)
        new.matched = self.matched
        return new

    def copy(self, other):
        """
        Copies the attributes of another Keyword instance
        """
        self.name = other.name
        self.values = other.values
        self.matched = other.matched

    def __repr__(self):
        result = "KEY(%s)=%r" % (self.name, self.values)
        if self.matched:
            result = "{" + result + "}"
        return result

    def __getitem__(self, ii):
        """Returns the i-th value from the keyword."""

        return self.values[ii]

    # def __len__(self):
    #     """Returns the length of the values."""
    #
    #     return len(self.values)


class RawKeyword(Keyword):
    """
    Represents the reserved RAW keyword
    """

    def __init__(self, line):
        """
        Creates a new raw keyword instance
        """
        self.name = "raw"
        self.values = Values([line])
        self.matched = False

    def __repr__(self):
        result = "RAWKEY(%s)=%r" % (self.name, self.values)
        return result

    def canonical(self):
        """
        Returns the canonical string representation of a raw keyword
        """
        return "raw=%s" % self.values[0]

    def tokenized(self):
        """
        Returns the parse token representation of a raw keyword
        """
        return "RAW=LINE"

    def clone(self):
        """
        Returns a clone of this object
        """
        new = RawKeyword(self.values[0])
        new.matched = self.matched
        return new

    def copy(self, other):
        """
        Copies the attributes of another Keyword instance
        """
        self.values = other.values
        self.matched = other.matched


class Keywords(list, Canonized):
    """
    Represents an ordered set of keywords
    """

    def canonical(self, delimiter):
        """
        Returns the canonical string representation of a set of keywords

        Two sets of keywords with identical canonical strings are
        equivalent. Keyword ordering is considered to be significant. A
        canonical string is, by definition, invariant under parsing.
        """
        result = ""
        for delimited, keyword in enumerate(self):
            if delimited:
                result += delimiter
            result += keyword.canonical()
        return result

    def tokenized(self, delimiter):
        """
        Returns the parse token representation of a set of keywords

        Two sets of keywords with identical tokenized strings have the
        same basic grammar. Keyword ordering is considered to be
        significant. A tokenized string is invariant under parsing.
        """
        result = ""
        for delimited, keyword in enumerate(self):
            if delimited:
                result += delimiter
            result += keyword.tokenized()
        return result

    def clone(self):
        """
        Returns a clone of this object
        """
        new = Keywords()
        for keyword in self:
            new.append(keyword.clone())
        return new

    def copy(self, other):
        """
        Copies the keywords of another Keywords instance
        """
        del self[:]
        self.extend(other)

    def __getitem__(self, index):
        """
        Returns the keyword at the specified integer or string index

        An integer index returns a keyword by position starting from
        zero. A string index returns a keyword by name.
        """
        try:
            return list.__getitem__(self, index)
        except TypeError:
            if isinstance(index, str):
                name = index.lower()
                for k in self:
                    if k.name.lower() == name:
                        return k
                raise KeyError(index)
            raise TypeError("Keywords index must be integer or string")

    def get(self, name, default=None):
        """Returns the keyword matching name or default if not found."""

        for key in self:
            if key.name == name:
                return key

        return default

    def __getslice__(self, begin, end):
        """
        Returns a slice of ordered keywords via the usual list syntax
        """
        return Keywords(list.__getslice__(self, begin, end))

    def __contains__(self, name):
        """
        Tests if a keyword with the specified name is present
        """
        if isinstance(name, str):
            lower = name.lower()
            for k in self:
                if k.name.lower() == lower:
                    return True
            return False
        raise TypeError("Keyword names must be strings")


class ReplyHeader(Canonized):
    """
    Represents the headers of a reply
    """

    MsgCode = types.Enum(
        ">",
        "D",
        "I",
        "W",
        "E",
        ":",
        "F",
        "!",
        labelHelp=[
            "Queued",
            "Debug",
            "Information",
            "Warning",
            "Error",
            "Finished",
            "Error",
            "Fatal",
        ],
        name="code",
        help="Reply header status code",
    )

    def __init__(self, program, user, actorStack, commandId, actor, code):
        self.program = program
        self.user = user
        self.actorStack = actorStack
        # The commander name is the concatenation of the first three fields and should
        # exactly reproduce the initial word of the reply message string.
        self.cmdrName = "%s.%s%s" % (self.program, self.user, self.actorStack)
        self.commandId = int(commandId)
        self.actor = actor
        try:
            self.code = ReplyHeader.MsgCode(code)
        except ValueError:
            raise MessageError("Invalid reply header code: %s" % code)

    def canonical(self):
        return "%s %d %s %s" % (self.cmdrName, self.commandId, self.actor, self.code)

    def tokenized(self):
        return "prog.user 123 actor %s" % self.code

    def clone(self):
        return ReplyHeader(
            self.program, self.user, self.commandId, self.actor, self.code
        )

    def copy(self, other):
        self.program = other.program
        self.user = other.user
        self.commandId = other.commandId
        self.actor = other.actor
        self.code = other.code

    def __repr__(self):
        return "HDR(%s,%s,%d,%s,%s)" % (
            self.program,
            self.user,
            self.commandId,
            self.actor,
            self.code,
        )


class ActorReplyHeader(Canonized):
    """
    Represents the header of a reply from an actor (as opposed to the hub)
    """

    MsgCode = types.Enum(
        ">",
        "D",
        "I",
        "W",
        "E",
        ":",
        "F",
        "!",
        labelHelp=[
            "Queued",
            "Debug",
            "Information",
            "Warning",
            "Error",
            "Finished",
            "Error",
            "Fatal",
        ],
        name="code",
        help="Reply header status code",
    )

    def __init__(self, commandId, userId, code):
        self.commandId = int(commandId)
        self.userId = int(userId)
        try:
            self.code = ReplyHeader.MsgCode(code)
        except ValueError:
            raise MessageError("Invalid reply header code: %s" % code)

    def canonical(self):
        return "%d %d %s" % (self.commandId, self.userId, self.code)

    def tokenized(self):
        return "123 1 %s" % self.code

    def clone(self):
        return ReplyHeader(self.commandId, self.userId, self.code)

    def copy(self, other):
        self.commandId = other.commandId
        self.userId = other.userId
        self.code = other.code

    def __repr__(self):
        return "ACTHDR(%d,%d,%s)" % (self.commandId, self.userId, self.code)


class Reply(Canonized):
    """
    Represents a reply

    A reply consists of one or more keywords separated by semicolons.
    Keywords are ordered and duplicates do not generate a runtime
    exception.
    """

    def __init__(self, header, keywords, string=None):
        """
        Creates a new reply instance
        """
        self.header = header
        self.keywords = Keywords(keywords)
        self.string = string

    def canonical(self):
        """
        Returns the canonical string representation of this reply

        Two replies with identical canonical strings are equivalent. A
        canonical string is, by definition, invariant under parsing.
        """
        return "%s %s" % (
            self.header.canonical(),
            self.keywords.canonical(delimiter=";"),
        )

    def tokenized(self):
        """
        Returns the parse token representation of a reply

        Two replies with identical tokenized strings have the same
        basic grammar. A tokenized string is invariant under parsing.
        """
        return "%s %s" % (
            self.header.tokenized(),
            self.keywords.tokenized(delimiter=";"),
        )

    def clone(self):
        """
        Returns a clone of this object
        """
        new = Reply(header=self.header.clone(), keywords=[], string=self.string)
        new.keywords = self.keywords.clone()
        return new

    def copy(self, other):
        """
        Copies the keywords of another Keywords instance
        """
        self.header.copy(other.header)
        self.keywords = other.keywords
        self.string = other.string

    def __repr__(self):
        result = "REPLY(%r,%r)" % (self.header, self.keywords)
        return result


class CommandHeader(Canonized):
    """
    Represents the headers of a command
    """

    def __init__(self, cmdrName, mid, actor):
        self.cmdrName = cmdrName
        self.mid = mid
        self.actor = actor

    @property
    def program(self):
        """ Return program part of cmdrname. """
        return self.cmdrName.split(".", 1)[0]

    def canonical(self):
        return "%s %d %s" % (self.cmdrName, self.mid, self.actor)

    def tokenized(self):
        return "prog.user 123 actor %s" % self.actor

    def clone(self):
        return CommandHeader(self.cmdrName, self.mid, self.actor)

    def copy(self, other):
        self.cmdrName = other.cmdrName
        self.mid = other.mid
        self.actor = other.actor

    def __repr__(self):
        return "CommandHeader(%s,%d,%s)" % (self.cmdrName, self.mid, self.actor)


class Command(Canonized):
    """Represents a command

    A command consists of a name (verb) with optional values followed by
    zero or more keywords. Keywords are ordered and duplicates do not
    generate a runtime exception.

    """

    def __init__(self, name, values=None, keywords=None, string=None):
        """Creates a new command instance

        The name must not contain the dot (.) character and must not
        equal "raw" (case insensitive), but no other checks are
        performed on the characters used in the name (the parser has
        normally already done this).
        """
        if "." in name:
            raise MessageError("name %r contains an illegal dot (.) character." % name)
        if name.lower() == "raw":
            raise MessageError('name cannot be "%s"' % name)
        self.name = name
        self.values = Values(values or [])
        self.keywords = Keywords(keywords or [])
        self.string = string

    def canonical(self):
        """
        Returns the canonical string representation of this command

        Two commands with identical canonical strings are equivalent.
        The canonical form of a verb name is all lower case. A canonical
        string is, by definition, invariant under parsing.
        """
        result = self.name.lower()
        if self.values and len(self.values) > 0:
            result += " %s" % self.values.canonical()
        if self.keywords:
            result += " "
            result += self.keywords.canonical(delimiter=" ")
        return result

    def tokenized(self):
        """
        Returns the parse token representation of a command

        Two commands with identical tokenized strings have the same
        basic grammar. A tokenized string is invariant under parsing.
        """
        result = "VERB"
        if self.values and len(self.values) > 0:
            result += " %s" % self.values.tokenized()
        if self.keywords:
            result += " "
            result += self.keywords.tokenized(delimiter=" ")
        return result

    def clone(self):
        """
        Returns a clone of this object
        """
        new = Command(self.name, self.values, [], self.string)
        new.keywords = self.keywords.clone()
        return new

    def copy(self, other):
        """
        Copies the keywords of another Keywords instance
        """
        self.name = other.name
        self.values = other.values
        self.keywords = other.keywords
        self.string = other.string

    def __repr__(self):
        result = "CMD(%r=%r;%r)" % (self.name, self.values, self.keywords)
        return result
