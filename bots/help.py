from .core import CoreBot
from .utils import sanitize, load_db
import discord
import asyncio

def binwords(message, **bins):
    try:
        lookup = {member:target for target,members in bins.items() for member in members}
        results = {}
        for word in message.split():
            if word in lookup:
                key = lookup[word]
                if key not in results:
                    results[key] = 1
                else:
                    results[key] += 1
        return max(
            (count, item) for item,count in results.items()
        )[-1]
    except:
        return

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
            await self.client.send_message( #->generalize from self.commands
                self.user,
                "Here is the list of commands I currently support:\n"
                "`!ow <battle#tag>` : Tells me to track your overwatch rank using"
                " that battle tag. Example: `!ow fakename#1234`\n"
                "`!party [party name]` : Tells me to create a temporary party for"
                " you. The party name part is optional. Example: `!party Test`\n"
                "`!disband` : Disbands your party, if you have one\n"
                "`!birthday <your birthday>` : Informs me of your birthday so I"
                " can congratulate you when it comes. Example: `!birthday 1/1/1970`\n"
                "`!poll <poll title> | [poll option 1] | [poll option 2] | etc...`"
                " : Creates a reaction based poll. Use `|` to separate the title"
                " and each option (up to ten options). Example: `!poll Is beymax"
                " cool? | Yes | Absolutely`\n"
                "`!bug [feedback or bug report]` : Opens a new ticket with your"
                " feedback. Example: `!bug Beymax didn't understand me in a help session`\n"
                "`!comment <bug ID> [your comment]` : Comments on an open issue."
                " Example: `!comment 2 The help system is working great!`\n"
                "`!thread <bug ID>` : Pulls up the full comment thread of an issue. "
                "Example: `!thread 2`\n"
                "`!bug:unsubscribe <bug ID>` : Removes you from the list of mentions"
                " on an open issue. Example: `!bug:unsubscribe 2`\n"
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
        if not self.active:
            return
        cmd = sanitize(message, '`~!@#$%^&*()-_=+{[]}\\|,.<>/?;:\'"').lower()
        print("Digest content:", cmd)
        if self.stage == 'default':
            choice = binwords(
                cmd,
                bots=['bots', 'apps', 'robots'],
                octavia=['octavia', 'tenno', 'dj', 'music'],
                beymax=['beymax', 'baymax', 'jroot', 'dev', 'helper', 'you', 'yourself'],
                beymax_commands=[command[1:] for command in self.client.commands],
                channels=['channels', 'groups', 'messages', 'channel'],
                general=['general'],
                jukebox=['jukebox'],
                testing_grounds=['testing', 'grounds', 'testing_grounds'],
                rpgs=['rpgs', 'rpg'],
                afk=['afk'],
                party=['party'] + [
                    party['name'].split() for party in load_db('parties.json', [])
                ],
                help=['help'],
            )
            if choice is None:
                await self.client.send_message(
                    self.user,
                    "I didn't quite understand what you meant by that."
                    " If you think I should have been able to understand, "
                    " type `!bug Beymax didn't understand '%s'`" % message
                )
                # await self.stage_default()
            elif choice == 'bots':
                await self.stage_bots()
            elif choice in {'octavia', 'beymax'}:
                self.aux = choice
                await self.stage_explain_bot()
            elif choice == 'beymax_commands':
                self.aux = 'beymax'
                await self.stage_commands()
            elif choice == 'channels':
                await self.stage_channels()
            elif choice in {'general', 'jukebox', 'testing_grounds', 'rpgs', 'party', 'afk'}:
                self.aux = choice
                await self.stage_explain_channel()
            elif choice == 'help':
                await self.stage_help()
        elif self.stage == 'bots':
            choice = binwords(
                cmd,
                octavia=['octavia', 'tenno', 'dj', 'music'],
                beymax=['beymax', 'baymax', 'jroot', 'dev', 'helper', 'you', 'yourself'],
                back=['go', 'back']
            )
            if choice is None:
                await self.client.send_message(
                    self.user,
                    "I didn't quite understand what you meant by that."
                    " If you think I should have been able to understand, "
                    " type `!bug Beymax didn't understand '%s'`" % message
                )
            elif choice == 'back':
                await self.stage_default()
            elif choice in {'octavia', 'beymax'}:
                self.aux = choice
                await self.stage_explain_bot()
        elif self.stage == 'explain-bot':
            choice = binwords(
                cmd,
                yes=['yes', 'sure', 'ok', 'yep', 'please', 'okay', 'yeah'],
                no=['no', 'nope', 'na', 'thanks']
            )
            if choice is None:
                await self.client.send_message(
                    self.user,
                    "I didn't quite understand what you meant by that."
                    " If you think I should have been able to understand, "
                    " type `!bug Beymax didn't understand '%s'`" % message
                )
            elif choice == 'yes':
                await self.stage_commands()
            else:
                await self.stage_terminal()
        elif self.stage == 'terminal':
            choice = binwords(
                cmd,
                bots=['bots', 'apps', 'robots'],
                octavia=['octavia', 'tenno', 'dj', 'music'],
                beymax=['beymax', 'baymax', 'jroot', 'dev', 'helper', 'you', 'yourself'],
                beymax_commands=[command[1:] for command in self.client.commands],
                channels=['channels', 'groups', 'messages', 'channel'],
                general=['general'],
                jukebox=['jukebox'],
                testing_grounds=['testing', 'grounds', 'testing_grounds'],
                rpgs=['rpgs', 'rpg'],
                afk=['afk'],
                party=['party'] + [
                    party['name'].split() for party in load_db('parties.json', [])
                ],
                help=['help'],
                yes=['yes', 'sure', 'ok', 'yep', 'please', 'okay', 'yeah'],
                no=['no', 'nope', 'nah', 'thanks']
            )
            if choice is None:
                await self.client.send_message(
                    self.user,
                    "I didn't quite understand what you meant by that."
                    " If you think I should have been able to understand, "
                    " type `!bug Beymax didn't understand '%s'`" % message
                )
            elif choice == 'yes':
                await self.stage_default()
            elif choice == 'bots':
                await self.stage_bots()
            elif choice in {'octavia', 'beymax'}:
                self.aux = choice
                await self.stage_explain_bot()
            elif choice == 'beymax_commands':
                self.aux = 'beymax'
                await self.stage_commands()
            elif choice == 'channels':
                await self.stage_channels()
            elif choice in {'general', 'jukebox', 'testing_grounds', 'rpgs', 'party', 'afk'}:
                self.aux = choice
                await self.stage_explain_channel()
            elif choice == 'help':
                await self.stage_help()
            else:
                self.active = False
                await self.client.send_message(
                    self.user,
                    "Okay. Glad to be of service"
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
                    "I didn't quite understand what you meant by that."
                    " If you think I should have been able to understand, "
                    " type `!bug Beymax didn't understand '%s'`" % message
                )
            elif choice in {'general', 'jukebox', 'testing_grounds', 'rpgs', 'party', 'afk'}:
                self.aux = choice
                await self.stage_explain_channel()

def EnableHelp(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.help_sessions = {}

    @bot.add_command('!ouch')
    async def cmd_help(self, message, content):
        """`!ouch` : Asks for my help"""
        await self.send_message(
            message.author,
            "Hello! I am Beymax, your personal ~~healthcare~~ **server** companion.\n"+
            "It's my job to make sure you have a good time and understand the various tools at your disposal in this server\n"+
            "You can ask me for help with the bots, or the channels, but\n"+
            "if you're not sure what sort of things I can do, just say `help`\n"+
            "What seems to be the problem?"
        )
        self.help_sessions[message.author.id] = HelpSession(self, message.author)

    def should_help(self, message):
        return isinstance(message.channel, discord.PrivateChannel) and message.author.id in self.help_sessions

    @bot.add_special(should_help)
    async def help_digest(self, message, content):
        await self.help_sessions[message.author.id].digest(message.content)
        self.help_sessions = {user:session for user,session in self.help_sessions.items() if session.active}

    def confused(self, message):
        return isinstance(message.channel, discord.PrivateChannel) and message.author.id not in self.help_sessions

    @bot.add_special(confused)
    async def suggest_help(self, message, content):
        await self.send_message(
            message.channel,
            "I can't tell if you're asking for my help or not. If you would like"
            " to start a help session, say `!ouch`"
        )

    return bot
