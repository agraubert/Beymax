from .utils import load_db, save_db, getname, validate_permissions
import discord
import asyncio
import time
import os
import yaml
import sys


class CoreBot(discord.Client):
    ignored_users = set()
    commands = {} # !cmd -> function wrapper. Functions take (self, message, content)
    users = {} # id/fullname -> {id, fullname, mention, name}
    tasks = [] # [interval(s), function] functions take (self)
    special = [] # [callable, function] callable takes (self, message) and returns True if function should be run. Func takes (self, message, content)

    def add_command(self, *cmds): #decorator. Attaches the decorated function to the given command(s)
        if not len(cmds):
            raise ValueError("Must provide at least one command")
        def wrapper(func):
            for cmd in cmds:
                self.commands[cmd] = func
            return func
        return wrapper

    def add_task(self, interval): #decorator. Sets the decorated function to run on the specified interval
        def wrapper(func):
            self.tasks.append((interval, func))
            return func
        return wrapper

    def add_special(self, check): #decorator. Sets the decorated function to run whenever the check is true
        def wrapper(func):
            self.special.append((check, func))
            return func
        return wrapper

    def EnableAll(self, *bots): #convenience function to enable a bunch of subbots at once
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
        self.categories = {
            channel.name:channel for channel in self.get_all_channels()
            if channel.type == 4 # Placeholder. ChannelType.category is not in discord.py yet
        }
        self.general = self._general
        self._bug_channel = self._general #Change which channels these use
        self.bug_channel = self._general #Change which channels these use
        self.dev_channel = self._general #Change which channels these use
        self.primary_server = self._general.server
        self.update_times = [0] * len(self.tasks) # set all tasks to update at next trigger
        self.permissions = None
        self.ignored_users = set(load_db('ignores.json', []))
        if os.path.exists('permissions.yml'):
            with open('permissions.yml') as reader:
                self.permissions = yaml.load(reader)
            #get user by name: server.get_member_named
            #get user by id: server.get_member
            #iterate over server.role_hierarchy until the command is found (default enabled)
            #validate the permissions object
            if not isinstance(self.permissions, dict):
                sys.exit("permissions.yml must be a dictionary")
            if 'defaults' not in self.permissions:
                sys.exit("permissions.yml must define defaults")
            validate_permissions(self.permissions['defaults'], True)
            if 'permissions' in self.permissions:
                if not isinstance(self.permissions['permissions'], list):
                    sys.exit("permissions key of permissions.yml must be a list")
            seen_roles = set()
            for target in self.permissions['permissions']:
                validate_permissions(target)
                if 'role' in target:
                    if target['role'] in seen_roles:
                        sys.exit("Duplicate role encountered in permissions.yml")
                    seen_roles.add(target['role'])
            self.permissions['roles'] = {
                discord.utils.find(
                    lambda role: role.name == obj['role'] or role.id == obj['role'],
                    self.primary_server.roles
                ).id:obj for obj in self.permissions['permissions']
                if 'role' in obj
            }
            try:
                tmp = [
                    (self.getid(user),obj) for obj in self.permissions['permissions']
                    if 'users' in obj
                    for user in obj['users']
                ]
            except NameError as e:
                raise SystemExit("Unable to find user") from e
            self.permissions['users'] = {}
            for uid, rule in tmp:
                if uid not in self.permissions['users']:
                    self.permissions['users'][uid] = [rule]
                else:
                    self.permissions['users'][uid].append(rule)
            for uid in self.permissions['users']:
                self.permissions['users'][uid].sort(
                    key=lambda x:len(x['users'])
                )
            self.permissions['defaults']['_grant'] = 'by default'
            for user in self.permissions['users']:
                for i in range(len(self.permissions['users'][user])):
                    nUsers = len(self.permissions['users'][user][i]['users'])
                    self.permissions['users'][user][i]['_grant'] = (
                        'directly to you' if nUsers == 1 else
                        'to you and %d other people' % nUsers
                    )
            for role in self.permissions['roles']:
                self.permissions['roles'][role]['_grant'] = 'by role `%s`' % (
                    self.permissions['roles'][role]['role']
                )

    async def close(self):
        save_db(self.users, 'users.json')
        await super().close()

    async def send_message(self, destination, content, *, delim='\n', **kwargs):
        #built in chunking
        body = content.split(delim)
        tmp = []
        last_msg = None
        for line in body:
            tmp.append(line)
            msg = delim.join(tmp)
            if len(msg) > 2048 and delim=='. ':
                # If the message is > 2KB and we're trying to split by sentences,
                # try to split it up by spaces
                last_msg = await self.send_message(
                    destination,
                    msg,
                    delim=' ',
                    **kwargs
                )
            elif len(msg) > 1536 and delim=='\n':
                # if the message is > 1.5KB and we're trying to split by lines,
                # try to split by sentences
                last_msg = await self.send_message(
                    destination,
                    msg,
                    delim='. ',
                    **kwargs
                )
            elif len(msg) > 1024:
                # Otherwise, send it if the current message has reached the
                # 1KB chunking target
                last_msg = await super().send_message(
                    destination,
                    msg,
                    **kwargs
                )
                tmp = []
                await asyncio.sleep(1)
        if len(tmp):
            #send any leftovers (guaranteed <2KB)
            last_msg = await super().send_message(
                destination,
                msg
            )
        return last_msg

    def getid(self, username):
        #Get the id of a user from an unknown reference (could be their username, fullname, or id)
        if username in self.users:
            return self.users[username]['id']
        result = self.primary_server.get_member_named(username)
        if result is not None:
            return result.id
        result = self.primary_server.get_member(username)
        if result is not None:
            return result.id
        raise NameError("Unable to locate member '%s'. Must use a user ID, username, or username#discriminator" % username)

    def build_permissions_chain(self, user):
        # Assemble the chain of permissions rules for a given user
        chain = []
        if user.id in self.permissions['users']:
            chain += self.permissions['users'][user.id]
        if hasattr(user, 'roles'):
            user_roles = set(user.roles)
            for role in self.primary_server.role_hierarchy:
                if role in user_roles and role.id in self.permissions['roles']:
                    chain.append(self.permissions['roles'][role.id])
        return [item for item in chain] + [self.permissions['defaults']]

    def has_underscore_permissions(self, user, chain=None):
        # Check the permissions chain for a user to see if they can use
        # Administrative (underscore) commands
        if chain is None:
            #build the chain, if it wasn't given as an argument
            chain = self.build_permissions_chain(user)
        for obj in chain:
            if 'underscore' in obj:
                return obj['underscore']

    def check_permissions_chain(self, cmd, user, chain=None):
        #Important note: cmd argument does not include the leading ! of a command
        # Permissions.yml file contains commands without prefix, and we check them
        # here without the prefix
        if chain is None:
            #build the chain, if it wasn't given as an argument
            chain = self.build_permissions_chain(user)
        for obj in chain:
            if 'allow' in obj and cmd in obj['allow']:
                return True, obj['_grant']
            elif 'deny' in obj and cmd in obj['deny']:
                return False, obj['_grant']
            elif cmd.startswith('_') and 'underscore' in obj:
                return obj['underscore'], obj['_grant']
        return (not cmd.startswith('_'), 'by default') #default behavior

    async def on_message(self, message):
        if message.author == self.user:
            return
        # build the user struct and update the users object
        # FIXME: We should migrate away from self.users[] and add our own get_user method
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
            if message.author.id in self.ignored_users:
                print("Ignoring command from", message.author,":", content)
            elif self.check_permissions_chain(content[0][1:], message.author)[0]:
                print("Command in channel", message.channel, "from", message.author, ":", content)
                await self.commands[content[0]](self, message, content)
            else:
                print("Denied", message.author, "using command", content[0], "in", message.channel)
                await self.send_message(
                    message.channel,
                    "You do not have permissions to use this command\n" +
                    # Add additional message if this is a DM and they may actually
                    # have permissions for this command
                    (("If you have permissions granted to you by a role, "
                     "I cannot check those in private messages\n")
                     if isinstance(message.channel, discord.PrivateChannel)
                     else ""
                    ) +
                    "To check your permissions, use the `!permissions` command"
                )
        # If this was not a command, check if any of the special functions
        # would like to run on this message
        elif message.author.id not in self.ignored_users:
            # Ignored users cannot trigger special handlers
            for check, func in self.special:
                if check(self, message):
                    print("Running special", func.__qualname__)
                    await func(self, message, content)
                    break
        # Check if it is time to run any tasks
        #
        current = time.time()
        for i, (interval, task) in enumerate(self.tasks):
            last = self.update_times[i]
            if current - last > interval:
                print("Running task", task.__qualname__)
                await task(self)
                self.update_times[i] = current

def EnableUtils(bot): #prolly move to it's own bot
    #add some core commands
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command('!output-dev')
    async def cmd_dev(self, message, content):
        """
        `!output-dev` : Any messages that would always go to general will go to testing grounds
        """
        self.general = self.dev_channel
        self.bug_channel = self.dev_channel
        await self.send_message(
            self.dev_channel,
            "Development mode enabled. All messages will be sent to testing grounds"
        )

    @bot.add_command('!output-prod')
    async def cmd_prod(self, message, content):
        """
        `!output-prod` : Restores normal message routing
        """
        self.general = self._general
        self.bug_channel = self._bug_channel
        await self.send_message(
            self.dev_channel,
            "Production mode enabled. All messages will be sent to general"
        )

    @bot.add_command('!_announce')
    async def cmd_announce(self, message, content):
        """
        `!_announce <message>` : Forces me to say the given message in general.
        Example: `!_announce I am really cool`
        """
        await self.send_message(
            self.general,
            message.content.strip().replace('!_announce', '')
        )

    @bot.add_command('!permissions')
    async def cmd_perms(self, message, content):
        """
        `!permissions` : Gets a list of commands you have permissions to use
        """
        chain = self.build_permissions_chain(message.author)
        cmds = []
        for command in sorted(self.commands):
            (allow, rule) = self.check_permissions_chain(command[1:], message.author, chain)
            if allow:
                cmds.append((
                    command,
                    rule
                ))
        body = ["Here are the commands you have permissions to use:"]
        for cmd, rule in cmds:
            body.append('`%s` : Granted **%s**' % (
                cmd,
                rule
            ))
        if isinstance(message.channel, discord.PrivateChannel):
            body.append(
                "You may have additional permissions granted to you by a role"
                " but I cannot check those within a private chat. Try the"
                " `!permissions` command in a server channel"
            )
        await self.send_message(
            message.author,
            '\n'.join(body)
        )

    @bot.add_command('!ignore')
    async def cmd_ignore(self, message, content):
        """
        `!ignore <user id or user#tag>` : Ignore all commands by the given user
        until the next time I'm restarted
        Example: `!ignore Username#1234` Ignores all commands from Username#1234
        """
        if len(content) != 2:
            await self.send_message(
                message.channel,
                "Syntax is `!ignore <user id or user#tag>`"
            )
        else:
            try:
                uid = self.getid(content[1])
                if uid in self.ignored_users:
                    await self.send_message(
                        message.channel,
                        "This user is already ignored"
                    )
                    return
                self.ignored_users.add(uid)
                save_db(
                    list(self.ignored_users),
                    'ignores.json'
                )
                user = self.primary_server.get_member(uid)
                await self.send_message(
                    user,
                    "I have been asked to ignore you by %s. Please contact them"
                    " to petition this decision." % (str(message.author))
                )
                await self.send_message(
                    self.general,
                    "%s has asked me to ignore %s. %s can no longer issue any commands"
                    " until they have been `!pardon`-ed" % (
                        str(message.author),
                        str(user),
                        getname(user)
                    )
                )
            except NameError:
                await self.send_message(
                    message.channel,
                    "I couldn't find that user. Please provide a user id or user#tag"
                )

    @bot.add_command('!pardon')
    async def cmd_pardon(self, message, content):
        """
        `!pardon <user id or user#tag>` : Pardons the user and allows them to issue
        commands again.
        Example: `!pardon Username#1234` pardons Username#1234
        """
        if len(content) != 2:
            await self.send_message(
                message.channel,
                "Syntax is `!pardon <user id or user#tag>`"
            )
        else:
            try:
                uid = self.getid(content[1])
                if uid not in self.ignored_users:
                    await self.send_message(
                        message.channel,
                        "This user is not currently ignored"
                    )
                self.ignored_users.remove(uid)
                save_db(
                    list(self.ignored_users),
                    'ignores.json'
                )
                user = self.primary_server.get_member(uid)
                await self.send_message(
                    user,
                    "You have been pardoned by %s. I will resume responding to "
                    "your commands." % (str(message.author))
                )
                await self.send_message(
                    self.general,
                    "%s has pardoned %s" % (
                        str(message.author),
                        str(user)
                    )
                )
            except NameError:
                await self.send_message(
                    message.channel,
                    "I couldn't find that user. Please provide a user id or user#tag"
                )


    return bot
