from .core import CoreBot
from .utils import load_db, save_db
import asyncio
import time
import datetime
import re

date_pattern = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4})')

# cash : {project : {goal, current, title, contributions, notified, end, account}}
def EnableCash(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command('!_payment')
    async def cmd_payment(self, message, content):
        if len(content) != 4:
            await self.send_message(
                message.channel,
                'Syntax is: `!_payment project uid $amount`'
            )
        elif not content[3].startswith('$'):
            await self.send_message(
                message.channel,
                'Syntax is: `!_payment project uid $amount`'
            )
        else:
            # cash : {project : {goal, current, title, contributions, notified, end, account}}
            cash = load_db('cash.json')
            if content[1] not in cash:
                await self.send_message(
                    message.channel,
                    'Project %s not found. Current projects: %s' % (
                        content[1],
                        ' '.join('"%s"' % k for k in cash)
                    )
                )
            else:
                project = content[1]
                uid = content[2]
                try:
                    amount = float(content[3][1:])
                except ValueError:
                    amount = int(contents[3][1:])
                cash[project]['current'] += amount
                cash[project]['contributions'].append(
                    {
                        'time':time.time(),
                        'user': uid,
                        'amount': amount
                    }
                )
                await self.send_message(
                    self.general,
                    '@everyone %s has generously donated $%0.2f towards %s, which puts us'
                    ' at %.0f%% of the $%d goal.\n'
                    'There is $%0.2f left to raise by %d/%d/%d\n'
                    'If you would like to donate, '
                    'venmo `%s` and mention `%s` in the payment' % (
                        self.users[uid]['mention'] if uid in self.users else 'someone',
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
                save_db(cash, 'cash.json')

    @bot.add_command('!_project')
    async def cmd_project(self, message, content):
        args = message.content.replace('!_project', '').split('|')
        #!_project full name | short name | end MM/DD/YY | $goal | venmo
        if len(args) != 5:
            await self.send_message(
                message.channel,
                "Syntax is: `!_project full name | short name | end date "
                "MM/DD/YYYY | $goal | venmo account`"
            )
        else:
            cash = load_db('cash.json')
            print(args)
            full = args[0].strip()
            short = args[1].strip()
            end = args[2].strip()
            goal = args[3].strip()
            account = args[4].strip()
            if len(short.split())>1:
                await self.send_message(
                    message.channel,
                    "Syntax is: `!_project full name | short name | end date "
                    "MM/DD/YYYY | $goal | venmo account`. "
                    "There can be no spaces in the short name"
                )
            elif not date_pattern.match(end):
                await self.send_message(
                    message.channel,
                    "Syntax is: `!_project full name | short name | end date "
                    "MM/DD/YYYY | $goal | venmo account`. "
                    "End date must be in MM/DD/YYYY format"
                )
            elif not goal.startswith('$'):
                await self.send_message(
                    message.channel,
                    "Syntax is: `!_project full name | short name | end date "
                    "MM/DD/YYYY | $goal | venmo account`. "
                    "Goal must be an integer and start with '$'"
                )
            elif short in cash:
                await self.send_message(
                    message.channel,
                    "A project with that short name already exists. (Short name"
                    " must be unique)"
                )
            else:
                try:
                    goal = int(goal[1:])
                    end = date_pattern.match(end)
                    # cash : {project : {goal, current, title, contributions, notified, end, account}}
                    cash[short] = {
                        'goal': goal,
                        'current': 0,
                        'title': full,
                        'contributions': [],
                        'notified': time.time(),
                        'end': {
                            'year': int(end.group(3)),
                            'month': int(end.group(1)),
                            'day': int(end.group(2))
                        },
                        'account': account
                    }
                    await self.send_message(
                        self.general,
                        '%s has started a new funding project:\n'
                        'Raise $%d by %s for %s\n'
                        'If you would like to donate, venmo `%s` and mention `%s`'
                        ' in the payment\n'
                        'Remember, all projects are pay-what-you-want' % (
                            message.author.mention,
                            goal,
                            args[2],
                            full,
                            account,
                            short
                        )
                    )
                    await self.send_message(
                        message.author,
                        "You have created the funding project `%s`. Currently, "
                        "you must manually notify me when you get paid. The command"
                        " for this is `!_payment`.\nFor example, if I paid you $10"
                        ", you would use `!_payment %s %s $10` \n(that number is my user id)."
                        " To get user IDs, you must be in development mode, then"
                        " right click on a user and select 'Copy ID'.\n"
                        "Use `0` as the user ID to record an anonymous payment" % (
                            short,
                            short,
                            self.user.id,
                        )
                    )
                    save_db(cash, 'cash.json')
                except:
                    await self.send_message(
                        message.channel,
                        "Syntax is: `!_project full name | short name | end date "
                        "MM/DD/YY | $goal | venmo account`. "
                        "Goal must be an integer and start with '$'"
                    )

    @bot.add_command('!_project:end')
    async def cmd_end_project(self, message, content):
        if len(content) != 2:
            await self.send_message(
                message.channel,
                "Syntax is: `!_project:end short_name`"
            )
        else:
            cash = load_db('cash.json')
            project = content[1]
            if project not in cash:
                await self.send_message(
                    message.channel,
                    "No funding project with that name"
                )
            else:
                await self.send_message(
                    self.general,
                    "The funding project for %s has ended at %.0f%% of its $%d goal" % (
                        cash[project]['title'],
                        100*(cash[project]['current']/cash[project]['goal']),
                        cash[project]['goal']
                    )
                    + (
                        "\nNice work, and thanks to all the donors!" if
                        cash[project]['current']>=cash[project]['goal']
                        else ""
                    )
                )
                old_cash = load_db('old_cash.json')
                old_cash[project] = cash[project]
                save_db(old_cash, 'old_cash.json')
                del cash[project]
                save_db(cash, 'cash.json')

    @bot.add_task(604800) # 1 week
    async def notify_projects(self):
        cash = load_db('cash.json')
        today = datetime.date.today()
        for project in [k for k in cash]:
            data = cash[project]
            end = data['end']
            ended = end['year'] < today.year
            ended |= end['year'] == today.year and end['month'] < today.month
            ended |= end['year'] == today.year and end['month'] == today.month and end['day'] < today.day
            if ended:
                await self.send_message(
                    self.general,
                    "The funding project for %s has ended at %.0f%% of its $%d goal" % (
                        data['title'],
                        100*(data['current']/data['goal']),
                        data['goal']
                    )
                )
                old_cash = load_db('old_cash.json')
                old_cash[project] = data
                save_db(old_cash, 'old_cash.json')
                del cash[project]
            elif time.time() - data['notified'] > 2628001: #~1 month
                await self.send_message(
                    self.general,
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
        save_db(cash, 'cash.json')

    return bot
