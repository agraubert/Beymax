from .core import CoreBot
from .args import Arg
from .utils import DBView, sanitize, getname
import discord
from discord.http import Route
import asyncio
import time
import os
import json

def sanitize_channel(name):
    return sanitize(name, '~!@#$%^*-<>', '_').rstrip()

PARTY_DURATION = 86400 # 24 hours

def EnableParties(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.subscribe('before:ready')
    async def cleanup(self, _):
        if not os.path.exists('parties.json'):
            return
        with open('parties.json') as r:
            parties = json.load(r)
        async with DBView('parties') as db:
            db['parties'] = parties
        os.remove('parties.json')

    @bot.add_command('party', Arg('name', remainder=True, help="Optional party name"))
    async def cmd_party(self, message, name):
        """
        `$!party [party name]` : Creates a new voice channel (name is optional).
        Example: `$!party` or `!party Birthday`
        """
        if message.guild is not None:
            async with DBView('parties', parties=[]) as db:
                for i in range(len(db['parties'])):
                    if message.guild.id == db['parties'][i]['guild'] and message.author.id == db['parties'][i]['creator'] and time.time()-db['parties'][i]['time'] < PARTY_DURATION:
                        await self.send_message(
                            message.channel,
                            "It looks like you already have a party together right now in this server: `%s`\n"
                            "However, I can disband that party and create this new one for you.\n"
                            "Would you like me to disband your current party? (Yes/No)"
                            % db['parties'][i]['name']
                        )
                        while True:
                            try:

                                response = await self.wait_for(
                                    'message',
                                    check=lambda m: m.author == message.author and m.channel == message.channel,
                                    timeout=60,
                                )
                            except asyncio.TimeoutError:
                                await self.send_message(
                                    message.channel,
                                    "%s, if you still want to create that party, "
                                    "you'll have to issue your command again." % (
                                        getname(message.author)
                                    )
                                )
                                return
                            if response.content.lower() == 'no':
                                await self.send_message(
                                    message.channel,
                                    "Okay, %s. Your current party will remain active"
                                    % getname(message.author)
                                )
                                return
                            elif response.content.lower() == 'yes':
                                break
                            await self.send_message(
                                message.channel,
                                "I didn't understand your response.\n"
                                "%s, would you like me to disband your "
                                "current party? (Yes/No)" % message.author.mention
                            )
                        try:
                            await discord.utils.get(
                                message.guild.channels,
                                id=db['parties'][i]['id'],
                                type=discord.VoiceChannel
                            ).delete()
                        except discord.NotFound:
                            pass
                        except Exception as e:
                            print("Error deleting channel:", type(e), e.text, e.response)
                            await self.send_message(
                                self.fetch_channel('dev'),
                                "Error deleting party channel for %s" % message.author.mention
                            )
                        db['parties'][i] = None
                db['parties'] = [party for party in db['parties'] if party is not None]
                name = (' '.join(name)+' Party') if len(name) > 0 else "{}'s Party".format(getname(message.author))
                name = sanitize_channel(name)
                party_names = {party['name'] for party in db['parties']}
                if name in party_names or name == 'Party':
                    suffix = 1
                    name += ' '
                    while name+str(suffix) in party_names:
                        suffix += 1
                    name += str(suffix)
                perms = {}
                #translate permissions from the text channel where the command was used
                #into analogous voice permissions
                if hasattr(message.channel, 'overwrites'):
                    perms = {
                        role: discord.PermissionOverwrite(
                            create_instant_invite=src.create_instant_invite,
                            manage_channels=src.manage_channels,
                            manage_permissions=src.manage_permissions,
                            manage_webhooks=src.manage_webhooks,
                            connect=src.read_messages,
                            speak=src.send_messages,
                            mute_members=src.manage_messages,
                            deafen_members=src.manage_messages,
                            move_members=src.manage_messages,
                            use_voice_activation=True
                        )
                        for role, src in message.channel.overwrites.items()
                    }
                # Add specific override for Beymax (so he can kill the channel)
                perms[message.guild.get_member(self.user.id)] = discord.PermissionOverwrite(
                    manage_channels=True,
                    # manage_permissions=True,
                )
                # Add specific override for the channel's creator (so they can modify permissions)
                perms[message.author] = discord.PermissionOverwrite(
                    connect=True,
                    speak=True,
                    # manage_permissions=True,
                    manage_channels=True # Allow creator to modify the channel
                )
                target_category = None
                target_reference = self.config_get('party_category')
                for cat in message.guild.categories:
                    if cat.name == target_reference or cat.id == target_reference:
                        target_category = cat
                channel = await message.guild.create_voice_channel(
                    name,
                    overwrites=perms,
                    category=cat,
                    reason="Creating party for {}".format(getname(message.author))
                )

                await self.send_message(
                    message.channel,
                    "Alright, %s, I've created the `%s` channel for you.\n"
                    "When you're finished, you can close the channel with `$!disband`\n"
                    "Otherwise, I'll go ahead and close it for you after 24 hours, if nobody's using it"
                    % (
                        message.author.mention,
                        name
                    )
                )
                db['parties'].append({
                    'name':name,
                    'id':channel.id,
                    'guild':message.guild.id,
                    'creator':message.author.id,
                    'reference_channel': message.channel.id,
                    'reference_message': message.id,
                    'time': time.time()
                })
                await self.dispatch_future(
                    PARTY_DURATION,
                    'cleanup-party',
                    partyID=channel.id,
                )
        else:
            await self.send_message(
                message.channel,
                "You cannot use this command in a private chat. "
                "Please try it again from within a guild channel"
            )

    @bot.add_command('disband')
    async def cmd_disband(self, message):
        """
        `$!disband` : Closes any active party voice channels you have
        """
        if message.guild is not None:
            pruned = False
            async with DBView('parties', parties=[]) as db:
                for party in db['parties']:
                    if message.guild.id == party['guild'] and message.author.id == party['creator']:
                        await kill_party(self, party)
                        pruned = True
                db['parties'] = [
                    party for party in db['parties']
                    if party is not None and party['creator'] != message.author.id
                ]
            if not pruned:
                await self.send_message(
                    message.channel,
                    "You don't have an active party"
                )

    @bot.subscribe('cleanup-party')
    async def prune_parties(self, _, partyID):
        party = None
        async with DBView('parties', parties=[]) as db:
            for p in db['parties']:
                if p['id'] == partyID:
                    party = p
                    break
        if party is not None:
            await kill_party(self, party)
        async with DBView('parties', parties=[]) as db:
            db['parties'] = [
                p for p in db['parties']
                if p is not None and p['id'] != partyID
            ]

    async def kill_party(bot, party):
        channel = discord.utils.get(
            bot.get_all_channels(),
            id=party['id'],
            type=discord.ChannelType.voice
        )
        if channel is not None:
            if len(channel.members):
                # Rescheduler event, since channel is still active
                await bot.dispatch_future(
                    3600, # 1 hour,
                    'cleanup-party',
                    partyID=party['id']
                )
                return
            name = (
                '`{}`'.format(party['name'])
                if str(party['name']) == str(channel.name)
                else
                '`{}` AKA `{}`'.format(
                    channel.name,
                    party['name']
                )
            )
            await channel.delete()
            reference = discord.utils.get(
                bot.get_all_channels(),
                id=party['reference_channel'],
                type=discord.ChannelType.text
            )
            ref_message = None
            if reference is not None:
                ref_message = await reference.fetch_message(party['reference_message'])
            if reference is not None and ref_message is not None:
                await reference.send(
                    "{} has been disbanded. If you would like to create another party, use the `$!party` command".format(
                        name
                    ),
                    reference=ref_message.to_reference()
                )
            else:
                await self.send_message(
                    self.fetch_channel('general'),
                    "{} has been disbanded. If you would like to create another party, use the `$!party` command".format(
                        name
                    )
                )


    return bot
