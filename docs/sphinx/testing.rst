
Testing with CLU
================

CLU provides several tools to test actors. A typical example is as follows ::

    import click
    from clu.parser import command_parser
    from clu.testing import setup_test_actor

    @command_parser.command()
    @click.argument('NAME', type=str)
    async def greeter(command, name):
        command.finish(text=f'Hi {name}!')

    async def test_actor():

        test_actor = setup_test_actor(LegacyActor('my_actor',
                                                  host='localhost',
                                                  port=9999))

        # The following is not needed, start() is replaced with a MagicMock()
        await test_actor.start()

        # Invoke command and wait until it finishes
        command = test_actor.invoke_command('greeter John')
        await command

        # Make sure the command finished successfully
        assert command.status.is_done

        # Get the last reply and check its "text" keyword
        last_reply = test_actor.mock_replies[-1]
        assert last_reply.flag == ':'
        assert last_reply['text'] == 'Hi John!'

What `.setup_test_actor` does is to replace the `~.BaseLegacyActor.start` method with a mock so that it's not necessary to establish a real connection over TCP/IP. It also adds an ``invoke_command`` method that can be used to send test commands to the actor. Instead of replying via the normal actor channel, replies are stored in ``mock_replies`` as `.MockReply` objects.

If using `pytest <https://docs.pytest.org>`__, a normal design pattern is to define the test actor as a fixture ::

    @pytest.fixture(scope='session')
    async def test_actor():

        _actor = setup_test_actor(LegacyActor('my_actor', host='localhost', port=9999))

        yield _actor

        # Clear replies
        _actor.mock_replies.clear()

This usually requires instally `pytest-asyncio <https://github.com/pytest-dev/pytest-asyncio>`__ to be able to define coroutines as fixtures.

.. note:: `.setup_test_actor` currently only works with `.LegacyActor` and `.JSONActor`.


API
---

.. automodule:: clu.testing
    :members: setup_test_actor, MockReplyList, MockReply
    :noindex:
