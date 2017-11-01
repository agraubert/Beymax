from .core import CoreBot
from .utils import getname

def EnablePolls(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command('!poll')
    async def cmd_poll(self, message, content):
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
        await self.delete_message(message)

    return bot
