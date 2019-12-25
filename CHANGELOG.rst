.. _clu-changelog:

=========
Changelog
=========

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
* **Breaking change:** Rename ``Client.run()`` and ``Actor.run()`` to ``.start()`` (same for legacy actor). Added a `.LegacyActor.run_forever` method for convenience.

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
