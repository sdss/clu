.. _clu-changelog:

=========
Changelog
=========

* :support:`64` Use ``type_checker`` with ``jsonschema`` to allow lists and tuples to be be used as arrays (fixes deprecation of the ``type`` argument).

* :release:`0.7.4 <2021-03-23>`
* :support:`63` Breaking change. `.TronKey` is now set with two attributes (in addition to ``value``): ``key`` which contains the actorkeys ``Key`` instance, and ``keyword`` with the updated keyword as an opscore ``Keyword`` object. ``TronKey.value`` contains a list of the ``keyword`` values as Python native types. This is a breaking change because in previous versions ``TronKey.key`` contained the ``Keyword``, but this nomenclature is more consistent with the opscore class names.

* :release:`0.7.3 <2021-03-17>`
* :support:`-` Remove leftover print statements used for testing.

* :release:`0.7.2 <2021-03-16>`
* :feature:`59` Fail AMQP client command when the consumer is not connected.
* :support:`-` Typing: `.BaseCommand` now accepts a generic with the class of the actor.
* :feature:`61` `.Model` and `.TronModel` callbacks receive the model and the updated keyword again. This is done in a backwards compatible manner; if the callback has a single argument in its signature it will receive only the model.
* :bug:`-` Deal with a case in which the loop for a ``CallbackMixIn`` may not be running at the time at which the callback needs to be invoked.

* :release:`0.7.1 <2021-02-21>`
* :feature:`-` Add the option to update the object of the parser object by setting `.ClickParser.context_obj`.
* :support:`57` Documentation on :ref:`actor communication <actor-communication>`.

* :release:`0.7.0 <2021-02-18>`
* :feature:`49` `.setup_test_actor` can now be used with `.AMQPActor` instances.
* :feature:`48` `.BaseActor.write` now processes the reply regardless of the specific actor implementation and creates a `.Reply`. The `.Reply` is passed to the actor ``_write_internal`` implementation which handles sending it to the users using the specific actor transport. If the reply has been created by a command, the `.Reply` object is appended to `.BaseCommand.replies`.

* :release:`0.6.3 <2021-02-16>`
* :feature:`-` The JSONSchema ``array`` type now allows both Python ``list`` and ``tuple``.
* :support:`-` Renamed ``no_validate`` in actors ``write`` method to ``validate`` (defaults to ``True`` so the behaviour should not change).

* :release:`0.6.2 <2021-02-13>`
* :bug:`-` If ``version=False`` the console logger level was being set to zero. Now it's set to ``WARNING`` unless ``verbose=True`` which sets it to ``DEBUG`` or if ``verbose=<int>`` in which case it sets it to that numerical value.
* :feature:`54` Filter out issues parsing out Tron replies and log them only to the file logger.
* :bug:`-` Missing variable ``_TimeTupleJ2000`` in PVT.

* :release:`0.6.1 <2021-02-13>`
* :feature:`-` Use log rollover.
* :bug:`-` If ``verbose=True`` set console logger level to ``DEBUG``. This prevents replies being logged to the console.
* :bug:`-` Remove newline when logging `.JSONActor` replies.
* :feature:`52` Flatten dictionary message in `.LegacyActor.write` into a list, when possible.

* :release:`0.6.0 <2021-02-04>`
* :feature:`50` Add type hints to all codebase.

* :release:`0.5.8 <2021-01-27>`
* :feature:`-` Allow ``error`` keyword to output a string or a list of string. When the message being written fails schema validation, output the error message as a list.
* :feature:`-` New option ``--no-indent`` in CLI to output JSONs in a single line.
* :feature:`-` Add time string at the beginning of the CLI messages. The option ``--no-time`` allows to disable it.

* :release:`0.5.7 <2021-01-24>`
* :bug:`-` More file logger fixes. Prevent a failure when the log directory cannot be created.
* :support:`-` Improve the output of the ``help`` command.
* :bug:`-` Add colour code for error message in ``clu`` CLI.

* :release:`0.5.6 <2020-12-07>`
* :bug:`-` Do not try to set logger format if it failed to create the file logger.

* :release:`0.5.5 <2020-11-17>`
* :bug:`-` Fix AMQP CLI. It failed when printing a message code ``>`` as HTML.
* :bug:`44` Add ``url``, ``virtualhost``, and ``ssl`` parameters for `.AMQPClient` that propagates to `.TopicListener`. When defined ``url`` overrides the connection parameters. The CLU CLI now also accepts a ``--url`` flag.

* :release:`0.5.4 <2020-11-05>`
* :bug:`-` Fix typo that caused `.Device.stop` to fail.
* :feature:`-` When a ``parent`` command is specified, output messages using that command.
* :feature:`-` Add ``silent`` option to `.BaseCommand.set_status`.
* :feature:`-` Provide more information in actor reply for an uncaught error.
* :bug:`-` Handle `.Device.stop` when the client is not connected.

* :release:`0.5.3 <2020-10-31>`
* :feature:`-` Expose ``BaseClient.config`` with the full configuration passed to `.BaseClient.from_config`.

* :release:`0.5.2 <2020-09-22>`
* :support:`-` Significantly increased coverage and cleaned some code.
* :bug:`42` Detect EOF received in `.TronConnection` and cleanly close the connection.
* :support:`-` Call the `.TronModel` callback only with the model itself (it was also receiving the latest changed key). This make it consistent with `.Model` and the documentation.

* :release:`0.5.1 <2020-09-09>`
* :support:`-` Rename ``clu_exchange`` to ``sdss_exchange``.
* :support:`38` Use reply code ``>`` when the command is set to `~.CommandStatus.RUNNING`.
* :support:`39` Use ``schema`` and schema validation in `.LegacyActor` and `.JSONActor`.
* :feature:`40` Use ``context_settings={'ignore_unknown_options': True}`` in `.CluCommand` by default to allow correct parsing of negative number in arguments.

* :release:`0.5.0 <2020-09-01>`
* :support:`-` First version with >80% test coverage.
* :support:`-` Several changes to homogenise the API. All actors and clients now have ``start``, ``stop``, and ``run_forever`` methods.
* :bug:`29` Fix the CLI application.
* :feature:`4` `.AMQPActor` actors now self-validate their messages. The schema can be requested as a command.
* :bug:`34` Fix actor replies with level ``REPLY`` not being logged.
* :feature:`32` Add default ``version`` command.
* :support:`35` `.TronConnection` now subclasses from `.BaseClient` and keeps track of running commands and replies.
* :feature:`31` Add ``multiline`` command to `.JSONActor` to produce human-readable output.

* :release:`0.4.1 <2020-08-19>`
* :support:`-` Set default logging level to warning for stdout/stderr.
* :bug:`-` Fix starting server in `.TCPStreamPeriodicServer`.

* :release:`0.4.0 <2020-08-09>`
* :support:`27` Consolidated how stream servers and clients work. Renamed ``TCPStreamClient`` to `~clu.protocol.open_connection` and ``TCPStreamClientContainer`` to `.TCPStreamClient`. All servers and clients now start and stop with ``start`` and ``stop`` coroutines. The ``_server`` and ``_client`` attributes are now consistently named and not public.
* :support:`27` Replace ``CallbackScheduler`` with `.CallbackMixIn`.
* :bug:`27` Fixed parsing of ``KeyDictionary`` from ``actorkeys``.
* :support:`27` Tests for legacy tools.

* :release:`0.3.3 <2020-08-01>`
* :bug:`-` In the previous release I set the level to ``ERRO`` instead of ``ERROR`` 😓.

* :release:`0.3.1 <2020-08-01>`
* :bug:`-` Log ``StreamHandler`` to ``stderr`` when the record level is ``ERROR`` or greater.

* :release:`0.3.0 <2020-07-31>`
* :support:`-` *Breaking changes.* Improve modularity. Some files have been renamed. `.BaseActor` is now parser-agnostic and the Click-parsing functionality has been moved to `.ClickParser`. Similarly, `.BaseLegacyActor` does not include a parser, with the Click parser implemented in `.LegacyActor`. The logging system has been streamlined.

* :release:`0.2.2 <2020-07-29>`
* :bug:`-` Fix bug in `.MockReplyList.parse_reply` when the value of the keyword contains multiple ``=``.
* :support:`-` Relax ``sdsstools`` version to allow ``jaeger`` to bump the minimum version.

* :release:`0.2.1 <2020-01-24>`
* For `.JSONActor`, the ``help`` commands output lines as a list to improve readability.
* :feature:`18` Allow to pass a command parser that inherits from `.CluGroup` and autocomplete ``help`` and ``ping`` if needed.
* Add `.CommandStatus.did_succeed`.

* :release:`0.2.0 <2020-01-19>`
* :feature:`21` Renamed ``BaseCommand.done`` and ``.failed`` to `.BaseCommand.finish` and `.BaseCommand.fail`.
* Allow to define the default keyword to use if a message is just a string.
* `.BaseCommand.finish` and `.BaseCommand.fail` now return the command itself. This is useful when doing ``return command.fail()`` in case the user wants to do something else with the command.

* :release:`0.1.12 <2020-01-14>`
* Some tweaks to `.JSONActor` and the testing framework.
* Added an error reply level.

* :release:`0.1.11 <2020-01-14>`
* Remove numpy dependency from CLU.
* Improve logging to actor.
* Use `~unittest.mock.AsyncMock` in the ``testing`` module when running Python 3.8+.
* Improve representation of actor classes (print name of class as ``repr``).
* Simplify ``from_config`` by taking advantage that one can pass arguments as keyword arguments and does not need to conserve the original order. This allows to define only `.BaseClient.from_config` and do not need to override it of each subclass.
* Add a `.JSONActor` class that replies to the user using JSON dictionaries.
* Move ``parser`` argument from `.BaseClient` to `.BaseActor`, since only actors receive and need to parse commands.
* Rename `Actor <.AMQPActor>` to `.AMQPActor`.

* :release:`0.1.10 <2019-12-25>`
* Tweak dependencies and poetry install.

* :release:`0.1.9 <2019-11-21>`
* Fix ``__version__`` definition from package version.

* :release:`0.1.8 <2019-11-21>`
* Allow to pass a mapping of logging to actor codes to the `.ActorHandler`.
* Use `poetry <https://poetry.eustace.io/>`__ for development and building.

* :release:`0.1.7 <2019-11-19>`
* Added `.BaseCommand.debug`, `~.BaseCommand.info`, and `~.BaseCommand.warning` convenience methods.

* :release:`0.1.6 <2019-11-15>`
* Fix display of warnings in actor.
* In legacy actor, default to use the ``text`` keyword if the message passed is a string.
* *Breaking change:* Rename ``Client.run()`` and ``Actor.run()`` to ``.start()`` (same for legacy actor). Added a `.BaseLegacyActor.run_forever` method for convenience.

* :release:`0.1.5 <2019-11-13>`
* :bug:`6` Fix bug when asking for help of subcommands and command groups.
* :feature:`7` Allow Tron connection to fail but keep the actor alive and working.
* :bug:`11` Allow to pass parser arguments to a `.CluGroup`.
* :bug:`8` Fix `AttributeError` when connection breaks.
* :feature:`15` Implement subcommands.
* :feature:`17` Allow to run commands on a loop.

* :release:`0.1.4 <2019-10-11>`
* Fix Travis deployment.

* :release:`0.1.3 <2019-10-11>`
* Fix Travis deployment.

* :release:`0.1.2 <2019-10-11>`
* Allow to pass the command parser as an argument.
* Make sure help command finishes.
* Modify legacy command parser. Now it accepts commands in the form ``<command_id> <command_body>`` (in ``tron``, this requires setting the ``ASCIICmdEncoder`` with ``useCID=False, CIDfirst=False``).
* Provide a new :ref:`clu.testing <api-testing>` module with testing tools.
* Better exception and logging handling.

* :release:`0.1.1 <2019-10-03>`
* Fix tag version.

* :release:`0.1.0 <2019-10-03>`
* Basic framework.
