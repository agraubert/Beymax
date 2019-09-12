from bots.core import CoreBot, EnableUtils
from bots.birthday import EnableBirthday
from bots.bug import EnableBugs
from bots.help import EnableHelp
from bots.ow import EnableOverwatch
from bots.party import EnableParties
from bots.poll import EnablePolls
from bots.cash import EnableCash
from bots.games import EnableGames
from bots.args import Arg
import discord
import asyncio
import random
random.seed()

"""Note:
This file is what we consider the 'reference implimentation' of Beymax.
bots/core.py and bots/utils.py contain the development framework upon which
all of Beymax is built. The remaining bots/*.py files build unique feature sets
out of this framework. This file is where we tie it all together. Starting from
the CoreBot (defined in bots/core.py) we add in a few additional just-for-fun
features (greetings, statuses, etc) which we wanted on our server, but which we didn't
think justified an entire feature set. Then we enable all of the other features
using EnableAll, and the various Enable___ functions. Lastly, the bot is launched
by reading a token out of token.txt

You are free to use any of the features in this file and others to get your bot
setup as you wish. Note that bots/help.py is considered server-specific and just
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
            'with the server settings',
            'with the Discord API',
            'with your very lives',
            'Metadata Salesman'
        ],
        1
    )[0]


def ConstructBeymax(): #enable Beymax-Specific commands
    beymax = CoreBot()
    beymax = EnableGames(beymax) # Story needs priority on special message recognition

    @beymax.subscribe('after:ready')
    async def ready_up(self, event):
        print('Logged in as') #then run Beymax-Specific startup (print info)
        print(self.user.name)
        print(self.user.id)
        print('------')
        print("Bot connected to:")
        for server in self.servers:
            print(server.name)
        print("Bot has access to:")
        for channel in self.get_all_channels():
            print(channel.name, channel.type)
        print("Ready to serve!")
        self.dispatch('task:update_status') # manually set status at startup
        from bots.utils import Database

    @beymax.subscribe('member_join')
    async def greet_member(self, event, member): #greet new members
        await self.send_message(
            self.fetch_channel('general'),
            "Welcome, "+member.mention+"!\n"
            "I am %s, your personal ~~healthcare~~ server companion\n"
            "https://giphy.com/gifs/hello-hi-dzaUX7CAG0Ihi\n"
            "Try typing `$!permissions` to find the list of commands you can use "
            "or `$!ouch` to get help with them" % (
                self.user.mention
            )
        )
        if not member.bot:
            await asyncio.sleep(10)
            message = await self.send_message(
                member,
                "We're glad to have you on our server! Would you like a brief "
                "introduction on what I can do? (Yes/No)"
            )
            response = await self.wait_for(
                'message',
                check=lambda m : m.channel == message.channel
            )
            if response is None or response.content.lower() == 'no':
                await self.send_message(
                    message.channel,
                    "Alright. Have fun, and enjoy your stay!"
                )
                return
            elif response.content.lower() != 'yes':
                await self.send_message(
                    message.channel,
                    "I didn't understand your response, but I'll go ahead and"
                    " give you the rundown anyways"
                )
            await self.send_message(
                message.channel,
                "You can use the `$!birthday` command so I'll post a message on your birthday. "
                "If you're an Overwatch player, you can use `$!ow` and I'll keep track of your competitive rank. "
                "You can use the `$!party` command if you want to make a voice channel for you your friends to hang out for a while. "
                "And if you're ever bored, try `$!bid` to play a game in the $CHANNEL channel. "
                "These are just a few of my commands; you can get the full list with `$!permissions`,"
                " and if you ever need my help with a command, just say `$!ouch`",
                interp=self.fetch_channel('story')
            )

    @beymax.add_command('kill-beymax', aliases=['satisfied'], empty=True)
    async def cmd_shutdown(self, message, content):
        """
        `$!satisfied` : Shuts down beymax
        """
        await self.shutdown()

    @beymax.add_command('coinflip', empty=True)
    async def cmd_flip(self, message, content):
        await self.send_message(
            message.channel,
            "Heads" if random.random() < 0.5 else "Tails"
        )

    @beymax.add_command('_greet', empty=True)
    async def cmd_greet(self, message, content):
        """
        `$!_greet` : Manually triggers a greeting (I will greet you)
        """
        self.dispatch('member_join', message.author)

    @beymax.add_task(3600) # 1 hour
    async def update_status(self, *args):
        name = select_status()
        print("CHANGING STATUS:", name)
        await self.change_presence(
            activity=discord.Game(name=name)
        )

    @beymax.add_command('_status', Arg('status', remainder=True, help="Manually set this status"))
    async def cmd_status(self, message, args):
        if len(args.status):
            name = ' '.join(args.status).strip()
        else:
            name = select_status()
        await self.change_presence(
            activity=discord.Game(name=name)
        )

    def pick(self, message):
        return random.random() < 0.05

    @beymax.add_special(pick)
    async def react(self, message, content):
        await message.add_reaction(
            b'\xf0\x9f\x91\x8d'.decode() if random.random() < 0.8 else b'\xf0\x9f\x8d\x86'.decode() # :thumbsup: and sometimes :eggplant:
        )
        # print("granting reaction xp")
        self.dispatch(
            'grant_xp',
            message.author,
            2
        )

    beymax.EnableAll( #enable all sub-bots
        EnableUtils,
        EnableBirthday,
        EnableBugs,
        EnableHelp,
        EnableOverwatch,
        EnableParties,
        EnablePolls,
        EnableCash,
    )

    return beymax

if __name__ == '__main__':
    with open("token.txt") as r:
        try:
            bey = ConstructBeymax()
            bey.run(r.read().strip())
        finally:
            print(bey._dbg_event_queue)
