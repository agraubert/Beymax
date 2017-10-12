import discord
import re
import asyncio
import requests
import time
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
                "First and foremost, is **Octavia**, our DJ.  She's here to "
                "make sure everyone always has access to some sweet tunes\n"
                "And obviously there's me, **Beymax**. I'm here to help you "
                "out and answer any questions you have, as well as some other "
                "utilities like making polls, or greeting new users\n"
                "If you have any further questions about the bots, just type "
                "one of our names!"
            )
        elif cmd == "channels":
            await self.client.send_and_wait(
                self.user,
                "On this server, we try to keep different discussions organized "
                "into separate channels.\n"
                "There's the `general` text channel and `General` voice channel "
                "which are for any discussions\n"
                "The `testing grounds` channels are where bots like myself are "
                "tested before deployment.\n"
                "Beyond that, the different channels are mostly just organized "
                "for different games"
            )


class Beymax(discord.Client):
    help_sessions={}
    general=None
    users={}
    update_interval = 3600

    async def send_and_wait(self, *args, **kwargs):
        await self.send_message(*args, **kwargs)
        #await self.wait_for_message(author = self.user)

    def update_and_schedule(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.update_overwatch())
        loop.close()
        self.timer = threading.Timer(self.update_interval, self.update_overwatch)
        self.timer.start()

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
        self.status_update_time = 0
        self.party_update_time = 0
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
        self.timer = threading.Timer(self.update_interval, self.update_overwatch)
        self.timer.start()
        print("Ready to serve!")



    def getname(self, user):
        if 'nick' in dir(user) and type(user.nick) is str and len(user.nick):
            return user.nick
        return user.name

    async def on_message(self, message):
        if message.author == self.user:
            return
        self.users[message.author.name] = message.author
        print(message.author)
        content = message.content.strip().split()
        content[0] = content[0].lower()
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
            await self.close()
        elif re.match(r'!_greet', content[0]):
            await self.on_member_join(message.author)
        elif re.match(r'!_announce', content[0]):
            await self.send_message(self.general, message.content.strip().replace('!_announce', ''))
        elif re.match(r'!_owreset', content[0]):
            try:
                with open('stats.txt', 'r') as handle:
                    state={}
                    for line in handle:
                        if len(line.strip()):
                            line = line.split('\t')
                            state[line[0]] = line[1:]
            except FileNotFoundError:
                pass
            if len(state):
                for user, (member, rating) in state.items():
                    try:
                        current = get_mmr(user)
                        state[user] = [member, str(rating)]
                    except:
                        pass
                ranked = [(user, member, int(rating), rank(int(rating))) for user, (member, rating) in state.items()]
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
                        (self.users[member].mention if member in self.users else member)+
                        " with a rating of "+str(rating)+"\n"
                        +encourage(rn)
                    )
                await self.send_message(
                    self.general,
                    "Let's give everyone a round of applause.  Great show from everybody!\n"
                    "I can't wait to see how you all do next time! [Competitive ranks reset]"
                )
            with open('stats.txt', 'w') as handle:
                for (k,v) in state.items():
                    handle.write(
                        '\t'.join([
                            k,
                            v[0],
                            '0'
                        ])
                    )

        elif re.match(r'!owupdate', content[0]):
            await self.update_overwatch()
        elif re.match(r'!ow', content[0]):
            username = content[1].replace('#', '-')
            try:
                # rating = get_mmr(username)
                with open('stats.txt', 'r') as handle:
                    state={}
                    for line in handle:
                        if len(line.strip()):
                            line = line.split('\t')
                            state[line[0]] = line[1:]
                    state[username] = [message.author.name, '1']#str(rating)]
                with open('stats.txt', 'w') as handle:
                    for (k,v) in state.items():
                        handle.write(
                            '\t'.join([
                                k,
                                *v
                            ])
                        )
                await self.send_message(
                    message.channel,
                    "Alright! I'll keep track of your stats"
                )
                threading.Timer(120, self.update_overwatch).start()
            except:
                await self.send_message(
                    message.channel,
                    "I wasn't able to find your Overwatch ranking on Master Overwatch.\n"
                    "Are you sure you're ranked this season?"
                )
        elif re.match(r'!output-dev', content[0]):
            self.general = self._testing_grounds
            await self.send_message(
                self._testing_grounds,
                "Development mode enabled. All messages will be sent to testing grounds"
            )
        elif re.match(r'!output-prod', content[0]):
            self.general = self._general
            await self.send_message(
                self._testing_grounds,
                "Production mode enabled. All messages will be sent to general"
            )
        elif re.match(r'!party', content[0]):
            if message.server is not None:
                parties = load_db('parties.json')
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
                    # Sanitize channel name
                    suffix = 1
                    while name+str(suffix) in parties:
                        suffix += 1
                    name += str(suffix)
                    channel = await self.create_channel(
                        message.server,
                        name,
                        discord.ChannelType.voice
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
            if message.server is not None:
                parties = load_db('parties.json')
                pruned = []
                for i range(len(parties)):
                    if message.server.id == parties[i]['server'] and message.author.name == parties[i]['creator']:
                        await self.delete_channel(
                            discord.utils.get(
                                self.get_all_channels(),
                                id=parties[i]['id'],
                                type=discord.ChannelType.voice
                            )
                        )
                        pruned.append(parties[i]['name'])
                        parties[i]['id'] = None
                parties = [party for party in parties if party['id'] is not None]
                save_db(parties, 'parties.json')
                if len(pruned) == 1:
                    await self.send_message(
                        self.general,
                        '`%s` has been disbanded. If you would like to create another party, use the `!party` command'
                    )
                elif len(pruned) > 1:
                    await self.send_message(
                        self.general,
                        'The following parties have been disbanded:\n'
                        '\n'.join('`%s`' party for party in pruned)
                        '\nIf you would like to create another party, use the `!party` command'
                    )
        elif isinstance(message.channel, discord.PrivateChannel) and message.author in self.help_sessions:
            await self.help_sessions[message.author].digest(content)
        await self.maintenance_tasks()

    async def on_member_join(self, member):
        await self.send_message(
            self.general,
            "Welcome, "+member.mention+"!\n"+
            "https://giphy.com/gifs/hello-hi-dzaUX7CAG0Ihi"
        )

    async def maintenance_tasks(self):
        current = time.time()
        if current - self.status_update_time < self.update_interval:
            await self.change_presence(
                game=discord.Game(name=select_status())
            )
            await self.update_overwatch()
            self.status_update_time = current
        if current - self.party_update_time < 60:
            parties = load_db('parties.json')
            pruned = []
            for i range(len(parties)):
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
                        parties[i]['id'] = None
            parties = [party for party in parties if party['id'] is not None]
            save_db(parties, 'parties.json')
            if len(pruned) == 1:
                await self.send_message(
                    self.general,
                    '`%s` has been disbanded. If you would like to create another party, use the `!party` command'
                )
            elif len(pruned) > 1:
                await self.send_message(
                    self.general,
                    'The following parties have been disbanded:\n'
                    '\n'.join('`%s`' party for party in pruned)
                    '\nIf you would like to create another party, use the `!party` command'
                )
            self.party_update_time = current

    async def update_overwatch(self):
        try:
            with open('stats.txt', 'r') as handle:
                state={}
                for line in handle:
                    if len(line.strip()):
                        line = line.split('\t')
                        state[line[0]] = line[1:]
            print(state)
            for user, (member, rating) in state.items():
                try:
                    current = get_mmr(user)
                    state[user] = [member, str(current)]
                    currentRank = rank(current)
                    oldRank = rank(int(rating))
                    if currentRank[0] > oldRank[0]:
                        body = "Everyone put your hands together for "
                        body += self.users[member].mention if member in self.users else member
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
            print(state)
            with open('stats.txt', 'w') as handle:
                for (k,v) in state.items():
                    handle.write(
                        '\t'.join([
                            k,
                            *v
                        ])
                    )
        except FileNotFoundError:
            pass

def load_db(filename):
    try:
        with open(filename) as reader:
            return json.load(reader)
    except FileNotFoundError:
        return {}

def save_db(data, filename):
    with open(filename, 'w') as writer:
        return json.dump(data, writer)

if __name__ == '__main__':
    with open("token.txt") as r:
        Beymax().run(r.read().strip())
