from .core import CoreBot
from .utils import ListDatabase, sanitize, getname
import discord
from discord.http import Route
import asyncio
import time

def sanitize_channel(name):
    return sanitize(name, '~!@#$%^*-', '_').rstrip()


def EnableParties(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command('!party')
    async def cmd_party(self, message, content):
        """
        `!party [party name]` : Creates a new voice channel (name is optional).
        Example: `!party` or `!party Birthday`
        """
        if message.server is not None:
            async with ListDatabase('parties.json') as parties:
                for i in range(len(parties)):
                    if message.server.id == parties[i]['server'] and message.author.id == parties[i]['creator'] and time.time()-parties[i]['time'] < 86400:
                        await self.send_message(
                            message.channel,
                            "It looks like you already have a party together right now: `%s`\n"
                            "However, I can disband that party and create this new one for you.\n"
                            "Would you like me to disband your current party? (Yes/No)"
                            % parties[i]['name']
                        )
                        while True:
                            response = await self.wait_for_message(
                                timeout=60,
                                author=message.author,
                                channel=message.channel,
                                # check=lambda x:x.content.lower() in {'yes', 'no'}
                            )
                            if response is None:
                                await self.send_message(
                                    message.channel,
                                    "%s, if you still want to create that party, "
                                    "you'll have to issue your command again." % (
                                        getname(message.author)
                                    )
                                )
                                return
                            elif response.content.lower() == 'no':
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
                            await self.delete_channel(
                                discord.utils.get(
                                    message.server.channels,
                                    id=parties[i]['id'],
                                    type=discord.ChannelType.voice
                                )
                            )
                        except discord.NotFound:
                            pass
                        except Exception as e:
                            print("Error deleting channel:", type(e), e.text, e.response)
                            await self.send_message(
                                self.fetch_channel('dev'),
                                "Error deleting party channel for %s" % message.author.mention
                            )
                        parties[i] = None
                parties.update([party for party in parties if party is not None])
                name = (' '.join(content[1:])+' Party') if len(content) > 1 else 'Party'
                name = sanitize_channel(name)
                party_names = {party['name'] for party in parties}
                if name in party_names or name == 'Party':
                    suffix = 1
                    name += ' '
                    while name+str(suffix) in party_names:
                        suffix += 1
                    name += str(suffix)
                perms = []
                #translate permissions from the text channel where the command was used
                #into analogous voice permissions
                if hasattr(message.channel, 'overwrites'):
                    for role, src in message.channel.overwrites:
                        dest = discord.PermissionOverwrite(
                            create_instant_invite=src.create_instant_invite,
                            manage_channels=src.manage_channels,
                            manage_roles=src.manage_roles,
                            manage_webhooks=src.manage_webhooks,
                            connect=src.read_messages,
                            send=src.send_messages,
                            mute_members=src.manage_messages,
                            deafen_members=src.manage_messages,
                            move_members=src.manage_messages,
                            use_voice_activation=True
                        )
                        perms.append((role, dest))
                # Add specific override for Beymax (so he can kill the channel)
                perms.append((
                    message.server.get_member(self.user.id),
                    discord.PermissionOverwrite(
                        manage_channels=True
                    )
                ))
                # Add specific override for the channel's creator (so they can modify permissions)
                perms.append((
                    message.author,
                    discord.PermissionOverwrite(
                        manage_roles=True,
                        manage_channels=True # Allow creator to modify the channel
                    )
                ))
                # FIXME: discord.py needs to add category support
                # channel = await self.create_channel(
                #     message.server,
                #     name,
                #     *perms,
                #     type=discord.ChannelType.voice,
                #     category=self.categories['Voice Channels']
                # )

                #Temporary workaround for party creation within categories
                target_category = None
                category_reference = self.config_get('party_category')
                if category_reference is not None:
                    for channel in message.server.channels:
                        #FIXME: CategoryType instead of 4
                        if channel.type == 4 and (
                            channel.id == category_reference or
                            channel.name == category_reference
                        ):
                            target_category = channel.id
                    if target_category is None:
                        raise NameError("No category '%s'"%category_reference)

                @asyncio.coroutine
                def tmp_create_channel():
                    permissions_payload = [
                        {
                            'allow': rule.pair()[0].value,
                            'deny': rule.pair()[1].value,
                            'id': target.id,
                            'type': 'member' if isinstance(target, discord.User) else 'role'
                        }
                        for target, rule in perms
                    ]

                    def tmp_post_request():
                        payload = {
                            'name': name,
                            'type': str(discord.ChannelType.voice),
                            'permission_overwrites': permissions_payload,
                            'parent_id': target_category
                        }
                        return self.http.request(
                            Route(
                                'POST',
                                '/guilds/{guild_id}/channels',
                                guild_id=message.server.id
                            ),
                            json=payload,
                            # reason=None
                        )
                    data = yield from tmp_post_request()
                    channel = discord.Channel(server=message.server, **data)
                    return channel

                channel = await tmp_create_channel()
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
                    # 'primed':False,
                    'creator':message.author.id,
                    'time': time.time()
                })
            parties.save()
        else:
            await self.send_message(
                message.channel,
                "You cannot use this command in a private chat. "
                "Please try it again from within a server channel"
            )

    @bot.add_command('!disband')
    async def cmd_disband(self, message, content):
        """
        `!disband` : Closes any active party voice channels you have
        """
        if message.server is not None:
            async with ListDatabase('parties.json') as parties:
                pruned = []
                for i in range(len(parties)):
                    if message.server.id == parties[i]['server'] and message.author.id == parties[i]['creator']:
                        channel = discord.utils.get(
                            self.get_all_channels(),
                            id=parties[i]['id'],
                            type=discord.ChannelType.voice
                        )
                        if channel is not None:
                            pruned.append(
                                '`%s`' % parties[i]['name']
                                if str(parties[i]['name']) == str(channel.name)
                                else '`%s` AKA `%s`' % (
                                    channel.name,
                                    parties[i]['name']
                                )
                            )
                            await self.delete_channel(
                                channel
                            )
                        parties[i] = None
                parties.update([party for party in parties if party is not None])
                parties.save()
            if len(pruned) == 1:
                await self.send_message(
                    message.channel,
                    '%s has been disbanded. If you would like to create another party, use the `!party` command'
                    % pruned[0]
                )
            elif len(pruned) > 1:
                await self.send_message(
                    message.channel,
                    'The following parties have been disbanded:\n'
                    '\n'.join(pruned)+
                    '\nIf you would like to create another party, use the `!party` command'
                )
            else:
                await self.send_message(
                    message.channel,
                    "You don't have an active party"
                )

    @bot.add_task(600) # 10 min
    async def prune_parties(self):
        current = time.time()
        async with ListDatabase('parties.json') as parties:
            pruned = []
            for i in range(len(parties)):
                if current - parties[i]['time'] >= 86400: # 24 hours
                    channel = discord.utils.get(
                        self.get_all_channels(),
                        id=parties[i]['id'],
                        type=discord.ChannelType.voice
                    )
                    if channel is None or not len(channel.voice_members):
                        if channel is not None:
                            pruned.append(
                                '`%s`' % parties[i]['name']
                                if str(parties[i]['name']) == str(channel.name)
                                else '`%s` AKA `%s`' % (
                                    channel.name,
                                    parties[i]['name']
                                )
                            )
                            await self.delete_channel(
                                channel
                            )
                        parties[i] = None
            parties.update([party for party in parties if party is not None])
            parties.save()
        if len(pruned) == 1:
            await self.send_message(
                self.fetch_channel('general'),
                '%s has been disbanded. If you would like to create another party, use the `!party` command'
                 % pruned[0]
            )
        elif len(pruned) > 1:
            await self.send_message(
                self.fetch_channel('general'),
                'The following parties have been disbanded:\n'
                '\n'.join(pruned)+
                '\nIf you would like to create another party, use the `!party` command'
            )

    return bot
