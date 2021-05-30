# Changelog

## Next version

### 🔧 Fixed

* Correctly assign the type of the actor in a `Command`.


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
