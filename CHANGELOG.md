# Changelog


## Next version

### ✨ Improved

* When tracking the status of a command sent to Tron, update the status with each received reply, and store all the replies.


## 1.0.2 - May 18, 2021

### 🔧 Fixed

* [#78](https://github.com/sdss/clu/issues/78) Fixes a bug in which an actor with a defined `TronConnection` that had failed to start would still try to send commands to Tron.

### ✨ Improved

* [#78](https://github.com/sdss/clu/issues/79): `TronConnection` now uses a `ReconnectingTCPClientProtocol` that will try to keep the socket to Tron open, allowing Tron to restart without losing connection.

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
