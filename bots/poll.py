from .core import CoreBot
from .utils import getname
from .args import Arg
import discord
import asyncio

def EnablePolls(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.polls = {}

    @bot.add_command(
        '!poll',
        Arg('title', help="Poll Title"),
        Arg("options", nargs='*', help="Poll options"),
        delimiter='|'
    )
    async def cmd_poll(self, message, args):
        """
        `!poll <poll title> | [Option 1] | [Option 2] | [etc...]` : Creates a poll
        Example: `!poll Is Beymax cool? | Yes | Definitely`
        """
        #The argparse API is killing the blank handling, but I think that's okay
        opts = [
            (opt.rstrip() if '~<blank>' not in opt else opt)
            for opt in args.options
        ]
        if sum(1 for opt in opts if not len(opt)):
            await self.send_message(
                message.author,
                "Your poll command contained trailing or adjacent `|` characters"
                " which resulted in blank fields that I'm going to ignore. If"
                " the blank fields were intentional, add `~<blank>` into each"
                " field that you want to leave blank"
            )
        opts = [opt.replace('~<blank>', '') for opt in opts if len(opt)]
        body = getname(message.author)+" has started a poll:\n"
        body+=args.title+"\n"
        body+="\n".join((
                "%d) %s"%(num+1, opt)
                for (num, opt) in
                enumerate(opts)
            ))
        body+="\n\nReact with your vote"
        target = await self.send_message(
            message.channel,
            body
        )
        for i in range(1,len(opts)+1):
            await self.add_reaction(
                target,
                (b'%d\xe2\x83\xa3'%i).decode()#hack to create number emoji reactions
            )
        if not isinstance(message.channel, discord.PrivateChannel):
            try:
                await self.delete_message(message)
            except:
                print("Warning: Unable to delete poll source message")
            self.polls[target.id] = (message.author, set())

    @bot.subscribe('reaction_add')
    async def on_reaction_add(self, event, reaction, user):
        if reaction.message.id in self.polls:
            creator, reactors = self.polls[reaction.message.id]
            if user.id not in reactors:
                await self.send_message(
                    creator,
                    getname(user)+" has voted on your poll in "+reaction.message.channel.name
                )
                self.polls[reaction.message.id][1].add(user.id)

    return bot
