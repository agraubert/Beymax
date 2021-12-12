from ..core import CommandSuite
from ..utils import getname, keycap_emoji, DBView
from ..args import Arg
import discord
import asyncio

Polls = CommandSuite('Polls')

emoji_lookup = {
    keycap_emoji(i+1): i
    for i in range(10)
}

@Polls.add_command(
    'poll',
    Arg('title', help="Poll Title"),
    Arg("options", nargs='+', help="Poll options"),
    delimiter='|'
)
async def cmd_poll(self, message, title, options):
    """
    `$!poll <poll title> | [Option 1] | [Option 2] | [etc...]` : Creates a poll
    Example: `$!poll Is $NAME cool? | Yes | Definitely`
    """
    #The argparse API is killing the blank handling, but I think that's okay
    opts = [
        (opt.rstrip() if '~<blank>' not in opt else opt)
        for opt in options
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
    if len(opts) > 10:
        return await self.send_message(
            message.channel,
            "Currently this command only supports polls of up to 10 options."
        )
    header = (
        "{author} has started a poll:\n"
        "{title}"
    ).format(
        author=getname(message.author),
        title=title,
    )
    polldata = {
        'header': header,
        'votes': {
            opt: 0
            for opt in opts
        },
        'options': opts,
        'participated': [],
    }
    target = await self.send_message(
        message.channel,
        format_poll(polldata),
        skip_debounce=True
    )
    for i in range(1,len(opts)+1):
        await target.add_reaction(
            keycap_emoji(i)
        )
    if not isinstance(message.channel, discord.abc.PrivateChannel):
        try:
            await message.delete()
        except:
            print("Warning: Unable to delete poll source message")
    async with DBView('polls') as db:
        polldata['message'] = target.id
        polldata['channel'] = target.channel.id
        polldata['author'] = message.author.id
        db['polls'][target.id] = polldata

def format_poll(polldata, disconnected=False):
    options="\n".join(
        "{num}: {opt}{votes}".format(
            num=keycap_emoji(num+1),
            opt=opt,
            votes='' if disconnected or polldata['votes'][opt] == 0 else ' ({} vote{})'.format(
                polldata['votes'][opt],
                's' if polldata['votes'][opt] != 1 else ''
            )
        )
        for num, opt in enumerate(polldata['options'])
    )
    return (
        "{header}\n\n"
        "{options}\n\n"
        "React with your vote!"
    ).format(
        header=polldata['header'],
        options=options,
    )

@Polls.subscribe('raw_reaction_add')
@Polls.subscribe('raw_reaction_remove')
async def on_poll_react(self, event, payload):
    emoji = payload.emoji
    polls = DBView.readonly_view('polls', polls={})['polls']
    if emoji.is_unicode_emoji() and payload.message_id in polls:
        data = polls[payload.message_id]
        channel = self.get_channel(data['channel'])
        author = self.get_user(data['author'])
        message = await channel.fetch_message(data['message'])
        user = self.get_user(payload.user_id)
        for reaction in message.reactions:
            if reaction.emoji == payload.emoji.name:
                await update_poll(self, event, author, message, reaction, user)



async def update_poll(self, event, author, message, reaction, user):
    async with DBView('polls') as db:
        if reaction.message.id in db['polls'] and (not reaction.custom_emoji) and reaction.emoji in emoji_lookup:
            opt_index = emoji_lookup[reaction.emoji]
            db['polls'][reaction.message.id]['votes'][db['polls'][reaction.message.id]['options'][opt_index]] = reaction.count - 1 # Beymax
            data = db['polls'][reaction.message.id]
            await message.edit(
                content=format_poll(data)
            )
            if user.id not in data['participated']:
                await self.send_message(
                    author,
                    getname(user)+" has voted on your poll in "+reaction.message.channel.name
                )
                db['polls'][reaction.message.id]['participated'].append(user.id)
