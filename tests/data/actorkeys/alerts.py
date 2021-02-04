#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-12-28
# @Filename: alerts.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

# flake8:noqa
# type: ignore


KeysDictionary(
    "alerts",
    (1, 7),
    Key("version", String(help="product version")),
    Key(
        "activeAlerts",
        String(name="alertID", help="alert ID: actor.keyword") * (0, None),
        help="A list of the ID of every active alert",
    ),
    Key(
        "alert",
        String(name="alertID", help="alert ID: actor.keyword"),
        Enum(
            "ok",
            "info",
            "apogeediskwarn",
            "warn",
            "serious",
            "critical",
            name="severity",
            help="The severity level of an alert; ok means the alert is over.",
        ),
        String(name="value", help="value of keyword"),
        Bool("disabled", "enabled", name="isEnabled"),
        Bool(
            "noack", "ack", name="isAcknowledged", help="has alert been acknowledged?"
        ),
        String(
            name="acknowledger",
            help="commander ID of person who acknowledge "
            "the alert (or, perhaps, unacked it)",
        ),
        help="Information about one active alert",
        doCache=False,
    ),
    Key(
        "disabledAlertRules",
        String(name="rule", help="(actor.keyword, severity, who)") * (0, None),
        help="A list of all disabled alert rules.",
    ),
    Key(
        "downInstruments",
        String() * (0, None),
        help="A list of instruments that are down "
        "(and whose alerts are thus ignored)",
    ),
    Key(
        "instrumentNames",
        String() * (0, None),
        help="A list of known instruments. These are valid values "
        "for the alert instrumentState command and the downInstruments keyword",
    ),
    Key("text", String(), help="text for humans"),
)
