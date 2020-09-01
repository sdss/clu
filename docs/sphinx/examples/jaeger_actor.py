import logging

import clu
from clu import ActorHandler

from jaeger import __version__, log

class JaegerActor(clu.LegacyActor):
    """The jaeger SDSS-style actor."""

    def __init__(self, fps, *args, **kwargs):

        self.fps = fps

        # Pass the FPS instance as the second argument to each parser
        # command (the first argument is always the actor command).
        self.parser_args = [fps]

        super().__init__(*args, **kwargs)

        self.version = __version__

        # Add ActorHandler to log
        self.actor_handler = ActorHandler(self, code_mapping={logging.INFO: 'd'})
        log.addHandler(self.actor_handler)
        self.actor_handler.setLevel(logging.INFO)

        if fps.ieb and not fps.ieb.disabled:
            self.timed_commands.add_command('ieb status', delay=60)
