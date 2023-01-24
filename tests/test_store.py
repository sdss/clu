#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-09-01
# @Filename: test_store.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import pytest

from clu.actor import AMQPActor
from clu.base import Reply
from clu.store import KeywordOutput, KeywordStore


@pytest.fixture
def store():
    dummy_actor = AMQPActor(name="test_actor")

    _store = KeywordStore(dummy_actor)

    reply1 = Reply("i", {"key": 1})
    _store.add_reply(reply1)

    reply2 = Reply("i", {"key": 2})
    _store.add_reply(reply2)

    yield _store


def test_store(store):
    assert isinstance(store, KeywordStore)

    assert len(store) == 1
    assert store["hi!"] == []


def test_store_filter(store):
    store.filter = ["key"]

    assert len(store["key"]) == 2
    reply = Reply("i", {"key": 3})
    store.add_reply(reply)
    assert len(store["key"]) == 3

    assert len(store["filtered_key"]) == 0
    reply = Reply("i", {"filtered_key": 5})
    store.add_reply(reply)
    assert len(store["filtered_key"]) == 0


def test_store_add_reply(store):
    assert len(store["key"]) == 2
    assert isinstance(store["key"], list)
    assert isinstance(store["key"][0], KeywordOutput)

    assert store["key"][0].message_code == "i"
    assert store["key"][0].value == 1


def test_store_head(store):
    assert isinstance(store.head("key"), list)
    assert len(store.head("key")) == 1
    assert store.head("key")[0].value == 1


def test_store_tail(store):
    assert isinstance(store.tail("key"), list)

    assert len(store.tail("key")) == 1
    assert len(store.tail("key", 2)) == 2
    assert len(store.tail("key", 3)) == 2

    assert store.tail("key")[0].value == 2
