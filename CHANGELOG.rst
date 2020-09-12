.. _clu-changelog:

=========
Changelog
=========

* :support:`-` Significantly increased coverage and cleaned some code.

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
