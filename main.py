import discord
import re
import asyncio

class HelpSession:
    def __init__(self, client, user):
        self.client = client
        self.user = user
        self.stage = None

    async def digest(self, message):
        print("Digest content:", message)
        cmd = message[0].replace('`', '').lower()
        if cmd == 'help':
            await self.client.send_and_wait(
                self.user,
                "OK"
            )
            await self.client.send_and_wait(
                self.user,
                "There are several bots in the server.  If you would like to know about the bots, just say `bots`"
            )
            await self.client.send_and_wait(
                self.user,
                "Each channel serves a different purpose.  If you would like to know about the channels, just say `channels`"
            )
        elif cmd == 'bots':
            await self.client.send_and_wait(
                self.user,
                "First and foremost, is **Octavia**, our DJ.  She's here to make sure everyone always has access to some sweet tunes"
            )
            await self.client.send_and_wait(
                self.user,
                "The **Master Overwatch** bot is here so you can brag about your pro Overwatch skills"
            )
            await self.client.send_and_wait(
                self.user,
                "Lastly, I am here to help you out where I can to make sure you have a great time"
            )

class Beymax(discord.Client):
    help_sessions={}

    async def send_and_wait(self, *args, **kwargs):
        await self.send_message(*args, **kwargs)
        await self.wait_for_message(author = self.user)

    async def on_ready(self):
        print('Logged in as')
        print(self.user.name)
        print(self.user.id)
        print('------')
        print("Bot connected to:")
        for server in self.servers:
            print(server.name)
        print("Bot has access to:")
        for channel in self.get_all_channels():
            print(channel.name)
        print("Ready to serve!")

    async def on_message(self, message):
        if message.author == self.user:
            return
        content = message.content.strip().split()
        print("Message in channel:", message.channel.name)
        print("Content:", content)
        if re.match(r'!ouch', content[0]):
            await self.send_and_wait(
                message.author,
                "Hello! I am Beymax, your personal ~~healthcare~~ **server** companion."
            )
            await self.send_and_wait(
                message.author,
                "It's my job to make sure you have a good time and understand the various tools at your disposal in this server"
            )
            await self.send_and_wait(
                message.author,
                "If you're not sure what sort of things I can do, just say `help`"
            )
            await self.send_and_wait(
                message.author,
                "What seems to be the problem?"
            )
            self.help_sessions[message.author] = HelpSession(self, message.author)
        elif re.match(r'!kill-devbot', content[0]):
            await self.close()
        elif isinstance(message.channel, discord.PrivateChannel) and message.author in self.help_sessions:
            await self.help_sessions[message.author].digest(content)


if __name__ == '__main__':
    Beymax().run('MzEwMjgzOTMyMzQxODk1MTY5.C-7uwg.fP8bYdDv0Vj44-ZvzJx0FFh3muE')
