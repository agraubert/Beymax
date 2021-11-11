from beymax.core import Client, CommandSuite
from beymax.bots.birthday import Birthdays
from beymax.bots.help import Help
from beymax.bots.party import Parties
from beymax.bots.poll import Polls
from beymax.bots.games import Games
from beymax.bots.utility import Utility
from beymax.args import Arg, UserType
from beymax.utils import getname, DBView
import discord
import asyncio
import random
import aiohttp
from editdistance import eval as leven
random.seed()

"""Note:
This file is what we consider the 'reference implimentation' of Beymax.
bots/core.py and bots/utils.py contain the development framework upon which
all of Beymax is built. The remaining bots/*.py files build unique feature sets
out of this framework. This file is where we tie it all together. Starting from
the CoreBot (defined in bots/core.py) we add in a few additional just-for-fun
features (greetings, statuses, etc) which we wanted on our guild, but which we didn't
think justified an entire feature set. Then we enable all of the other features
using EnableAll, and the various Enable___ functions. Lastly, the bot is launched
by reading a token out of token.txt

You are free to use any of the features in this file and others to get your bot
setup as you wish. Note that bots/help.py is considered guild-specific and just
generally bad. We appologize and intend to deprecate or fix this code in the future

If you have any trouble, feel free to reach out to us by opening an issue on our
github repo https://github.com/agraubert/beymax
"""

def select_status():
    #return a randomly selected status message from the list
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
            'with the guild settings',
            'with the Discord API',
            'with your very lives',
            'Metadata Salesman',
            'with the STONK market'
        ],
        1
    )[0]

Extras = CommandSuite('Extras')
MEMELOCK = asyncio.Lock()
MEMES = None

async def get_meme_url(session, meme_id, username, password, top_text, bottom_text=None):
    meme_key = '{}:{}:{}'.format(
        meme_id,
        top_text,
        '' if bottom_text is None else bottom_text
    )
    async with DBView('memecache') as db:
        if meme_key not in db['memecache']:
            print("Loading new meme")
            meme = {
                'template_id': meme_id,
                'username': username,
                'password': password,
                'text0': top_text
            }
            if bottom_text is not None:
                meme['text1'] = bottom_text
            async with session.post('https://api.imgflip.com/caption_image', data=meme) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'success' in data and data['success']:
                        db['memecache'][meme_key] = {
                            'url': data['data']['url'],
                            'page': data['data']['page_url']
                        }
                    else:
                        return False, {'status': response.status, 'response': data}
                else:
                    return False, {'status': response.status, 'response': data}
        else:
            print("Using cached meme")
        return True, db['memecache'][meme_key]


@Extras.subscribe('after:ready', once=True)
async def ready_up(self, event):
    print('Logged in as') #then run Beymax-Specific startup (print info)
    print(self.user.name, self.user.id)
    if self.primary_guild is not None:
        print("Primary Guild:", self.primary_guild.name)
    else:
        print("Bot connected to:", len(self.guilds), "guilds")
    print("Bot has access to:", len([*self.get_all_channels()]), "channels")
    print("Ready to serve!")
    self.dispatch('task:update_status') # manually set status at startup

@Extras.subscribe('member_join')
async def greet_member(self, event, member): #greet new members
    username = self.config_get('imgflip', 'username')
    password = self.config_get('imgflip', 'password')
    rich_greet = False
    if self.config_get("imgflip", "greet") and not (username is None or password is None):
        async with aiohttp.ClientSession() as sesh:
            rich_greet, meme = await get_meme_url(
                sesh,
                self.config_get('imgflip', 'greet', 'template', default='119139145'),
                username,
                password,
                self.config_get('imgflip', 'greet', 'top_text', default='{} in five minutes'.format(getname(member))),
                self.config_get('imgflip', 'greet', 'bottom_text', default='Leave Server')
            )
            if rich_greet:
                await self.send_rich_message(
                    self.fetch_channel('general'),
                    content=(
                        "Welcome, "+member.mention+"!\n"
                        "I am %s, your personal ~~healthcare~~ **server** companion\n"
                        "https://giphy.com/gifs/hello-hi-dzaUX7CAG0Ihi\n"
                        "Try typing `$!permissions` to find the list of commands you can use "
                        "or `$!ouch` to get help with them" % (
                            self.user.mention
                        )
                    ),
                    author=member,
                    image=meme['url'],
                    footer='jk please dont go'
                )
            else:
                print("Fail", meme)
    if not rich_greet:
        await self.send_rich_message(
            self.fetch_channel('general'),
            content=(
                "Welcome, "+member.mention+"!\n"
                "I am %s, your personal ~~healthcare~~ **server** companion\n"
                "Try typing `$!permissions` to find the list of commands you can use "
                "or `$!ouch` to get help with them" % (
                    self.user.mention
                )
            ),
            image='https://media0.giphy.com/media/dzaUX7CAG0Ihi/giphy.gif',
            author=member
        )
    if not member.bot:
        await asyncio.sleep(10)
        await self.send_message(
            member,
            "We're glad to have you on our guild! Would you like a brief "
            "introduction on what I can do? (Yes/No)"
        )
        response = await self.wait_for(
            'message',
            check=lambda m : m.channel == member.dm_channel and m.author.id == member.id
        )
        if response is None or response.content.lower() == 'no':
            await self.send_message(
                member,
                "Alright. Have fun, and enjoy your stay!"
            )
            return
        elif response.content.lower() != 'yes':
            await self.send_message(
                member,
                "I didn't understand your response, but I'll go ahead and"
                " give you the rundown anyways"
            )
        await self.send_message(
            member,
            "You can use the `$!birthday` command so I'll post a message on your birthday. "
            "If you're an Overwatch player, you can use `$!ow` and I'll keep track of your competitive rank. "
            "You can use the `$!party` command if you want to make a voice channel for you your friends to hang out for a while. "
            "And if you're ever bored, try `$!bid` to play a game in the $CHANNEL channel. "
            "These are just a few of my commands; you can get the full list with `$!permissions`,"
            " and if you ever need my help with a command, just say `$!ouch`",
            interp=self.fetch_channel('story')
        )

@Extras.add_command('kill-beymax', aliases=['satisfied'])
async def cmd_shutdown(self, message):
    """
    `$!satisfied` : Shuts down beymax
    """
    await self.shutdown()

@Extras.add_command('coinflip')
async def cmd_flip(self, message):
    await self.send_message(
        message.channel,
        "Heads" if random.random() < 0.5 else "Tails"
    )

@Extras.add_command('_greet', Arg('target', type=UserType(Extras), nargs='?', default=None))
async def cmd_greet(self, message, target):
    """
    `$!_greet` : Manually triggers a greeting (I will greet you)
    """
    self.dispatch('member_join', target if target is not None else message.author)

@Extras.add_task(3600) # 1 hour
async def update_status(self, *args):
    name = select_status()
    print("CHANGING STATUS:", name)
    await self.change_presence(
        activity=discord.Game(name=name)
    )

@Extras.add_command('_status', Arg('status', remainder=True, help="Manually set this status"))
async def cmd_status(self, message, status):
    if len(status):
        name = ' '.join(status).strip()
    else:
        name = select_status()
    await self.change_presence(
        activity=discord.Game(name=name)
    )

def pick(self, message):
    return random.random() < 0.05

@Extras.add_special(pick)
async def react(self, message):
    await message.add_reaction(
        b'\xf0\x9f\x91\x8d'.decode() if random.random() < 0.8 else b'\xf0\x9f\x8d\x86'.decode() # :thumbsup: and sometimes :eggplant:
    )
    # print("granting reaction xp")
    self.dispatch(
        'grant_xp',
        message.author,
        2
    )

@Extras.add_special(lambda s,m: m.content.startswith('!help'))
async def maybe_help(self, message):
    try:
        await self.wait_for(
            'message',
            check=lambda m:m.author.bot,
            timeout=5
        )
    except asyncio.TimeoutError:
        await self.send_message(
            message.channel,
            "I think you might be talking to me. If you need help with $MENTION, use `!ouch`"
        )

@Extras.add_command('meme', Arg('meme_name', help="Search text for the base meme"), Arg("top", help="Top text"), Arg("bottom", help="Bottom Text", nargs='?', default=None), delimiter='|')
async def cmd_meme(self, message, meme_name, top, bottom):
    """
    `$!meme <name> | <top text> [| <bottom text>]` : Generates a meme
    Example: $!meme mocking spongebob | Look at me, I'm a bot
    """
    global MEMES
    username = self.config_get('imgflip', 'username')
    password = self.config_get('imgflip', 'password')
    if username is None or password is None:
        return await self.send_message(
            message.channel,
            "imgflip API credentials not set in the config"
        )
    async with aiohttp.ClientSession() as sesh:
        if MEMES is None:
            async with MEMELOCK:
                async with sesh.get('https://api.imgflip.com/get_memes') as response:
                    MEMES = (await response.json())['data']['memes']
                    print(len(MEMES))
        selected = [meme for meme in MEMES if meme_name.lower() in meme['name'].lower()]
        query = {
            'q': meme_name,
            'transparent_only': 0,
            'include_nsfw': 1,
            'allow_gifs': 0
        }
        try:
            async with sesh.get('https://imgflip.com/ajax_meme_search_new', params=query) as response:
                if response.status == 200:
                    selected += (await response.json())['results']
        except:
            await self.trace()
        if len(selected) == 0:
            selected = sorted(
                [meme for meme in MEMES if leven(meme['name'].lower(), meme_name.lower()) < len(meme_name)],
                key=lambda meme:leven(meme['name'].lower(), meme_name.lower())
            )
            if len(selected) == 0:
                return await self.send_message(
                    message.channel,
                    '{} I couldn\'t find any memes on imgflip matching "{}"'.format(
                        message.author.mention,
                        meme_name
                    )
                )
            selected = selected[0]
        else:
            selected = sorted(
                selected,
                key=lambda meme:leven(meme['name'].lower(), meme_name.lower())
            )[0]
        if 'url' in selected:
            prompt = await self.send_rich_message(
                message.channel,
                content="Is this what you were looking for? (Yes/No)",
                image=selected['url'],
                title=selected['name']
            )
        else:
            result, data = await get_meme_url(
                sesh,
                selected['id'],
                username,
                password,
                ' ',
            )
            if result:
                prompt = await self.send_rich_message(
                    message.channel,
                    content="Is this what you were looking for? (Yes/No)",
                    image=data['url'],
                    title=selected['name']
                )
            else:
                promt = await self.send_message(
                    message.channel,
                    "I couldn't load a preview for this meme, but here's the title: {}. Is this what you were looking for? (Yes/No)".format(
                        selected['name']
                    )
                )
        response = await self.wait_for(
            'message',
            check=lambda m : m.channel == message.channel and m.author.id == message.author.id
        )
        try:
            await prompt.delete()
        except:
            pass
        try:
            await response.delete()
        except:
            pass
        if response.content.lower() != 'yes':
            return await self.send_message(
                message.channel,
                "I'm sorry, I couldn't find any matching memes. Please try again with a different query"
            )
        result, data = await get_meme_url(
            sesh,
            selected['id'],
            username,
            password,
            top,
            bottom
        )
        if result:
            await self.send_rich_message(
                message.channel,
                author=message.author,
                title=selected['name'],
                url=data['page'],
                image=data['url'],
                footer="{} \u2665's memes".format(
                    getname(self.user)
                )
            )
        else:
            await self.send_message(
                message.channel,
                "I'm sorry, I was unable to craft your excellent meme. The imgflip api responded with {}".format(
                    data
                )
            )


if __name__ == '__main__':
    with open("token.txt") as r:
        beymax = Client()
        beymax.enableSuites(
            Games,
            Extras,
            Utility,
            Birthdays,
            Help,
            Parties,
            Polls
        )
        beymax.run(r.read().strip())
