from ..core import CommandSuite
from ..utils import DBView, keycap_emoji, getname
from ..args import Arg
import discord
from emoji import demojize
import re

emoji_opt = re.compile(r':keycap_(\d{1,2}):')
num_opt = re.compile(r'(\d{1,2})')

Gamba = CommandSuite('Gamba')

emoji_lookup = {
    keycap_emoji(i): i
    for i in range(1, 11)
}

def OptType(arg):
    """
    Argument Type to handle arbitrary poll options (emoji, numbers, text)
    """
    match = emoji_opt.match(demojize(arg))
    if match is not None:
        return int(match.group(1))
    match = num_opt.match(arg)
    if match is not None:
        return int(match.group(1))
    return arg

@Gamba.add_command(
    'gamba',
    Arg('title', help="Poll Title"),
    Arg("options", nargs='+', help="Poll options"),
    delimiter='|'
)
async def cmd_gamba(self, message, title, options):
    """
    `!gamba <Poll title> | [Option 1] | [Option 2] | [etc...]` : Creates a new gamba poll
    Example: `$!gamba Is $NAME cool? | Yes | Definitely`
    """
    async with DBView('gamba') as db:
        # Do all work within db context to prevent a race between gamba commands
        if message.channel.id in db['gamba']:
            try:
                existing = await message.channel.fetch_message(db['gamba'][message.channel.id]['message'])
                await message.channel.send(
                    "There is already an active gamba poll in this channel, please wait"
                    " until it is resolved",
                    reference=existing.to_reference()
                )
            except:
                await self.trace(False)
                await self.send_message(
                    message.channel,
                    "There is already an active gamba poll in this channel, please wait"
                    " until it is resolved"
                )
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
            "{author} has started a gamba poll:\n"
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
            'participated': {},
        }
        target = await self.send_message(
            message.channel,
            format_poll(polldata),
            skip_debounce=True
        )
        if not isinstance(message.channel, discord.abc.PrivateChannel):
            try:
                await message.delete()
            except:
                print("Warning: Unable to delete poll source message")
        polldata['message'] = target.id
        polldata['channel'] = target.channel.id
        polldata['author'] = message.author.id
        db['gamba'][message.channel.id] = polldata

def format_poll(polldata, disconnected=False):
    options="\n".join(
        "{num}: {opt}{votes}{winner}".format(
            num=keycap_emoji(num+1),
            opt=opt,
            votes='' if disconnected or polldata['votes'][opt] == 0 else ' ({} token{})'.format(
                polldata['votes'][opt],
                's' if polldata['votes'][opt] != 1 else ''
            ),
            winner=' **Winning option**' if 'winner' in polldata and polldata['winner']==num else ''
        )
        for num, opt in enumerate(polldata['options'])
    )
    return (
        "{header}\n\n"
        "{options}\n\n"
        "{vote}"
    ).format(
        header=polldata['header'],
        options=options,
        vote="Vote with `$!bet <amount> <option>`" if 'winner' not in polldata else '(This poll has closed)'
    )

@Gamba.add_command(
    'bet',
    Arg('amount', type=int, help="Your bet amount, in tokens"),
    Arg('option', type=OptType, nargs='?', default='', help="The option to bet on. Can be an emoji, number, or the option's text")
)
async def cmd_bet(self, message, amount, option):
    """
    `$!bet <amount> <option>` : Places a bet on a gamba poll. Option can be an emoji numeral, a number, or the option's text
    Example: `$!bet 10 7` : Places 10 tokens on option 7
    """
    async with DBView('gamba', 'players') as db:
        if message.author.id not in db['players']:
            db['players'][message.author.id] = {
                'balance':10
            }

        balance = db['players'][message.author.id]['balance']
        if message.channel.id not in db['gamba']:
            return await self.send_message(
                message.channel,
                "There are currently no gamba polls in this channel"
            )
        polldata = db['gamba'][message.channel.id]
        try:
            existing = await message.channel.fetch_message(polldata['message'])
        except:
            await self.trace(True)
            self.dispatch('gamba-reset', message.channel.id)
            return await self.send_message(
                message.channel,
                "I've lost track of the gamba poll in this channel. "
                "It will be aborted and all bets refunded"
            )
        if message.author.id in polldata['participated']:
            return await message.channel.send(
                "You have already partipated in this poll with a bet of {} tokens on {}".format(
                    polldata['participated'][message.author.id]['amount'],
                    keycap_emoji(polldata['participated'][message.author.id]['option'] + 1)
                ),
                reference=existing.to_reference()
            )
        if isinstance(option, str):
            # match option text
            try:
                option = [opt.strip() for opt in polldata['options']].index(option.strip())
            except ValueError:
                return await message.channel.send(
                    "`{}` didn't match any options in the current poll".format(
                        option
                    ),
                    reference=existing.to_reference()
                )
        else:
            # Option is int
            option -= 1
        if option < 0 or option >= len(polldata['options']):
            return await message.channel.send(
                "There is no option {} in the current poll".format(option + 1),
                reference=existing.to_reference()
            )
        if amount > balance:
            return await self.send_message(
                message.channel,
                "You do not have enough tokens to place that bet"
            )
        polldata['participated'][message.author.id] = {
            'amount': amount,
            'option': option,
        }
        polldata['votes'][polldata['options'][option]] += amount
        db['players'][message.author.id]['balance'] -= amount
        db['gamba'][message.channel.id] = polldata
        await message.channel.send(
            "{}, your bet has been placed on option {}.".format(
                getname(message.author),
                keycap_emoji(option + 1)
            ),
            reference=existing.to_reference()
        )
        await existing.edit(
            content=format_poll(polldata)
        )

@Gamba.add_command('resolve', Arg('option', type=OptType, nargs='?', default='', help="The option to bet on. Can be an emoji, number, or the option's text. Defaults to the option with the most votes"))
async def cmd_resolve(self, message, option):
    """
    `$!resolve` : Resolves the open gamba poll in this channel.
    You must either be the poll's creator, or have administrator permissions in my configuration.
    """
    async with DBView('gamba', 'players') as db:
        if message.author.id not in db['players']:
            db['players'][message.author.id] = {
                'balance':10
            }

        balance = db['players'][message.author.id]['balance']
        if message.channel.id not in db['gamba']:
            return await self.send_message(
                message.channel,
                "There are currently no gamba polls in this channel"
            )
        polldata = db['gamba'][message.channel.id]
        try:
            existing = await message.channel.fetch_message(polldata['message'])
        except:
            await self.trace(True)
            self.dispatch('gamba-reset', message.channel.id)
            return await self.send_message(
                message.channel,
                "I've lost track of the gamba poll in this channel. "
                "It will be aborted and all bets refunded"
            )
        if not (message.author.id == polldata['author'] or self.permissions.query_underscore(message.author)[0]):
            return await message.channel.send(
                "You do not have the authority to resolve this gamba poll",
                reference=existing.to_reference()
            )
        if isinstance(option, str):
            # match option text
            try:
                blank = len(option.strip()) == 0
                option = [opt.strip() for opt in polldata['options']].index(option.strip())
                if blank:
                    return await message.channel.send(
                        "A blank option value exists in this poll, so I cannot"
                        " disambiguate between resolving the poll based on most"
                        " bets, or resolving the poll with an explicit correct option."
                        "\nPlease use `$!resolve {}` to resolve the poll based on the blank text option."
                        "\nOr `$!resolve {}` to resolve the poll based on the current winning option".format(
                            keycap_emoji(option+1),
                            keycap_emoji(1+polldata['votes'].index(max(polldata['votes'])))
                        ),
                        reference=message.channel.to_reference()
                    )
            except ValueError:
                # Index of current leading option
                maxv = max(polldata['votes'].values())
                options = [opt for opt, votes in polldata['votes'].items() if votes == maxv]
                if len(options) != 1:
                    return await message.channel.send(
                        "There are multiple options with an equal amount of tokens."
                        " Please manually specify the winning option",
                        reference=existing.to_reference()
                    )
                option = polldata['options'].index(options[0])
        else:
            # Option is int
            option -= 1
        # 1) Compute total pot to distribute
        pot = sum(polldata['votes'].values()) - polldata['votes'][polldata['options'][option]]
        # 2) Compute payouts
        # Winners are paid their bet + a portion of the pot based on how much they contributed to the winning bet
        maxp = 0
        maxu = None
        for uid, bet in polldata['participated'].items():
            if bet['option'] == option:
                payout = round(polldata['participated'][uid]['amount'] * (1 + pot / polldata['votes'][polldata['options'][option]]))
                if payout > maxp:
                    maxp = payout
                    maxu = uid
                if uid not in db['players']:
                    db['players'][uid] = {'balance': 10}
                db['players'][uid]['balance'] += payout
        # 3) Announce closure
        await message.channel.send(
            "This gamba poll has been resolved. " + (
                "Nobody bet on the winning option, {}.".format(keycap_emoji(option + 1))
                if maxu is None
                else (
                    "Anyone who bet on {} will be paid"
                    " their original bet plus a share of the {} token pot proportional to"
                    " their bet. Today's big winner is {}, taking home {} tokens"
                ).format(
                    keycap_emoji(option + 1),
                    pot,
                    self.get_user(maxu).mention,
                    maxp
                )
            ),
            reference=existing.to_reference()
        )
        polldata['winner'] = option
        await existing.edit(
            content=format_poll(polldata)
        )
        # 4) cleanup
        del db['gamba'][message.channel.id]

@Gamba.subscribe('gamba-reset')
async def reset(self, _, channelid):
    async with DBView('gamba', 'players') as db:
        if channelid in db['gamba']:
            polldata = db['gamba'][channelid]
            for uid, bet in polldata['participated'].items():
                if uid in db['players']:
                    db['players'][uid]['balance'] += bet['amount']
            del db['gamba'][channelid]
