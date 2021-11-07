"""
String parser for SDSS-3 command and reply protocols

Refer to https://trac.sdss3.org/wiki/Ops/Parsing for details. Unit and
timing tests, together with an alternative implementation using
pyparsing, are available in the SDSS-3 repository in
tops.sdss3.protocols.

Uses a copy of the PLY parser package
(http://www.dabeaz.com/ply/ply.html) that is included in this
distribution.
"""

# type: ignore

# Created 10-Oct-2008 by David Kirkby (dkirkby@uci.edu)

import re

from .messages import (
    ActorReplyHeader,
    Command,
    Keyword,
    MessageError,
    RawKeyword,
    Reply,
    ReplyHeader,
)
from .ply import lex, yacc


name_pattern = re.compile("[A-Za-z][A-Za-z0-9_.]*$")


class ParseError(Exception):
    pass


class TemporaryBase(object):
    """
    Serves as a temporary base class that will be substituted later
    """

    pass


class ReplyParser(TemporaryBase):
    """
    Specifies the parsing rules for reply strings

    The base class will eventually be ParserBase but is not declared
    above since PLY applies grammar rules in the order in which they are
    declared.
    """

    _name = "(?:[A-Za-z][A-Za-z0-9_]*)"
    _extra = r"(?:\.[A-Za-z][A-Za-z0-9_.]*)"
    _number = "0|[1-9][0-9]*"
    hdr_pattern = re.compile(
        r"(%s?)\.(%s)(%s?)[ \t]+(%s)[ \t]+(%s)[ \t]+(.)[ \t]+"
        % (_name, _name, _extra, _number, _name)
    )

    # lexical tokens
    tokens = ["EQUALS", "COMMA", "VALUE", "NAME_OR_VALUE", "QUOTED", "SEMICOLON"]

    def p_reply(self, p):
        "reply : keywords"
        p[0] = Reply(header=self.header, keywords=p[1], string=self.string)

    def p_empty_reply(self, p):
        "reply :"
        p[0] = Reply(header=self.header, keywords=[], string=self.string)

    def p_reply_keywords(self, p):
        "keywords : keywords SEMICOLON keyword"
        p[0] = p[1]
        p[0].append(p[3])

    def p_one_keyword(self, p):
        "keywords : keyword"
        p[0] = [p[1]]

    t_SEMICOLON = ";"

    def unwrap(self):
        matched = ReplyParser.hdr_pattern.match(self.string)
        if not matched:
            raise ParseError("Badly formed reply header in: %s" % self.string)
        self.header = ReplyHeader(*matched.groups())
        return self.string[matched.end() :]


class ActorReplyParser(ReplyParser):
    """
    Specifies the parsing rules for reply strings from actors

    The basic format is:
    commandID userID code data

    The base class will eventually be ParserBase but is not declared
    above since PLY applies grammar rules in the order in which they are
    declared.
    """

    hdr_pattern = re.compile(
        "(%s)[ \t]+(%s)[ \t]+(.)[ \t]+" % (ReplyParser._number, ReplyParser._number)
    )

    def unwrap(self):
        matched = ActorReplyParser.hdr_pattern.match(self.string)
        if not matched:
            raise ParseError("Badly formed reply header in: %s" % self.string)
        self.header = ActorReplyHeader(*matched.groups())
        return self.string[matched.end() :]


class CommandParser(TemporaryBase):
    """
    Specifies the parsing rules for command strings

    The base class will eventually be ParserBase but is not declared
    above since PLY applies grammar rules in the order in which they are
    declared.
    """

    # lexical tokens
    tokens = ["EQUALS", "COMMA", "VALUE", "NAME_OR_VALUE", "QUOTED", "RAW", "LINE"]

    def p_verb_with_values_command(self, p):
        "command : verb_with_values keywords"
        p[0] = Command(name=p[1][0], values=p[1][1:], keywords=p[2], string=self.string)

    def p_verb_no_values_command(self, p):
        "command : NAME_OR_VALUE NAME_OR_VALUE values keywords"
        p[0] = Command(name=p[1], keywords=[Keyword(p[2], p[3])], string=self.string)
        p[0].keywords.extend(p[4])

    def p_raw_command(self, p):
        "command : NAME_OR_VALUE RAW LINE"
        p[0] = Command(name=p[1], keywords=[RawKeyword(p[3])], string=self.string)

    def p_ambiguous_command(self, p):
        "command : NAME_OR_VALUE NAME_OR_VALUE keywords"
        p[0] = Command(name=p[1], keywords=[Keyword(p[2])], string=self.string)
        p[0].keywords.extend(p[3])

    def p_verb_only_command(self, p):
        "command : NAME_OR_VALUE"
        p[0] = Command(name=p[1], string=self.string)

    def p_verb_add_values(self, p):
        "verb_with_values : verb_with_values COMMA value"
        p[0] = p[1]
        p[0].append(p[3])

    def p_verb_with_two_values(self, p):
        "verb_with_values : NAME_OR_VALUE NAME_OR_VALUE COMMA NAME_OR_VALUE"
        p[0] = [p[1], p[2], p[4]]

    def p_verb_with_one_value(self, p):
        """verb_with_values : NAME_OR_VALUE VALUE
        | NAME_OR_VALUE QUOTED"""
        p[0] = [p[1], p[2]]

    def p_command_keywords(self, p):
        "keywords : keywords keyword"
        p[0] = p[1]
        p[0].append(p[2])

    def p_no_keywords(self, p):
        "keywords :"
        p[0] = []

    def p_raw_keyword(self, p):
        "keyword : RAW LINE"
        p[0] = RawKeyword(p[2])

    # lexical analysis states
    states = (("RAW", "exclusive"),)

    # capture inline whitespace in RAW mode
    t_RAW_ignore = ""

    def t_RAW_LINE(self, t):
        r"\s*=(?P<value>.*)"
        t.value = self.lexer.lexmatch.group("value")
        self.lexer.begin("INITIAL")
        return t

    def word_token(self, t):
        if t.value.lower() == "raw":
            t.type = "RAW"
            t.lexer.begin("RAW")
            return t
        else:
            return ParserBase.word_token(self, t)

    def unwrap(self):
        return self.string


class ParserBase(object):
    """
    Specifies the parsing rules common to all messages

    Although this is the base class for command and reply parsers we
    must define it after those classes since PLY applies grammar rules
    in the order in which they are declared.
    """

    def __init__(self, debug=0):
        """
        Initializes a new parser object

        A debug level of 1 will print out the lex rules on
        initialization and the yacc state in case of an error. Level 2
        will also provide a trace of the yacc analysis.
        """
        self.debug = debug
        self.lexer = lex.lex(object=self, debug=debug)
        self.engine = yacc.yacc(module=self, debug=debug, write_tables=0)

    def p_keyword_with_values(self, p):
        "keyword : NAME_OR_VALUE values"
        p[0] = Keyword(p[1], p[2])

    def p_bare_keyword(self, p):
        "keyword : NAME_OR_VALUE"
        p[0] = Keyword(p[1])

    def p_many_values(self, p):
        "values : values COMMA value"
        p[0] = p[1]
        p[0].append(p[3])

    def p_values(self, p):
        "values : EQUALS value"
        p[0] = [p[2]]

    def p_value(self, p):
        """value : NAME_OR_VALUE
        | VALUE
        | QUOTED"""
        p[0] = p[1]

    # ignore redundant inline whitespace
    t_ignore = " \t"

    # single-character literal tokens
    t_EQUALS = "="
    t_COMMA = ","

    def word_token(self, t):
        if name_pattern.match(t.value):
            t.type = "NAME_OR_VALUE"
        else:
            t.type = "VALUE"
        return t

    def t_WORD(self, t):
        r'[^"\'\s=,;]+'
        return self.word_token(t)

    def t_QUOTED1(self, t):
        r"'(?P<value>(?:[^\\'\n]|\\.)*?)'"
        t.type = "QUOTED"
        t.value = t.lexer.lexmatch.group("value")
        return t

    def t_QUOTED2(self, t):
        r'"(?P<value>(?:[^\\"\n]|\\.)*?)"'
        t.type = "QUOTED"
        t.value = t.lexer.lexmatch.group("value")
        return t

    def p_error(self, tok):
        """
        Handles parse errors
        """
        # reset the lexer in case we were doing some modal processing
        # (this should only happen for the raw command keyword)
        # see http://www.dabeaz.com/ply/ply.html#ply_nn21
        self.lexer.begin("INITIAL")
        if not tok:
            raise ParseError("Unexpected end of input")
        raise ParseError(
            "Unexpected %s parse token (%r) in:\n%s"
            % (tok.type, tok.value[: min(len(tok.value), 20)], self.string)
        )

    def t_ANY_error(self, tok):
        """
        Handles lexical analysis errors
        """
        if not tok:
            raise ParseError("Undefined lexical analysis error")
        raise ParseError(
            "Lexical analysis error at %r" % tok.value[: min(len(tok.value), 20)]
        )

    def tokenize(self, string):
        """
        Generates the lexical tokens found in the message string
        """
        string = string.rstrip("\n")
        self.lexer.input(string)
        tok = self.lexer.token()
        while tok:
            yield tok
            tok = self.lexer.token()

    def parse(self, string):
        """
        Returns a parsed representation of the message string

        Any trailing newline characters are removed before parsing.
        Raises an exception if the string cannot be parsed.
        """
        self.string = string.rstrip("\n")
        try:
            body = self.unwrap()
            return self.engine.parse(body, lexer=self.lexer, debug=self.debug)
        except MessageError as e:
            raise ParseError(str(e))


# Replace the parser base classes. This is necessary since PLY applies YACC rules
# in the order in which they are declared in the source file, but python expects
# that a base class is declared before any subclasses.

ReplyParser.__bases__ = (ParserBase,)
CommandParser.__bases__ = (ParserBase,)
