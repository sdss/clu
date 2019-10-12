.. _clu-changelog:

=========
Changelog
=========

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
