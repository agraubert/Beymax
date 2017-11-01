from .utils import load_db, save_db, getname
import discord
import asyncio
import time


class CoreBot(discord.Client):
    commands = {} # !cmd -> function wrapper. Functions take (self, message, content)
    users = {} # id/fullname -> {id, fullname, mention, name}
    tasks = [] # [interval(s), function] functions take (self)
    special = [] # [callable, function] callable takes (self, message) and returns True if function should be run. Func takes (self, message, content)

    def add_command(self, *cmds):
        if not len(cmds):
            raise ValueError("Must provide at least one command")
        def wrapper(func):
            for cmd in cmds:
                self.commands[cmd] = func
            return func
        return wrapper

    def add_task(self, interval):
        def wrapper(func):
            self.tasks.append((interval, func))
            return func
        return wrapper

    def add_special(self, check):
        def wrapper(func):
            self.special.append(check, func)
            return func
        return wrapper

    def EnableAll(self, *bots):
        for bot in bots:
            if callable(bot):
                self = bot(self)
            else:
                raise TypeError("Bot is not callable")
        return self

    async def on_ready(self):
        self.users = load_db('users.json')
        self._general = discord.utils.get(
            self.get_all_channels(),
            name='general',
            type=discord.ChannelType.text
        )
        self.general = self._general
        self._bug_channel = self._general #Change which channels these use
        self.bug_channel = self._general #Change which channels these use
        self.dev_channel = self._general #Change which channels these use
        self.update_times = [0] * len(self.tasks) # set all tasks to update at next trigger

    async def close(self):
        save_db(self.users, 'users.json')
        await super().close()

    async def on_message(self, message):
        if message.author == self.user:
            return
        struct = {
            'id': message.author.id,
            'fullname': str(message.author),
            'mention': message.author.mention,
            'name': getname(message.author)
        }
        self.users[str(message.author)] = struct
        self.users[message.author.id] = struct
        try:
            content = message.content.strip().split()
            content[0] = content[0].lower()
        except:
            return
        if content[0] in self.commands:
            print("Command in channel", message.channel, "from", message.author, ":", content)
            await self.commands[content[0]](self, message, content)
        else:
            for check, func in self.special:
                if check(self, message):
                    await func(self, message, content)
        current = time.time()
        for i, (interval, task) in enumerate(self.tasks):
            last = self.update_times[i]
            if current - last > interval:
                await task(self)
                self.update_times[i] = current

def EnableUtils(bot): #prolly move to it's own bot
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command('!output-dev')
    async def cmd_dev(self, message, content):
        self.general = self.dev_channel
        self.bug_channel = self.dev_channel
        await self.send_message(
            self.dev_channel,
            "Development mode enabled. All messages will be sent to testing grounds"
        )

    @bot.add_command('!output-prod')
    async def cmd_prod(self, message, content):
        self.general = self._general
        self.bug_channel = self._bug_channel
        await self.send_message(
            self.dev_channel,
            "Production mode enabled. All messages will be sent to general"
        )

    @bot.add_command('!_announce')
    async def cmd_announce(self, message, content):
        await self.send_message(
            self.general,
            message.content.strip().replace('!_announce', '')
        )

    return bot
