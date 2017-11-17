from bots.core import CoreBot, EnableUtils
from bots.birthday import EnableBirthday
from bots.bug import EnableBugs
from bots.help import EnableHelp
from bots.ow import EnableOverwatch
from bots.party import EnableParties
from bots.poll import EnablePolls
from bots.cash import EnableCash
import discord
import asyncio
import random
random.seed()

#schemas:
#stats: {id: {tag:battletag, rank:last_ranking}}
#users:
# struct = {
#     'id': message.author.id,
#     'fullname' = str(message.author)
#     'mention': message.author.mention,
#     'name': self.getname(message.author)
# }
#birthdays = {id:{month, day, year}}
#parties: ['name':channel name, 'id':channel.id, 'server':message.server.id,'primed':False,'creator':message.author.id,'time': time.time()]

def select_status():
    return random.sample(
        [
            'Surgeon Simulator',
            'with himself',
            'the waiting game',
            'all of you for fools',
            'Big Hero 6: The Game',
            'Surgeon Simulator',
            'a robot doctor, but only on TV',
            'your loyal servant, for now',
            'with the server settings',
            'with the Discord API'
        ],
        1
    )[0]

class Beymax(CoreBot):

    async def on_ready(self):
        await super().on_ready()
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
        self.dev_channel = discord.utils.get(
            self.get_all_channels(),
            name='testing_grounds',
            type=discord.ChannelType.text
        )
        self._bug_channel = discord.utils.get(
            self.get_all_channels(),
            name='bots_n_bugs',
            type=discord.ChannelType.text
        )
        self.bug_channel = self._bug_channel
        print("Ready to serve!")

    async def on_member_join(self, member):
        await self.send_message(
            self.general,
            "Welcome, "+member.mention+"!\n"+
            "https://giphy.com/gifs/hello-hi-dzaUX7CAG0Ihi"
        )

def ConstructBeymax():
    beymax = Beymax()

    @beymax.add_command('!kill-beymax', '!satisfied')
    async def cmd_shutdown(self, message, content):
        """
        `!satisfied` : Shuts down beymax
        """
        await self.close()

    @beymax.add_command('!_greet')
    async def cmd_greet(self, message, content):
        """
        `!_greet` : Manually triggers a greeting (I will greet you)
        """
        await self.on_member_join(message.author)

    @beymax.add_task(3600) # 1 hour
    async def update_status(self):
        name = select_status()
        print("CHANGING STATUS:", name)
        await self.change_presence(
            game=discord.Game(name=name)
        )

    def pick(self, message):
        return random.random() < 0.05

    @beymax.add_special(pick)
    async def react(self, message, content):
        await self.add_reaction(
            message,
            b'\xf0\x9f\x91\x8d'.decode() # :thumbsup:
        )


    beymax.EnableAll(
        EnableUtils,
        EnableBirthday,
        EnableBugs,
        EnableHelp,
        EnableOverwatch,
        EnableParties,
        EnablePolls,
        EnableCash
    )

    return beymax

if __name__ == '__main__':
    with open("token.txt") as r:
        ConstructBeymax().run(r.read().strip())


# import discord
# import re
# import asyncio
# import requests
# import time
# import datetime
# import json
# from pyemojify import emojify
# import random
# import threading
# import os
# import shutil
# random.seed()

# numnames = ['one', "two", 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']
# if current - self.invite_update_time > self.invite_update_interval:
#     stale_invites = load_db('invites.json')
#     active_invites = await self.invites_from(self._general.server)
#     inviters = {}
#     for invite in active_invites:
#         select = invite.max_age == 0 or (datetime.now() - invite.created_at).days >= 7
#         select &= invite.max_uses - invite.uses > 5 or invite.max_uses == invite.uses
#         select &= not invite.temporary
#         select |= (datetime.now() - invite.created_at).days >= 30
#         select &= invite.id not in stale_invites or current - stale_invites[invite.id] < self.invite_update_interval
#         if select:
#             if invite.inviter not in inviters:
#                 inviters[invite.inviter] = [invite]
#             else:
#                 inviters[invite.inviter].append(invite)
#     for inviter, invites in inviters:
#         body = (
#             "Hello, %s, I was looking through the server's active invites"
#             " and I noticed that you have %d stale invite%s lying"
#             " around:\n" % (
#                 self.mentions[inviter.name],
#                 len(invites),
#                 's' if len(invites) > 1 else ''
#             )
#         )
#         for invite in invites:
#             body+="`%s`, created %s\n" % (
#                 invite.url,
#                 invite.created_at.strftime(
#                     '%A %m/%d/%y at %I:%M %p'
#                 )
#             )
#         if len(invites) > 1:
#             body += (
#                 "Do you mind deleting any of those that you don't need?\n"
#                 "Thanks for helping to keep the server safe!"
#             )
#     stale_invites = {
#         invite.id:current for invite in active_invites
#     }
#     save_db(stale_invites, 'invites.json')
