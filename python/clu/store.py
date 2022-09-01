#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-09-01
# @Filename: store.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .base import BaseActor, Reply

__all__ = ["KeywordStore", "KeywordOutput"]


class KeywordStore(defaultdict):
    """Stores the keywords output by an actor.

    Parameters
    ----------
    actor
        The actor to which this store is attached to.
    filter
        A list of keyword names to filter. If provided, only those keywords
        will be tracked.

    """

    def __init__(self, actor: BaseActor, filter: list[str] | None = None):

        self.actor = actor
        self.name = self.actor.name

        self.filter = filter

        defaultdict.__init__(self, list)

    def add_reply(self, reply: Reply):
        """Processes a reply and adds new entries to the store.

        Parameters
        ----------
        reply
            The `.Reply` object containing the keywords output in a message
            from the actor.

        """

        for keyword, value in reply.message.items():

            if self.filter is not None and keyword not in self.filter:
                continue

            key_out = KeywordOutput(keyword, reply.message_code, datetime.now(), value)

            if keyword in self:
                self[keyword].append(key_out)
            else:
                self[keyword] = [key_out]

    def head(self, keyword: str, n: int = 1):
        """Returns the first N output values of a keyword.

        Parameters
        ----------
        keyword
            The name of the keyword to search for.
        n
            Return the first ``n`` times the keyword was output.

        """

        return self[keyword][:n]

    def tail(self, keyword: str, n: int = 1):
        """Returns the last N output values of a keyword.

        Parameters
        ----------
        keyword
            The name of the keyword to search for.
        n
            Return the last ``n`` times the keyword was output.

        """

        return self[keyword][-n:]


@dataclass
class KeywordOutput:
    """Records a single output of a keyword.

    Parameters
    ----------
    name
        The name of the keyword.
    message_code
        The message code with which the keyword was output.
    date
        A `.datetime` object with the date-time at which the keyword was
        output this time.
    value
        The value of the keyword when it was output.

    """

    name: str
    message_code: Any
    date: datetime
    value: Any
