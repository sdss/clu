# Changelog

## Next version

### 🚀 New

* Support Python 3.10.

### ✨ Improved

* [#101](https://github.com/sdss/clu/issues/101) The legacy actor now accepts command strings with a commander id (e.g., `APO.Jose 10 status`). The commander id is stored in the `Command` object. Added a `Command.send_command()` that will call the remote command propagating the commander ID. For example, if a command has commander `APO.Jose` and sends a command to `guider`, the `guider` actor will receive a command with commander `APO.Jose.guider`.
* [#102](https://github.com/sdss/clu/issues/102) When calling a model or property callback, ensure that the arguments sent are a frozen copy of the state of the model/property at the time of the callback. This prevents that if a model is updated twice in quick succession, the callback may receive only the second value. A consequence of this change is that the model callback now receives a flattened dictionary with all the model keywords as the first argument.
* If not specified, a message with code `e` or `f`, or an exception, will use the keyword `error`.


## 1.5.0 - October 12, 2021

### ✨ Improved

* [#99](https://github.com/sdss/clu/issues/99) Add `exception_module` value to the output of an exception.
* [sdss/sdsstools#29](https://github.com/sdss/sdsstools/issues/29) Allow to pass a custom PyYAML loader in `from_config()` that will be forwarded to `read_yaml_file()`.
* Actors now accept `<actor> --help` with the same result as `<actor> help`.
* Add `additional_properties` parameter to `LegacyActor`.
* When a legacy actor starts, if there is a `TronConnection` available it will try to send a `hub startNubs <actor>` to initiate the connection.

### 🔧 Fixed

* Use `clu.client` for `TronConnection.send_command()`.
* If a command in a `LegacySurvey` actor is left running after the client closes the connection, it would still try to output messages to it, causing a `socket.send() raised exception` error. Now if the client exists the command continues running, but outputs to that client are ignored.


## 1.4.0 - September 27, 2021

### 🚀 New

* [#98](https://github.com/sdss/clu/issues/98) Add `unique()` and `cancellable()` decorators for Click command parsers.

### ✨ Improved

* [#95](https://github.com/sdss/clu/issues/95) Cast all arguments to string in `ProxyClient.send_command()`.
* Add `get_keys` parameter to `LegacyActor.start()` that is passed to `TronConnection.start()`
* Use `.client` as default commander for `TronConnection` and `{actor}.{target}` for actor.

### 🔧 Fixed

* Avoid and error in the callback when a connection to the TCP server is closed.


## 1.3.0 - September 17, 2021

### 💥 Breaking changes

* [#86](https://github.com/sdss/clu/issues/86) `additionalProperties` is set to `false` by default if not specified, including if `schema=None` when initialising an actor.

### 🚀 New

* [#85](https://github.com/sdss/clu/issues/85) Added `BaseClient.proxy()` method.

### ✨ Improved

* [#90](https://github.com/sdss/clu/issues/90) If an exception object is passed as a keyword in a command or actor message, it will be unpacked into the exception type and message.
* Make the error output when a reply fails to validate more clear.

### 🔧 Fixed

* [#91](https://github.com/sdss/clu/issues/91) Documentation example for testing with CLU.

### 🧹 Cleanup

* Add `invoke_mock_command()` stub method to `BaseClient` to simplify type checking.


## 1.2.1 - June 20, 2021

### 🚀 New

* [#89](https://github.com/sdss/clu/issues/89) Use [furo](https://pradyunsg.me/furo/) Sphinx theme.

### 🔧 Fixed

* `LegacyActor` now accepts the `config` parameter sent by `from_config()`.

### ✨ Improved

* Subcommands now won't write to the users when they start running.


## 1.2.0 - June 3, 2021

### 🚀 New

* `Command` and `BaseActor.write()` now accept a `silent` argument that if `True` will execute the command normally and update the status and internal model, but won't write to the user. Timed command can be run in silent mode the first iteration by initialising them with `first_silent=True`.

### ✨ Improved

* [#77](https://github.com/sdss/clu/issues/77) Child commands will never emit ``:`` or ``f`` messages that may be confused as the parent being done.
* Timed commands are run immediately when started.
* `from_config()` now passes the configuration to the client `__init__()` so that it is accessible during initialisation.
* If a timed command takes longer to run than the interval at which the poller checks if new timed commands should be run, prevent it from being issued multiple times.


## 1.1.2 - May 31, 2021

### 🔧 Fixed

* Revert previous changes to the typing of `Command` that were causing problems, but keep the generic for the command future.


## 1.1.1 - May 30, 2021

### 🔧 Fixed

* Correctly assign the type of the actor in a `Command`.
* Fix error when `TopicListener.stop()` is called and there is not an active connection.

### ✨ Improved

* `Device.start()` now returns `self`.
* [#84](https://github.com/sdss/clu/issues/84) `send_command` now accepts multiple arguments before the keyword arguments. If they are passed, they will be concatenated to create the full command string. For example: `client.send_command('my_actor', 'sum', '-v', 2, 4, command_id=5)` is equivalent to `client.send_command('my_actor', 'sum -v 2 4', command_id=5)`


## 1.1.0 - May 29, 2021

### 🚀 New

* [#82](https://github.com/sdss/clu/issues/82) `send_command` now accepts a `callback` argument. If set, the callback will be called each time the actor replies and will receive the reply itself (`AMQPReply` in case of `AMQPClient/Actor` and `clu.legacy.types.messages.Reply` for `Tron/TronConnection`). Thanks to Florian Briegel for the idea.

### ✨ Improved

* [#81](https://github.com/sdss/clu/issues/81) Improve typing of `BaseCommand` and command replies.
* In `TronConnection`, do not fail with a `ParseError` if one of the keywords cannot be parsed. Instead, issue a warning and move on to the next one.
* The CLI now checks that the preferred style (`solarized-dark`) is available. Otherwise defaults to `pygments` default style.
* Copy `Property` before notifying the callbacks. This prevents the value passed being updated in the time that it takes for the callback to go out.
* `Property`, `BaseModel`, and `TronModel` now have a `last_seen` attribute that is updated with the Unix time when the model or property/key are updated.
* When the AMQP client is handling replies for a command, it will update the status every time it changes, not only when it is done or failed.
* `StatusCommand` callbacks now receive the status itself as an argument.


## 1.0.3 - May 20, 2021

### ✨ Improved

* When tracking the status of a command sent to Tron, update the status with each received reply, and store all the replies.
* When `as_complete_failer` cancels the tasks after an exception, suppress all possible exceptions, not only `CancelledError`, since the original exception will be raised again. Add tests for `as_complete_failer`.


## 1.0.2 - May 18, 2021

### 🔧 Fixed

* [#78](https://github.com/sdss/clu/issues/78) Fixes a bug in which an actor with a defined `TronConnection` that had failed to start would still try to send commands to Tron.

### ✨ Improved

* [#79](https://github.com/sdss/clu/issues/79) `TronConnection` now uses a `ReconnectingTCPClientProtocol` that will try to keep the socket to Tron open, allowing Tron to restart without losing connection.

### 🧹 Cleanup

* `releases` was misbehaving once we reached `1.x`, and its interpretation of semantic versioning was a bit too extreme. Instead, we are now using a Markdown file with `myst-parser`. The previous changelog is still available [here](https://clu.readthedocs.io/en/0.9.1/changelog.html).


## 1.0.1 - May 16, 2021

### ✨ Improved

* `BaseActor` receives a `validate` parameter that can be used to globally define whether the actor should validate its own messages against the model.


## 1.0.0 - May 12, 2021

### 🚀 New

* Transition CLU to stable!

### 🧹 Cleanup

* Upgrade `click` to `^8.0.0`.


## The Pre-history

The changelog for versions previous to 1.0.0 can be found [here](https://clu.readthedocs.io/en/0.9.1/changelog.html).
