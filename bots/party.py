from .core import CoreBot
from .utils import load_db, save_db, sanitize
import discord
import asyncio
import time

def sanitize_channel(name):
    return sanitize(name, '~!@#$%^&*()-', '_')


def EnableParties(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command('!party')
    async def cmd_party(self, message, content):
        if message.server is not None:
            parties = load_db('parties.json', [])
            current_party = None
            for i in range(len(parties)):
                if message.server.id == parties[i]['server'] and message.author.id == parties[i]['creator'] and time.time()-parties[i]['time'] < 86400:
                    if not parties[i]['primed']:
                        current_party = parties[i]['name']
                        parties[i]['primed'] = True
                    else:
                        await self.delete_channel(
                            discord.utils.get(
                                message.server.channels,
                                id=parties[i]['id'],
                                type=discord.ChannelType.voice
                            )
                        )
                        parties[i] = None
            parties = [party for party in parties if party is not None]
            if current_party:
                await self.send_message(
                    message.channel,
                    "It looks like you already have a party together right now: `%s`\n"
                    "However, I can disband that party and create this new one for you.\n"
                    "If you'd like me to do that, just type the same command again"
                    % current_party
                )
            else:
                name = (' '.join(content[1:])+' Party ') if len(content) > 1 else 'Party '
                name = sanitize_channel(name)
                suffix = 1
                while name+str(suffix) in parties:
                    suffix += 1
                name += str(suffix)
                channel = await self.create_channel(
                    message.server,
                    name,
                    type=discord.ChannelType.voice
                )
                await self.send_message(
                    message.channel,
                    "Alright, %s, I've created the `%s` channel for you.\n"
                    "When you're finished, you can close the channel with `!disband`\n"
                    "Otherwise, I'll go ahead and close it for you after 24 hours, if nobody's using it"
                    % (
                        message.author.mention,
                        name
                    )
                )
                parties.append({
                    'name':name,
                    'id':channel.id,
                    'server':message.server.id,
                    'primed':False,
                    'creator':message.author.id,
                    'time': time.time()
                })
            save_db(parties, 'parties.json')

    @bot.add_command('!disband')
    async def cmd_disband(self, message, content):
        if message.server is not None:
            parties = load_db('parties.json', [])
            pruned = []
            for i in range(len(parties)):
                if message.server.id == parties[i]['server'] and message.author.id == parties[i]['creator']:
                    await self.delete_channel(
                        discord.utils.get(
                            self.get_all_channels(),
                            id=parties[i]['id'],
                            type=discord.ChannelType.voice
                        )
                    )
                    pruned.append(parties[i]['name'])
                    parties[i] = None
            parties = [party for party in parties if party is not None]
            save_db(parties, 'parties.json')
            if len(pruned) == 1:
                await self.send_message(
                    self.general,
                    '`%s` has been disbanded. If you would like to create another party, use the `!party` command'
                    % pruned[0]
                )
            elif len(pruned) > 1:
                await self.send_message(
                    self.general,
                    'The following parties have been disbanded:\n'
                    '\n'.join('`%s`'% party for party in pruned)+
                    '\nIf you would like to create another party, use the `!party` command'
                )
            else:
                await self.send_message(
                    message.channel,
                    "You don't have an active party"
                )

    @bot.add_task(600) # 10 min
    async def prune_parties(self):
        parties = load_db('parties.json', [])
        pruned = []
        for i in range(len(parties)):
            if current - parties[i]['time'] >= 86400: # 24 hours
                channel = discord.utils.get(
                    self.get_all_channels(),
                    id=parties[i]['id'],
                    type=discord.ChannelType.voice
                )
                if not len(channel.voice_members):
                    await self.delete_channel(
                        channel
                    )
                    pruned.append(parties[i]['name'])
                    parties[i] = None
        parties = [party for party in parties if party is not None]
        save_db(parties, 'parties.json')
        if len(pruned) == 1:
            await self.send_message(
                self.general,
                '`%s` has been disbanded. If you would like to create another party, use the `!party` command'
                 % pruned[0]
            )
        elif len(pruned) > 1:
            await self.send_message(
                self.general,
                'The following parties have been disbanded:\n'
                '\n'.join('`%s`'% party for party in pruned)+
                '\nIf you would like to create another party, use the `!party` command'
            )

    return bot
