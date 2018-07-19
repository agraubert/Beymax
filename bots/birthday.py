from .core import CoreBot
from .utils import Database, get_attr
from .args import Arg, DateType
from .ow import postfix
import asyncio
import re
import datetime

def EnableBirthday(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command(
        'birthday',
        Arg(
            'birthday',
            type=DateType,
            help="Your birthday in MM/DD/YYYY format"
        )
    )
    async def cmd_birthday(self, message, args):
        """
        `$!birthday <your birthday>` : Informs me of your birthday so I
         can congratulate you when it comes. Example: `$!birthday 1/1/1970`
        """
        async with Database('birthdays.json') as birthdays:
            birthdays[message.author.id] = {
                'month': args.birthday.month,
                'day': args.birthday.day,
                'year': args.birthday.year
            }
            await self.send_message(
                message.channel,
                "Okay, I'll remember that"
            )
            if self.user.id not in birthdays:
                birthdays[self.user.id] = {
                    'month': 5,
                    'day': 6,
                    'year': 2017
                }
            birthdays.save()

    @bot.add_task(43200) #12 hours
    async def check_birthday(self):
        async with Database('birthdays.json') as birthdays:
            today = datetime.date.today()
            for uid, data in birthdays.items():
                month = data['month']
                day = data['day']
                if today.day == day and today.month == month:
                    await self.send_message(
                        self.fetch_channel('general'),
                        "@everyone Today is %s's **%s** birthday!" % (
                            get_attr(self.get_user(uid), 'mention', 'Someone'),
                            postfix(str(today.year - data['year']))
                        )
                    )

    return bot
