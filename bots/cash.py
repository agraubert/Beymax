from .core import CoreBot
from .utils import Database, get_attr
from .args import Arg, DateType, DollarType
from argparse import ArgumentTypeError
import asyncio
import time
import datetime

def ShorthandType(arg):
    if len(arg.split()) > 1:
        raise ArgumentTypeError('Cannot contain spaces')
    return arg

# cash : {project : {goal, current, title, contributions, notified, end, account}}
def EnableCash(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command(
        '_payment',
        Arg('project', help="Project shorthand name"),
        Arg('user', help="Username or ID (use 0 for anonymous)"),
        Arg('amount', type=DollarType, help="Donation amount")
    )
    async def cmd_payment(self, message, args):
        """
        `$!_payment <project> <username or ID> $<amount>` : Records a user's payment on a project.
        Use `0` as the user ID for anonymous payments.
        Example: `$!_payment bots $ID $5`
        """
        # cash : {project : {goal, current, title, contributions, notified, end, account}}
        async with Database('cash.json') as cash:
            if args.project not in cash:
                await self.send_message(
                    message.channel,
                    'Project %s not found. Current projects: %s' % (
                        args.project,
                        ' '.join('"%s"' % k for k in cash)
                    )
                )
            else:
                project = args.project
                uid = args.user
                amount = args.amount
                cash[project]['current'] += amount
                cash[project]['contributions'].append(
                    {
                        'time':time.time(),
                        'user': uid,
                        'amount': amount
                    }
                )
                await self.send_message(
                    self.fetch_channel('general'),
                    '@here %s has generously donated $%0.2f towards %s, which puts us'
                    ' at %.0f%% of the $%d goal.\n'
                    'There is $%0.2f left to raise by %d/%d/%d\n'
                    'If you would like to donate, '
                    'venmo `%s` and mention `%s` in the payment' % (
                        get_attr(self.get_user(uid), 'mention', 'Someone'),
                        amount,
                        cash[project]['title'],
                        100*(cash[project]['current']/cash[project]['goal']),
                        cash[project]['goal'],
                        cash[project]['goal']-cash[project]['current'],
                        cash[project]['end']['month'],
                        cash[project]['end']['day'],
                        cash[project]['end']['year'],
                        cash[project]['account'],
                        project
                    )
                )
                cash.save()

    @bot.add_command(
        '_project',
        Arg("project", type=ShorthandType, help="Project name (one word only)"),
        Arg("description", help="Project description"),
        Arg("end", type=DateType, help="Project end date (MM/DD/YYYY)"),
        Arg('amount', type=DollarType, help="Project goal amount"),
        Arg('account', help="Your Venmo username"),
        delimiter='|'
    )
    async def cmd_project(self, message, args):
        """
        `$!_project <Full project name> | <One word short name> | <End date MM/DD/YYYY> | $<goal amount> | <Venmo username>`
        Starts a new fundraising project.
        Example: `$!_project server costs for $NAME | bots 01/02/2003 | $5 | @user-name`
        """
        #!_project full name | short name | end MM/DD/YY | $goal | venmo
        async with Database('cash.json') as cash:
            print(args)
            full = args.description.strip()
            short = args.project.strip()
            end = args.end
            goal = args.amount
            account = args.account.strip()
            if short in cash:
                await self.send_message(
                    message.channel,
                    "A project with that short name already exists. (Short name"
                    " must be unique)"
                )
                return
            # cash : {project : {goal, current, title, contributions, notified, end, account}}
            cash[short] = {
                'goal': goal,
                'current': 0,
                'title': full,
                'contributions': [],
                'notified': time.time(),
                'end': {
                    'year': end.year,
                    'month': end.month,
                    'day': end.day
                },
                'account': account
            }
            await self.send_message(
                self.fetch_channel('general'),
                '%s has started a new funding project:\n'
                'Raise $%d by %s for %s\n'
                'If you would like to donate, venmo `%s` and mention `%s`'
                ' in the payment\n'
                'Remember, all projects are pay-what-you-want' % (
                    message.author.mention,
                    goal,
                    end.strftime('%m/%d/%Y'),
                    full,
                    account,
                    short
                )
            )
            await self.send_message(
                message.author,
                "You have created the funding project `%s`. Currently, "
                "you must manually notify me when you get paid. The command"
                " for this is `$!_payment`.\nFor example, if I paid you $10"
                ", you would use `$!_payment %s $ID $10` \n(that number is my user id)."
                " To get user IDs, you must be in development mode, then"
                " right click on a user and select 'Copy ID'.\n"
                "Use `0` as the user ID to record an anonymous payment" % (
                    short,
                    short,
                )
            )
            cash.save()

    @bot.add_command('_project:end', Arg('project', help="Project shorthand name"))
    async def cmd_end_project(self, message, args):
        """
        `$!_project:end <project short name>` : Ends fundraising for a project.
        Example: `$!project:end bots`
        """
        async with Database('cash.json') as cash:
            project = args.project
            if project not in cash:
                await self.send_message(
                    message.channel,
                    "No funding project with that name"
                )
            else:
                await self.send_message(
                    self.fetch_channel('general'),
                    "The funding project for %s has ended at %.0f%% of its $%d goal" % (
                        cash[project]['title'],
                        100*(cash[project]['current']/cash[project]['goal']),
                        cash[project]['goal']
                    )
                    + (
                        '\nDonations:\n' +
                        '\n'.join(
                            '%s: $%d' % (
                                get_attr(self.get_user(contrib['user']), 'mention', 'Anonymous'),
                                contrib['amount']
                            )
                            for contrib in sorted(
                                cash[project]['contributions'],
                                key=lambda x:x['amount'],
                                reverse=True
                            )
                        )
                    )
                    + (
                        "\nNice work, and thanks to all the donors!" if
                        cash[project]['current']>=cash[project]['goal']
                        else ""
                    )
                )
                async with Database('old_cash.json') as old_cash:
                    old_cash[project] = cash[project]
                    old_cash.save()
                del cash[project]
                cash.save()

    @bot.add_task(604800) # 1 week
    async def notify_projects(self):
        async with Database('cash.json') as cash:
            today = datetime.date.today()
            for project in [k for k in cash]:
                data = cash[project]
                end = data['end']
                ended = end['year'] < today.year
                ended |= end['year'] == today.year and end['month'] < today.month
                ended |= end['year'] == today.year and end['month'] == today.month and end['day'] < today.day
                if ended:
                    await self.send_message(
                        self.fetch_channel('general'),
                        "The funding project for %s has ended at %.0f%% of its $%d goal" % (
                            cash[project]['title'],
                            100*(cash[project]['current']/cash[project]['goal']),
                            cash[project]['goal']
                        )
                        + (
                            '\nDonations:\n' +
                            '\n'.join(
                                '%s: $%d' % (
                                    get_attr(self.get_user(contrib['user']), 'mention', 'Anonymous'),
                                    contrib['amount']
                                )
                                for contrib in sorted(
                                    cash[project]['contributions'],
                                    key=lambda x:x['amount'],
                                    reverse=True
                                )
                            )
                        )
                        + (
                            "\nNice work, and thanks to all the donors!" if
                            cash[project]['current']>=cash[project]['goal']
                            else ""
                        )
                    )
                    async with Database('old_cash.json') as old_cash:
                        old_cash[project] = cash[project]
                        old_cash.save()
                    del cash[project]
                elif time.time() - data['notified'] > 2628001: #~1 month
                    await self.send_message(
                        self.fetch_channel('general'),
                        "Funds are still being collected for %s\n"
                        "Current progress: $%0.2f/$%d (%.0f%%)\n"
                        "Project ends: %d/%d/%d\n"
                        'If you would like to donate, venmo `%s` and mention `%s`'
                        ' in the payment' % (
                            data['title'],
                            data['current'],
                            data['goal'],
                            100*(data['current']/data['goal']),
                            end['month'],
                            end['day'],
                            end['year'],
                            data['account'],
                            project
                        )
                    )
                    cash[project]['notified'] = time.time()
            cash.save()

    return bot
