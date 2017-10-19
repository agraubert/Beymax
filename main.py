import discord
import re
import asyncio
import requests
import time
import datetime
import json
from pyemojify import emojify
import random
import threading
random.seed()

numnames = ['one', "two", 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']

def get_mmr(user):
    base_url = 'https://masteroverwatch.com/profile/pc/us/'
    response = requests.get(
        base_url + user,
        timeout = 3
    )
    result = re.search(
        r'<span.*?class=\"[^\"]*mmr[^\"]*\"></span>\"?\s*\"?([0-9,]+)\s*\"?',
        response.text
    )
    return int(result.group(1).replace(',',''))

def rank(rating):
    if rating <=1499:
        return (1,'Bronze')
    elif rating <=1999:
        return (2,'Silver')
    elif rating <=2499:
        return (3,'Gold')
    elif rating <=2999:
        return (4,'Platinum')
    elif rating <=3499:
        return (5,'Diamond')
    elif rating <=3999:
        return (6,'Master')
    return (7,'Grand Master')

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

def encourage(n):
    if n <=2:
        pool = [
            "Good show! You gave it your all, and that's is an achivement in itself",
            "Well done! You certainly did better than I could have",
            "Meh."
        ]
    elif n<=4:
        pool = [
            "Excellent! That's no small feat!",
            "Very well done! I'm sure I could learn something from you",
            "Fantastic job! I'm proud of you!",
            "That's like, okay, I guess"
        ]
    elif n<=6:
        pool = [
            "Incredible! Advancing beyond Platinum is a monumental achivement!",
            "Wow! You climbed out of the masses and found yourself at the very peak!",
            "I've seen better"
        ]
    else:
        pool = [
            "Holy shit! You put your skills to the test, and came out on the very top!  Nicely, done!"
        ]
    return random.sample(pool,1)[0]


def postfix(n):
    if n[-1] == '1':
        return n+'st'
    elif n[-1] == '2':
        return n+'nd'
    elif n[-1] == '3':
        return n+'rd'
    return n+'th'

def binwords(message, **bings):
    pass

class HelpSession:
    def __init__(self, client, user):
        self.client = client
        self.user = user
        self.stage = 'default'
        self.aux = None
        self.active = True

    async def stage_default(self):
        await self.client.send_message(
            self.user,
            "You can ask me for help with the bots, or the channels, but "+
            "if you're not sure what sort of things I can do, just say `help`\n"+
            "What seems to be the problem?"
        )
        self.stage='default'

    async def stage_help(self):
        await self.client.send_message(
            self.user,
            "Over the course of this conversation, I'll do my best to answer any "+
            "questions you may have regarding this server and its features.\n"+
            "You can respond to these messages in normal English, and I'll "+
            "do my best to determine what you want. However, if you're having "+
            "trouble getting your point across to me, you can try using single "+
            "word responses, like you're talking to a computer."
        )
        self.stage = 'default'

    async def stage_bots(self):
        await self.client.send_message(
            self.user,
            "Right now, there are two bots on this server:\n"+
            "First and foremost, is **Octavia**, our DJ.  She's here to "
            "make sure everyone always has access to some sweet tunes.\n"
            "And then obviously there's me, **Beymax**. I'm here to help you "
            "out and answer any questions you have, as well as some other "
            "utilities like making polls or creating parties.\n"
            "If you have any further questions about the bots, just type "
            "one of our names. Or, if you'd like to go back, just say so."
        )
        self.stage = 'bots'

    async def stage_channels(self):
        await self.client.send_message(
            self.user,
            "On this server, we try to keep different discussions organized "
            "into separate channels.\n"
            "There's the `general` text channel and `General` voice channel "
            "which are pretty much for whatever you want (first come, first served).\n"
            "The `testing grounds` channels are where bots like myself are "
            "tested before deployment.\n"
            "The `rpg` text and `RPG` voice channels are for discussions related "
            "to the various tabletop games in progress. If you'd like to join "
            "rpg group, reach out to *Brightfire* or *GarethDen*.\n"
            "There's also the `AFK` voice channel, which is where we put you "
            "if you're silent in a voice channel for 30 minutes or so.\n"
            "Additionally, you may see various voice channels with `Party` in "
            "the name. These channels are temporary voice channels used when "
            "`General` is already claimed. You can create one with the `!party` "
            "command.\n"
            "If you'd like to know about any channel in particular, just say "
            "it's name. Otherwise, you can tell me to go back, if you want."
        )
        self.stage = 'channels'

    async def stage_explain_bot(self):
        self.stage = 'explain-bot'
        if self.aux == 'beymax':
            await self.client.send_message(
                self.user,
                "I am Beymax, your personal ~~healthcare~~ **server** companion.\n"
                "I'm here to help in situations like this, where someone wans "
                "to know a bit more about how this server works\n"
                "I can do lots of things like create polls, track overwatch rank, "
                "create voice channels, and even greet people as they join the server!\n"
                "Would you like to know about the commands that I respond to?"
            )
        elif self.aux == 'octavia':
            await self.client.send_message(
                self.user,
                "Octavia is a single-purpose bot. She sits politely in whichever "
                "voice channel she's been summoned to and will play music at "
                "anyone's request. Please note that there is only one of her, so "
                "you'll have to share. If someone else is already using Octavia "
                "please don't summon her into another voice channel.\n"
                "Would you like to know about the commands that she responds to?"
            )

    async def stage_commands(self):
        self.stage = 'stage-commands'
        if self.aux == 'beymax':
            await self.client.send_message(
                self.user,
                "Here is the list of commands I currently support:\n"
                "`!ow <battle#tag>` : Tells me to track your overwatch rank using"
                " that battle tag. Example: `!ow fakename#1234`\n"
                "`!party [party name]` : Tells me to create a temporary party for"
                " you. The party name part is optional. Example: `!party Test`\n"
                "`!disband` : Disbands your party, if you have one\n"
                "`!poll <poll title> | [poll option 1] | [poll option 2] | etc...`"
                " : Creates a reaction based poll. Use `|` to separate the title"
                " and each option (up to ten options). Example: `!poll Is beymax"
                " cool? | Yes | Absolutely`\n"
                "`!ouch` : Asks for my help, but you already knew how to use this one"
            )
        elif self.aux == 'octavia':
            await self.client.send_message(
                self.user,
                "Here are the common commands that Octavia supports:\n"
                "`!np` : Asks Octavia about the current song\n"
                "`!pause` : Asks Octavia to pause the song. Some users may not "
                "have permission to do this.\n"
                "`!play <song>` : Asks Octavia to play a song. You can give her"
                " specific URLs to play (youtube, soundcloud, etc) or you can "
                "give her some search terms and she'll figure it out (she's pretty"
                " smart). Example: `!play never gonna give you up`\n"
                "`!queue` : Asks Octavia about the current playlist\n"
                "`!skip` : Asks Octavia to skip the current song. Some users may"
                " not have permission to do this, and will instead vote to skip\n"
                "`!summon` : Brings Octavia into your current voice channel. "
                "Please be curteous and don't steal her from another channel if "
                "she's already plying music for someone else\n"
                "If you would like more help with Octavia's commands, go to the"
                " #jukebox channel and say `!help`. You can ask for specific help"
                " with `!help <command>` (for example: `!help play`)"
            )
        await self.stage_terminal()

    async def stage_terminal(self):
        self.stage = 'terminal'
        await self.client.send_message(
            self.user,
            "Is there anything else I can help you with?"
        )
    async def stage_explain_channel(self):
        self.stage='explain-channel'
        if self.aux == 'general':
            await self.client.send_message(
                self.user,
                "The general channels are for whatever you want.\n"
                "Talk about games, talk about life, talk about work, talk about "
                "talking -- it's up to you. The General voice channel is first-come"
                " first-serve, so if there's already a group there, you'll need "
                "to use the `!party` command to create your own channel"
            )
        elif self.aux == 'jukebox':
            await self.client.send_message(
                self.user,
                "The jukebox is Octavia's channel. It's the only channel where "
                "Octavia listens to commands, like `!play` or `!summon`. "
                "If you're looking to play some tunes, this is the place to go"
            )
        elif self.aux == 'testing_grounds':
            await self.client.send_message(
                self.user,
                "The testing ground channels are for development purposes. "
                "It's where bots, such as myself, are tested out before new features"
                " make there way out to general use. Locked out? It's nothing "
                "personal. We just only want you to see us at our best!"
            )
        elif self.aux == 'rpgs':
            await self.client.send_message(
                self.user,
                "The RPG channels are for playing RPGs or RPG-related discussion."
                " It's where people who are part of the various RPGs in our group"
                "hold RPG discussion so as not to spam the general channels. "
                "Looking to host or join an RPG? Reach out to Brightfire or "
                "GarethDen and they'll hook you up."
            )
        elif self.aux == 'party':
            await self.client.send_message(
                self.user,
                "Party channels are temporary voice channels used when a group "
                "doesn't want to use General (or if General's already in use). "
                "Parties are created with the `!party` command and usually last"
                " less than a day before I disband them"
            )
        elif self.aux == 'afk':
            await self.client.send_message(
                self.user,
                "The AFK channel is where we put people who sit in a voice channel"
                " without talking or typing for 30 minutes. It's not a punishment"
                " but it helps keep the voice channels clear if you're not really"
                " using them"
            )
        await self.stage_terminal()


    async def digest(self, message):
        print("Digest content:", message)
        cmd = message[0].replace('`', '').lower()
        if self.stage == 'default':
            choice = binwords(
                cmd,
                bots=['bots', 'apps', 'robots'],
                channels=['channels', 'groups', 'messages'],
                help=['help'],
            )
            if choice is None:
                await self.client.send_message(
                    self.user,
                    "I didn't quite understand what you meant by that"
                )
                # await self.stage_default()
            elif choice == 'bots':
                await self.stage_bots()
            elif choice == 'channels':
                await self.stage_channels()
            elif choice == 'help':
                await self.stage_help()
        elif self.stage == 'bots':
            choice = binwords(
                cmd,
                octavia=['octavia', 'tenno', 'dj', 'music'],
                beymax=['beymax', 'baymax', 'jroot', 'dev', 'helper'],
                back=['go', 'back']
            )
            if choice is None:
                await self.client.send_message(
                    self.user,
                    "I didn't quite understand what you meant by that"
                )
            elif choice == 'back':
                await self.stage_default()
            elif choice in {'octavia', 'beymax'}:
                self.aux = choice
                await self.stage_explain_bot()
        elif self.stage == 'explain-bot':
            choice = binwords(
                cmd,
                yes=['yes', 'sure', 'ok', 'yep', 'please'],
                no=['no', 'nope', 'na', 'thanks']
            )
            if choice is None:
                await self.client.send_message(
                    self.user,
                    "I didn't quite understand what you meant by that"
                )
            elif choice == 'yes':
                await self.stage_commands()
            else:
                await self.stage_terminal()
        elif self.stage == 'terminal':
            choice = binwords(
                cmd,
                yes=['yes', 'sure', 'ok', 'yep', 'please'],
                no=['no', 'nope', 'na', 'thanks']
            )
            if choice is None:
                await self.client.send_message(
                    self.user,
                    "I didn't quite understand what you meant by that"
                )
            elif choice == 'yes':
                await self.stage_default()
            else:
                self.active = False
                await self.send_message(
                    self.user,
                    "Okay. Glad to be of servie"
                )
        elif self.stage == 'channels':
            choice = binwords(
                cmd,
                general=['general'],
                jukebox=['jukebox'],
                testing_grounds=['testing', 'grounds', 'testing_grounds'],
                rpgs=['rpgs', 'rpg'],
                afk=['afk'],
                party=['party'] + [
                    party['name'].split() for party in load_db('parties.json', [])
                ]
            )
            if choice is None:
                await self.client.send_message(
                    self.user,
                    "I didn't quite understand what you meant by that"
                )
            elif choice in {'general', 'jukebox', 'testing_grounds', 'rpgs', 'party', 'afk'}:
                self.aux = choice
                await self.stage_explain_channel()


class Beymax(discord.Client):
    help_sessions={}
    general=None
    update_interval = 3600

    async def send_and_wait(self, *args, **kwargs):
        await self.send_message(*args, **kwargs)
        #await self.wait_for_message(author = self.user)

    # def update_and_schedule(self):
    #     loop = asyncio.get_event_loop()
    #     loop.run_until_complete(self.update_overwatch())
    #     loop.close()
    #     self.timer = threading.Timer(self.update_interval, self.update_overwatch)
    #     self.timer.start()

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
        self.mentions = load_db('mentions.json')
        self.status_update_time = 0
        self.party_update_time = 0
        self.invite_update_time = 0
        self.invite_update_interval = 604800 # 7 days
        self._general = discord.utils.get(
            self.get_all_channels(),
            name='general',
            type=discord.ChannelType.text
        )
        self._testing_grounds = discord.utils.get(
            self.get_all_channels(),
            name='testing_grounds',
            type=discord.ChannelType.text
        )
        self.general = self._general
        # self.timer = threading.Timer(self.update_interval, self.update_overwatch)
        # self.timer.start()
        print("Ready to serve!")



    def getname(self, user):
        if 'nick' in dir(user) and type(user.nick) is str and len(user.nick):
            return user.nick
        return user.name

    async def on_message(self, message):
        if message.author == self.user:
            return
        self.mentions[message.author.name] = message.author.mention
        # print(message.author)
        try:
            content = message.content.strip().split()
            content[0] = content[0].lower()
        except:
            return
        # print("Message in channel:", message.channel.name)
        # print("Content:", content)
        if re.match(r'!ouch', content[0]):
            print("Command from", message.author, content)
            await self.send_message(
                message.author,
                "Hello! I am Beymax, your personal ~~healthcare~~ **server** companion.\n"+
                "It's my job to make sure you have a good time and understand the various tools at your disposal in this server\n"+
                "You can ask me for help with the bots, or the channels, but\n"+
                "if you're not sure what sort of things I can do, just say `help`\n"+
                "What seems to be the problem?"
            )
            self.help_sessions[message.author] = HelpSession(self, message.author)
        elif re.match(r'!poll', content[0]):
            print("Command from", message.author, content)
            opts = ' '.join(content[1:]).split('|')
            title = opts.pop(0)
            body = self.getname(message.author)+" has started a poll:\n"
            body+=title+"\n"
            body+="\n".join((
                    "%d) %s"%(num, opt)
                    for (num, opt) in
                    zip(range(1,len(opts)+1), opts)
                ))
            body+="\n\nReact with your vote"
            target = await self.send_message(
                message.channel,
                body
            )
            for i in range(1,len(opts)+1):
                await self.add_reaction(
                    target,
                    (b'%d\xe2\x83\xa3'%i).decode()#emojify(':%s:'%numnames[i])
                )
            await self.delete_message(message)
        elif re.match(r'!kill-beymax', content[0]) or re.match(r'!satisfied', content[0]):
            print("Command from", message.author, content)
            save_db(self.mentions, 'mentions.json')
            await self.close()
        elif re.match(r'!_greet', content[0]):
            print("Command from", message.author, content)
            await self.on_member_join(message.author)
        elif re.match(r'!_announce', content[0]):
            print("Command from", message.author, content)
            await self.send_message(self.general, message.content.strip().replace('!_announce', ''))
        elif re.match(r'!_owreset', content[0]):
            print("Command from", message.author, content)
            state = load_db('stats.json')
            if len(state):
                for user, data in state.items():
                    member = data['member']
                    rating = data['rating']
                    try:
                        current = get_mmr(user)
                        state[user]['rating'] = current
                    except:
                        pass
                ranked = [(user, data['member'], int(data['rating']), rank(int(data['rating']))) for user, data in state.items()]
                ranked.sort(key=lambda x:(x[-1][1], x[-2])) #prolly easier just to sort by mmr
                await self.send_message(
                    self.general, # for now
                    "It's that time again, folks!\n"
                    "The current Overwatch season has come to an end.  Let's see how well all of you did, shall we?"
                )
                index = {
                    ranked[i][0]:postfix(str(len(ranked)-i)) for i in range(len(ranked))
                }
                for user,member,rating,(rn,rclass) in ranked:
                    await self.send_message(
                        self.general,
                        "In "+index[user]+" place, "+
                        (self.mentions[member] if member in self.mentions else member)+
                        " with a rating of "+str(rating)+"\n"
                        +encourage(rn)
                    )
                await self.send_message(
                    self.general,
                    "Let's give everyone a round of applause.  Great show from everybody!\n"
                    "I can't wait to see how you all do next time! [Competitive ranks reset]"
                )
            for user in state:
                state[user]['rating'] = 0
            save_db(state, 'stats.json')

        elif re.match(r'!owupdate', content[0]):
            print("Command from", message.author, content)
            await self.update_overwatch()
        elif re.match(r'!ow', content[0]):
            print("Command from", message.author, content)
            if len(content) != 2:
                await self.send_message(
                    message.channel,
                    "I need you to provide your battle tag\n"
                    "For example, `!ow beymax#1234`"
                )
            else:
                username = content[1].replace('#', '-')
                try:
                    state = load_db('stats.json')
                    state[username] = {
                        'member': message.author.name,
                        'rating': 0
                    }
                    save_db(state, 'stats.json')
                    await self.send_message(
                        message.channel,
                        "Alright! I'll keep track of your stats"
                    )
                    #the timer is prolly going to have to wait for now
                    # threading.Timer(
                    #     120,
                    #     lambda :self.loop.run_until_complete(
                    #         self.update_overwatch()
                    #     )
                    # ).start()
                    await asyncio.sleep(15)
                    await self.update_overwatch()
                except:
                    await self.send_message(
                        message.channel,
                        "I wasn't able to find your Overwatch ranking on Master Overwatch.\n"
                        "Are you sure you're ranked this season?"
                    )
        elif re.match(r'!output-dev', content[0]):
            print("Command from", message.author, content)
            self.general = self._testing_grounds
            await self.send_message(
                self._testing_grounds,
                "Development mode enabled. All messages will be sent to testing grounds"
            )
        elif re.match(r'!output-prod', content[0]):
            print("Command from", message.author, content)
            self.general = self._general
            await self.send_message(
                self._testing_grounds,
                "Production mode enabled. All messages will be sent to general"
            )
        elif re.match(r'!party', content[0]):
            print("Command from", message.author, content)
            if message.server is not None:
                parties = load_db('parties.json', [])
                current_party = None
                for i in range(len(parties)):
                    if message.server.id == parties[i]['server'] and message.author.name == parties[i]['creator'] and time.time()-parties[i]['time'] < 86400:
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
                        'creator':message.author.name,
                        'time': time.time()
                    })
                save_db(parties, 'parties.json')
        elif re.match(r'!disband', content[0]):
            print("Command from", message.author, content)
            if message.server is not None:
                parties = load_db('parties.json', [])
                pruned = []
                for i in range(len(parties)):
                    if message.server.id == parties[i]['server'] and message.author.name == parties[i]['creator']:
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
        elif isinstance(message.channel, discord.PrivateChannel) and message.author in self.help_sessions:
            await self.help_sessions[message.author].digest(content)
        await self.maintenance_tasks()
        self.help_sessions = {user:session for user,session in self.help_sessions if session.active}

    async def on_member_join(self, member):
        await self.send_message(
            self.general,
            "Welcome, "+member.mention+"!\n"+
            "https://giphy.com/gifs/hello-hi-dzaUX7CAG0Ihi"
        )

    async def maintenance_tasks(self):
        current = time.time()
        if current - self.status_update_time > self.update_interval:
            name = select_status()
            print("CHANGING STATUS:", name)
            await self.change_presence(
                game=discord.Game(name=name)
            )
            await self.update_overwatch()
            self.status_update_time = current
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
        if current - self.party_update_time > 60:
            parties = load_db('parties.json', [])
            pruned = []
            for i in range(len(parties)):
                if current - parties[i]['time'] >= 86400:
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
            self.party_update_time = current

    async def update_overwatch(self):
        state = load_db('stats.json')
        for user, data in state.items():
            member = data['member']
            rating = data['rating']
            try:
                current = get_mmr(user)
                state[user]['rating'] = current
                currentRank = rank(current)
                oldRank = rank(int(rating))
                if currentRank[0] > oldRank[0]:
                    body = "Everyone put your hands together for "
                    body += self.mentions[member] if member in self.mentions else member
                    body += " who just reached "
                    body += currentRank[1]
                    body += " in Overwatch!"
                    if currentRank[0] >= 4:
                        # Ping the channel for anyone who reached platinum or above
                        body = body.replace('Everyone', '@everyone')
                    await self.send_message(
                        self.general, #for now
                        body
                    )
            except:
                pass
        save_db(state, 'stats.json')

def load_db(filename, default=None):
    try:
        with open(filename) as reader:
            return json.load(reader)
    except FileNotFoundError:
        return {} if default is None else default

def save_db(data, filename):
    with open(filename, 'w') as writer:
        return json.dump(data, writer)

def sanitize_channel(name):
    return name.replace('~!@#$%^&*()-', '_')

if __name__ == '__main__':
    with open("token.txt") as r:
        Beymax().run(r.read().strip())
