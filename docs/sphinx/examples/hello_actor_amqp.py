import asyncio
import click
from clu import AMQPActor, command_parser

@command_parser.command()
@click.argument('NAME', type=str)
def say_hello(command, name):
    command.write('i', text=f'Hi {name}!')
    command.finish()

class HelloActor(AMQPActor):
    def __init__(self):
        super().__init__(name='hello_actor',
                         user='guest', password='guest',
                         host='localhost', port=5672,
                         version='0.1.0')

async def run_actor():
    hello_actor = await HelloActor().start()
    await hello_actor.run_forever()

asyncio.run(run_actor())
