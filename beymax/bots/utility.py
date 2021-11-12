from ..core import CommandSuite
from ..args import Arg, ChannelType, UserType, DateType
from ..utils import DBView
from datetime import datetime, timedelta
import json
import discord
import asyncio

Utility = CommandSuite('Utilities')

Utility.reserve_channel('dev') # Reserve a reference for a development channel

@Utility.add_command('_task', Arg('task', remainder=True, help='task name'))
async def cmd_task(self, message, task):
    """
    `$!_task <task name>` : Manually runs the named task
    """
    key = ' '.join(task)
    if not key.startswith('task:'):
        key = 'task:'+key
    if key in self.tasks:
        print("Manually running task", key, '(', self.tasks[key][1], ')')
        self.dispatch(key)
    else:
        await self.send_message(
            message.channel,
            "No such task"
        )

@Utility.add_command('_nt')
async def cmd_nt(self, message):
    await self.send_message(
        message.channel,
        '%d events have been dispatched' % self.nt
    )

@Utility.add_command('_announce', Arg('destination', type=ChannelType(Utility, by_name=False, nullable=True), nargs='?', help="Direct output to specific channel (provide a channel mention)", default=None), Arg('content', remainder=True, help="Message to echo"))
async def cmd_announce(self, message, destination, content):
    """
    `$!_announce <message>` : Forces me to say the given message in general.
    Example: `$!_announce I am really cool`
    """
    content = message.content.strip().replace(self.command_prefix+'_announce', '', 1).strip()
    # do this better with indexing
    if destination is not None and destination is not False:
        if content.startswith(destination.name):
            contant = content.replace(destination.name, '', 1)
        elif content.startswith(str(destination.id)):
            content = content.replace(str(destination.id), '', 1)
        elif content.startswith(destination.mention):
            content = content.replace(destination.mention, '', 1)
    await self.send_message(
        destination if destination is not None and destination is not False else self.fetch_channel('general'),
        # Don't use content here because we want to preserve whitespace
        content
    )

@Utility.add_command('permissions')
async def cmd_perms(self, message):
    """
    `$!permissions` : Gets a list of commands you have permissions to use
    """
    chain = self.permissions.query(message.author)
    cmds = []
    for command in sorted(self.commands):
        (allow, rule) = self.permissions.query(message.author, self.strip_prefix(command), _chain=chain)
        if allow:
            cmds.append((
                command,
                rule
            ))
    body = ["Here are the commands you have permissions to use:"]
    for cmd, rule in cmds:
        body.append('`%s` : Granted **%s**' % (
            cmd,
            'by default' if rule.type is None else (
                "by role `{}`".format(rule.data['name']) if rule.type is 'role'
                else (
                    'to you and {} others'.format(rule.data['priority'] - 1)
                    if rule.data['priority'] > 1
                    else 'directly to you'
                )
            )
        ))
    if isinstance(message.channel, discord.abc.PrivateChannel) and self.primary_guild is None:
        body.append(
            "You may have additional permissions granted to you by a role"
            " but I cannot check those within a private chat. Try the"
            " `$!permissions` command in a guild channel"
        )
    await self.send_message(
        message.author,
        '\n'.join(body)
    )

@Utility.add_command('ignore', Arg('user', type=UserType(Utility, by_nick=False), help="Username or ID"))
async def cmd_ignore(self, message, user):
    """
    `$!ignore <user id or user#tag>` : Ignore all commands by the given user
    until the next time I'm restarted
    Example: `$!ignore Username#1234` Ignores all commands from Username#1234
    """
    if user.id in self.ignored_users:
        await self.send_message(
            message.channel,
            "This user is already ignored"
        )
        return
    self.ignored_users.add(user.id)
    await DBView.overwrite(ignores=list(self.ignored_users))
    for guild in self.guilds:
        if user is not None:
            general = self.fetch_channel('general')
            if general.guild != guild:
                general = discord.utils.get(
                    guild.channels,
                    name='general',
                    type=discord.ChannelType.text
                )
            if self.config_get('ignore_role') != None:
                blacklist_role = self.config_get('ignore_role')
                for role in guild.roles:
                    if role.id == blacklist_role or role.name == blacklist_role:
                        await self.add_roles(
                            user,
                            role
                        )
            try:
                await self.send_message(
                    general,
                    "%s has asked me to ignore %s. %s can no longer issue any commands"
                    " until they have been `$!pardon`-ed" % (
                        str(message.author),
                        str(user),
                        getname(user)
                    )
                )
            except:
                pass
    await self.send_message(
        user,
        "I have been asked to ignore you by %s. Please contact them"
        " to petition this decision." % (str(message.author))
    )

@Utility.add_command('pardon', Arg('user', type=UserType(Utility, by_nick=False), help="Username or ID"))
async def cmd_pardon(self, message, user):
    """
    `$!pardon <user id or user#tag>` : Pardons the user and allows them to issue
    commands again.
    Example: `$!pardon Username#1234` pardons Username#1234
    """
    if user.id not in self.ignored_users:
        await self.send_message(
            message.channel,
            "This user is not currently ignored"
        )
        return
    self.ignored_users.remove(user.id)
    await DBView.overwrite(ignores=list(self.ignored_users))
    for guild in self.guilds:
        if user is not None:
            general = self.fetch_channel('general')
            if general.guild != guild:
                general = discord.utils.get(
                    guild.channels,
                    name='general',
                    type=discord.ChannelType.text
                )
            if self.config_get('ignore_role') != None:
                blacklist_role = self.config_get('ignore_role')
                for role in guild.roles:
                    if role.id == blacklist_role or role.name == blacklist_role:
                        await user.remove_roles(
                            role
                        )
            try:
                await self.send_message(
                    general,
                    "%s has pardoned %s" % (
                        str(message.author),
                        str(user)
                    )
                )
            except:
                pass
    await self.send_message(
        user,
        "You have been pardoned by %s. I will resume responding to "
        "your commands." % (str(message.author))
    )

@Utility.add_command('idof', Arg('query', remainder=True, help="Entity to search for"))
async def cmd_idof(self, message, query):
    """
    `$!idof <entity>` : Gets a list of all known entities by that name
    Example: `$!idof general` would list all users, channels, and roles with that name
    """
    guilds = [message.guild] if message.guild is not None else self.guilds
    result = []
    query = ' '.join(query).lower()
    for guild in guilds:
        first = True
        if query in guild.name.lower():
            if first:
                first = False
                result.append('From guild `%s`' % guild.name)
            result.append('Guild `%s` : %s' % (guild.name, guild.id))
        for channel in guild.channels:
            if query in channel.name.lower():
                if first:
                    first = False
                    result.append('From guild `%s`' % guild.name)
                result.append('Channel `%s` : %s' % (channel.name, channel.id))
        for role in guild.roles:
            if query in role.name.lower():
                if first:
                    first = False
                    result.append('From guild `%s`' % guild.name)
                result.append('Role `%s` : %s' % (role.name, role.id))
        for member in guild.members:
            if member.nick is not None and query in member.nick.lower():
                if first:
                    first = False
                    result.append('From guild `%s`' % guild.name)
                result.append('Member `%s` aka `%s` : %s' % (
                    str(member),
                    member.nick,
                    member.id
                ))
            elif query in member.name.lower():
                if first:
                    first = False
                    result.append('From guild `%s`' % guild.name)
                result.append('Member `%s`: %s' % (
                    str(member),
                    member.id
                ))
    if len(result):
        await self.send_message(
            message.channel,
            '\n'.join(result)
        )
    else:
        await self.send_message(
            message.channel,
            "I was unable to find any entities by that name"
        )

@Utility.add_command('timer', Arg('minutes', type=int, help="How many minutes"))
async def cmd_timer(self, message, minutes):
    """
    `$!timer <minutes>` : Sets a timer to run for the specified number of minutes
    """
    await self.dispatch_future(
        datetime.now() + timedelta(minutes=minutes),
        'timer-reminder-expired',
        userID=message.author.id,
        channelID=message.channel.id,
        messageID=message.id,
        text="{}, your {} minute timer is up!".format(message.author.mention, minutes),
    )
    await self.send_message(
        message.channel,
        "Okay, I'll remind you in %d minute%s" % (
            minutes,
            '' if minutes == 1 else 's'
        )
    )

@Utility.add_command('_viewdb', Arg('scopes', help='Optional list of DB scopes to view', nargs='*', default=None))
async def cmd_viewdb(self, message, scopes):
    """
    `$!_viewdb [scopes...]` : Displays the current database state
    If scopes are provided, then only show the requested scopes
    """
    async with DBView() as db:
        if scopes is None or not len(scopes):
            await self.send_message(
                message.channel,
                json.dumps(
                    {key:DBView.serializable(db[key]) for key in iter(db)},
                    indent=2,
                    sort_keys=False
                )
            )
        else:
            await self.send_message(
                message.channel,
                json.dumps(
                    {key:DBView.serializable(db[key]) for key in scopes if key in db},
                    indent=2,
                    sort_keys=False
                )
            )

@Utility.add_command('_dropdb', Arg('scopes', help='List of DB scopes to delete', nargs='+', default=None))
async def cmd_flushdb(self, message, scopes):
    """
    `$!_dropdb [scopes...]` : Deletes the given scopes from the database
    """
    async with DBView(*scopes) as db:
        await self.send_message(
            message.channel,
            "You are about to delete {} scopes with {} records. Is that okay?".format(
                len(scopes),
                sum(len(db[scope]) for scope in scopes)
            )
        )
        try:
            response = await self.wait_for(
                'message',
                check=lambda m: m.author==message.author and m.channel == message.channel,
                timeout=15,
            )
        except asyncio.TimeoutError:
            await self.send_message(
                message.channel,
                "I don't got all day! If you want to delete more tables,"
                " you'll have to issue that command again"
            )
            return
        if response.content.strip().lower() == 'yes':
            for scope in scopes:
                db[scope] = {}
        else:
            await self.send_message(
                message.channel,
                "Cancelled"
            )


@Utility.add_command('_printdb', Arg('scopes', help='Optional list of DB scopes to view', nargs='*', default=None))
async def cmd_printdb(self, message, scopes):
    """
    `$!_printdb [scopes...]` : Displays the current database state
    If scopes are provided, then only show the requested scopes
    """
    async with DBView() as db:
        if scopes is None or not len(scopes):
            print(
                {key:DBView.serializable(db[key]) for key in iter(db)}
            )
        else:
            print(
                {key:DBView.serializable(db[key]) for key in scopes if key in db}
            )


@Utility.add_command("remind", Arg('date', type=DateType, help="When should I remind you"))
async def cmd_reminder(self, message, date):
    """
    `$!remind (when)` : I'll send you a reminder about this message on the given date
    """
    await self.dispatch_future(
        date,
        'timer-reminder-expired',
        userID=message.author.id,
        channelID=message.channel.id,
        messageID=message.id,
        text="Hey, {} here's your reminder".format(message.author.mention),
    )
    await self.send_message(
        message.channel,
        "Okay, I'll remind you of this message on {}".format(
            date.strftime('%m/%d/%Y')
        )
    )

@Utility.subscribe('timer-reminder-expired')
async def test_reminders(self, _, userID, channelID, messageID, text):
    channel = self.get_channel(channelID)
    user = self.get_user(userID)
    message = await channel.fetch_message(messageID)
    await channel.send(
        text,
        reference=message.to_reference()
    )
