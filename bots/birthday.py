from .core import CoreBot
from .utils import DBView, get_attr
from .args import Arg, DateType
from .ow import postfix
import asyncio
import re
import datetime
import os
import json

def EnableBirthday(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.subscribe('before:ready')
    async def cleanup(self, _):
        if not os.path.exists('birthdays.json'):
            return
        with open('birthdays.json') as r:
            birthdays = json.load(r)
        async with DBView('birthdays', birthdays=birthdays) as db:
            for uid, data in birthdays.items():
                db['birthdays'][uid] = data
                if 'notified' not in db['birthdays'][uid]:
                    db['birthdays'][uid]['notified'] = 0
        os.remove('birthdays.json')


    @bot.add_command(
        'birthday',
        Arg(
            'birthday',
            type=DateType,
            help="Your birthday in MM/DD/YYYY format"
        )
    )
    async def cmd_birthday(self, message, birthday):
        """
        `$!birthday <your birthday>` : Informs me of your birthday so I
         can congratulate you when it comes. Example: `$!birthday 1/1/1970`
        """
        async with DBView('birthdays', birthdays={}) as db:
            db['birthdays'][message.author.id] = {
                'month': birthday.month,
                'day': birthday.day,
                'year': birthday.year,
                'notified': 0
            }
            await self.send_message(
                message.channel,
                "Okay, I'll remember that"
            )
            if self.user.id not in db['birthdays']:
                db['birthdays'][self.user.id] = {
                    'month': 5,
                    'day': 6,
                    'year': 2017,
                    'notified': 0
                }

    @bot.add_task(43200) #12 hours
    async def check_birthday(self):
        async with DBView('birthdays') as db:
            today = datetime.date.today()
            for uid, data in db['birthdays'].items():
                month = data['month']
                day = data['day']
                if today.day == day and today.month == month and today.year > data['notified']:
                    await self.send_message(
                        self.fetch_channel('general'),
                        "@here Today is %s's **%s** birthday!" % (
                            get_attr(self.get_user(uid), 'mention', 'Someone'),
                            postfix(str(today.year - data['year']))
                        )
                    )
                    db['birthdays'][uid]['notified'] = today.year

    return bot
