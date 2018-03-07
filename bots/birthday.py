from .core import CoreBot
from .utils import Database, get_attr
import asyncio
import re
import datetime

def EnableBirthday(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command('!birthday')
    async def cmd_birthday(self, message, content):
        """
        `!birthday <your birthday>` : Informs me of your birthday so I
         can congratulate you when it comes. Example: `!birthday 1/1/1970`
        """
        if len(content) < 2 or not re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', content[1]):
            await self.send_message(
                message.channel,
                "Please tell me your birthday in MM/DD/YYYY format. For"
                " example: `!birthday 1/1/1970`"
            )
        else:
            result = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', content[1])
            async with Database('birthdays.json') as birthdays:
                birthdays[message.author.id] = {
                    'month': int(result.group(1)),
                    'day': int(result.group(2)),
                    'year': int(result.group(3))
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
                        "@everyone Today is %s's birthday!"
                        " They turn %d!" % (
                            get_attr(self.get_user(uid), 'mention', 'Someone'),
                            today.year - data['year']
                        )
                    )

    return bot
