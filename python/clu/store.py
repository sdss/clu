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


class KeywordStore(defaultdict[str, list]):
    """Stores the keywords output by an actor."""

    def __init__(self, actor: BaseActor, filter: list[str] | None = None):

        self.actor = actor
        self.name = self.actor.name

        self.filter = filter

        defaultdict.__init__(self, list)

    def add_reply(self, reply: Reply):
        """Processes a reply and adds new entries to the store."""

        for keyword, value in reply.message.items():

            if self.filter is not None and keyword not in self.filter:
                continue

            key_out = KeywordOutput(keyword, reply.message_code, datetime.now(), value)

            if keyword in self:
                self[keyword].append(key_out)
            else:
                self[keyword] = [key_out]

    def head(self, keyword: str, n: int = 1):
        """Returns the first N output values of a keyword."""

        return self[keyword][:n]

    def tail(self, keyword: str, n: int = 1):
        """Returns the last N output values of a keyword."""

        return self[keyword][-n:]


@dataclass
class KeywordOutput:
    """Records a single output of a keyword."""

    name: str
    message_code: Any
    date: datetime
    value: Any
