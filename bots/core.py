from .utils import load_db, save_db, getname, validate_permissions
import discord
import asyncio
import time
import os
import yaml
import sys


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
            self.special.append((check, func))
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
        print("Commands:", [cmd for cmd in self.commands])
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
        self.primary_server = self._general.server
        self.update_times = [0] * len(self.tasks) # set all tasks to update at next trigger
        self.permissions = None
        if os.path.exists('permissions.yml'):
            with open('permissions.yml') as reader:
                self.permissions = yaml.load(reader)
                #get user by name: server.get_member_named
                #get user by id: server.get_member
                #iterate over server.role_hierarchy until the command is found (default enabled)
                #validate the permissions object
                if not isintance(self.permissions, dict):
                    sys.exit("permissions.yml must be a dictionary")
                if 'defaults' not in self.permissions:
                    sys.exit("permissions.yml must define defaults")
                validate_permissions(self.permissions, True)
                if 'permissions' in self.permissions:
                    if not isinstance(self.permissions['permissions'], list):
                        sys.exit("permissions key of permissions.yml must be a list")
                for target in self.permissions['permissions']:
                    validate_permissions(target)
                self.permissions['roles'] = {
                    discord.utils.find(
                        lambda role: role.name == obj['role'] or role.id == obj['role']
                        self.primary_server.roles
                    ).id:obj for obj in self.permissions['permissions']
                    if 'role' in obj
                }
                self.permissions['users'] = {
                    getid(user):obj for obj in self.permissions['permissions']
                    if 'users' in obj
                    for user in obj['users']
                }


    async def close(self):
        save_db(self.users, 'users.json')
        await super().close()

    def getid(self, username):
        if username in self.users:
            return self.users[username]['id']
        result = self.primary_server.get_member_named(username)
        if result is not None:
            return result.id
        result = self.primary_server.get_member(username)
        if result is not None:
            return result.id
        sys.exit("Unable to locate member '%s'. Must use a user ID, username, or username#discriminator" % username)

    def build_permissions_chain(user):
        chain = []
        if user.id in self.permissions['users']:
            chain.append(self.permissions['users'][user.id])
        elif hasattr(user, 'roles'):
            user_roles = set(user.roles)
            for role in self.primary_server.role_hierarchy:
                if role in user_roles:
                    chain.append(role)
        return [item for item in chain] + self.permissions['defaults']

    def has_underscore_permissions(user, chain=None):
        if chain is None:
            chain = self.build_permissions_chain(user)
        for obj in chain:
            if 'underscore' in obj:
                return obj['underscore']

    def check_permissions_chain(cmd, user, chain=None):
        if chain is None:
            chain = self.build_permissions_chain(user)
        for obj in chain:
            if 'allow' in obj and cmd in obj['allow']:
                return True, obj
            elif 'deny' in obj and cmd in obj['deny']:
                return False, obj
            elif cmd.startswith('_') and 'underscore' in obj:
                return obj['underscore'], obj

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
            if self.check_permissions_chain(cmd[1:], message.author)[0]:
                print("Command in channel", message.channel, "from", message.author, ":", content)
                await self.commands[content[0]](self, message, content)
            else:
                print(message.author, "permissions denied to use command", content[0], "in", message.channel)
                await self.send_message(
                    message.channel,
                    "You do not have permissions to use this command\n" +
                    (("If you have permissions granted to you by a role, "
                     "I cannot check those in private messages\n")
                     if isinstance(message.channel, discord.PrivateChannel)
                     else ""
                    ) +
                    "To check your permissions, use the `!perms` command"
                )
        else:
            for check, func in self.special:
                if check(self, message):
                    print("Running special", func.__qualname__)
                    await func(self, message, content)
                    break
        current = time.time()
        for i, (interval, task) in enumerate(self.tasks):
            last = self.update_times[i]
            if current - last > interval:
                print("Running task", task.__qualname__)
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

    @bot.add_command('!perms')
    async def cmd_perms(self, message, content):
        chain = self.build_permissions_chain(message.author)
        cmds = []
        for command in self.commands:
            (allow, rule) = self.check_permissions_chain(command[1:], message.author, chain)
            if allow:
                cmds.append((
                    command,
                    discord.utils.find(
                        lambda role: role.name ==rule['role'] or role.id == rule['role']
                        self.primary_server.roles
                    ) if 'role' in rule else None
                ))
        body = ["Here are the commands you have permissions to use:"]
        for cmd, rule in cmds:
            tmp = '`%s` : %s' % (
                cmd,
                'Granted by role ' + rule.name if rule is not None else
                'Granted directly to you'
            )
            body.append(''+tmp)
        if isinstance(message.channel, discord.PrivateChannel):
            body.append(
                "You may have additional permissions granted to you by a role"
                " but I cannot check those within a private chat"
            )
        await self.send_message(
            message.channel,
            '\n'.join(body)
        )

    return bot
