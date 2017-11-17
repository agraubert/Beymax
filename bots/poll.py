from .core import CoreBot
from .utils import getname
import discord
import asyncio

def EnablePolls(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.polls = {}

    @bot.add_command('!poll')
    async def cmd_poll(self, message, content):
        """
        `!poll <poll title> | [Option 1] | [Option 2] | [etc...]` : Creates a poll
        Example: `!poll Is Beymax cool? | Yes | Definitely`
        """
        opts = ' '.join(content[1:]).split('|')
        title = opts.pop(0)
        body = getname(message.author)+" has started a poll:\n"
        body+=title+"\n"
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
            await self.delete_message(message)
            self.polls[target.id] = (message.author, set())

    if 'on_reaction_add' in dir(bot):
        bot._poll_on_react = bot.on_reaction_add
    else:
        bot._poll_on_react = None

    async def on_reaction_add(reaction, user):
        if bot._poll_on_react is not None:
            await bot._poll_on_react(reaction, user)
        if reaction.message.id in bot.polls:
            creator, reactors = bot.polls[reaction.message.id]
            if user.id not in reactors:
                await bot.send_message(
                    creator,
                    getname(user)+" has voted on your poll in "+reaction.message.channel.name
                )
                bot.polls[reaction.message.id][1].add(user.id)
    bot.on_reaction_add = on_reaction_add

    return bot
