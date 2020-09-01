import asyncio
import os
import click
from clu import AMQPActor, command_parser

@command_parser.command()
@click.argument('NAME', type=str)
def say_hello(command, name):
    command.write('i', text=f'Hi {name}!')
    command.finish()

@command_parser.command()
def say_goodbye(command):
    command.write('i', invalid_key=f'Bye!')
    command.finish()

class HelloActor(AMQPActor):

    schema = os.path.join(os.path.dirname(__file__), 'hello_actor.json')

    def __init__(self):
        super().__init__(name='hello_actor',
                         user='guest', password='guest',
                         host='localhost', port=5672,
                         version='0.1.0')

async def run_actor():
    hello_actor = await HelloActor().start()
    await hello_actor.run_forever()

asyncio.run(run_actor())
