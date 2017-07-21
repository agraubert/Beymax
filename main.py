import discord
import re
import asyncio
import requests
from pyemojify import emojify

numnames = ['one', "two", 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']

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
                "There are several bots in the server.  If you would like to know about the bots, just say `bots`\n"+
                "Each channel serves a different purpose.  If you would like to know about the channels, just say `channels`"
            )
        elif cmd == 'bots':
            await self.client.send_and_wait(
                self.user,
                "First and foremost, is **Octavia**, our DJ.  She's here to make sure everyone always has access to some sweet tunes\n"+
                "Lastly, I am here to help you out where I can to make sure you have a great time"
            )


class Beymax(discord.Client):
    help_sessions={}
    general=None

    async def send_and_wait(self, *args, **kwargs):
        await self.send_message(*args, **kwargs)
        #await self.wait_for_message(author = self.user)

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
        self.general = discord.utils.get(
            self.get_all_channels(),
            name='general',
            type=discord.ChannelType.text
        )
        print("Ready to serve!")

    def getname(self, user):
        if 'nick' in dir(user) and type(user.nick) is str and len(user.nick):
            return user.nick
        return user.name

    async def on_message(self, message):
        if message.author == self.user:
            return
        content = message.content.strip().split()
        print("Message in channel:", message.channel.name)
        print("Content:", content)
        if re.match(r'!ouch', content[0]):
            await self.send_and_wait(
                message.author,
                "Hello! I am Beymax, your personal ~~healthcare~~ **server** companion.\n"+
                "It's my job to make sure you have a good time and understand the various tools at your disposal in this server\n"+
                "If you're not sure what sort of things I can do, just say `help`\n"+
                "What seems to be the problem?"
            )
            self.help_sessions[message.author] = HelpSession(self, message.author)
        elif re.match(r'!link', content[0]) and len(content)>1:
            await self.send_message(
                message.channel,
                "Looking up `"+content[1]+"` on MasterOverwatch..."
            )
            response = requests.get(
                "https://masteroverwatch.com/profile/pc/us/%s"%(
                        content[1].replace("#", "-")
                    ),
                timeout=5
                )
            if response.status_code != 200:
                await self.send_message(
                    message.channel,
                    "Sorry, I was unable to look up your standings"
                )
            else:
                await self.send_message(
                    message.channel,
                    "I've found your Overwatch stats and I'm linking them to your discord account here"
                )
        elif re.match(r'!poll', content[0]):
            opts = ' '.join(content[2:]).split('|')
            body = self.getname(message.author)+" has started a poll:\n"
            print(body)
            body+=content[1]+"\n"
            print(body)
            body+="\n".join((
                    "%d) %s"%(num, opt)
                    for (num, opt) in
                    zip(range(1, len(opts)+1), opts)
                ))
            print(body)
            body+="\nReact with your vote"
            print(body)
            target = await self.send_message(
                message.channel,
                body
            )
            for i in range(len(opts)):
                await self.add_reaction(
                    target,
                    '👍'#emojify(':%s:'%numnames[i])
                )
        elif re.match(r'!kill-devbot', content[0]):
            await self.close()
        elif re.match(r'!_greet', content[0]):
            await self.on_member_join(message.author)
        elif isinstance(message.channel, discord.PrivateChannel) and message.author in self.help_sessions:
            await self.help_sessions[message.author].digest(content)

    async def on_member_join(self, member):
        await self.send_message(
            self.general,
            "Welcome, @"+member.name+"!\n"+
            "https://giphy.com/gifs/hello-hi-dzaUX7CAG0Ihi"
        )

    async def on_reaction_add(self, reaction, user):
        print(reaction.emoji.encode('utf8'), dir(reaction.emoji))



if __name__ == '__main__':
    Beymax().run('MzEwMjgzOTMyMzQxODk1MTY5.C-7uwg.fP8bYdDv0Vj44-ZvzJx0FFh3muE')
