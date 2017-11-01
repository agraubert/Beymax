from .core import CoreBot
from .utils import load_db, save_db
import re
import datetime

def EnableBirthday(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command('!birthday')
    async def cmd_birthday(self, message, content):
        if len(content) < 2 or not re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', content[1]):
            await self.send_message(
                message.channel,
                "Please tell me your birthday in MM/DD/YYYY format. For"
                " example: `!birthday 1/1/1970`"
            )
        else:
            result = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', content[1])
            birthdays = load_db('birthdays.json')
            birthdays[message.author.id] = {
                'month': int(result.group(1)),
                'day': int(result.group(2)),
                'year': int(result.group(3))
            }
            await self.send_message(
                message.channel,
                "Okay, I'll remember that"
            )
            save_db(birthdays, 'birthdays.json')

    @bot.add_task(43200) #12 hours
    async def check_birthday(self):
        birthdays = load_db('birthdays.json')
        today = datetime.date.today()
        for uid, data in birthdays.items():
            month = data['month']
            day = data['day']
            if today.day == day and today.month == month:
                await self.send_message(
                    self.general,
                    "@everyone congratulate %s, for today is their birthday!"
                    " They are %d!" % (
                        self.users[uid]['mention'] if uid in self.users else "someone",
                        today.year - data['year']
                    )
                )

    return bot
