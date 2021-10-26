from .utils import DBView, getname, Interpolator, standard_intents, TIMESTAMP_FORMAT
from .args import Arg, Argspec, UserType, ChannelType, DateType
from .perms import PermissionsFile
import discord
import asyncio
import time
import os
import yaml
from math import ceil
import sys
import shlex
from functools import wraps, partial
import re
import traceback
import warnings
import json
from datetime import datetime, timedelta

mention_pattern = re.compile(r'<@.*?(\d+)>')

class CoreBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, intents=standard_intents(), **kwargs)
        self.nt = 0
        self.configuration = {}
        self.primary_guild = None
        self.channel_references = {} # reference name -> channel name/id
        self.event_listeners = {} # event name -> [listener functions (self, event)]
        # changed to set in favor of event API
        self.commands = {} # !cmd -> docstring. Functions take (self, message, content)
        self.ignored_users = set()
        self.tasks = {} # taskname (auto generated) -> [interval(s), qualname] functions take (self)
        self.special = {} # eventname -> checker. callable takes (self, message) and returns True if function should be run. Func takes (self, message, content)
        self.special_order = []
        self._dbg_event_queue = []
        self.debounced_channels = {}
        self.channel_lock = asyncio.Lock()
        if os.path.exists('config.yml'):
            with open('config.yml') as reader:
                self.configuration = yaml.load(reader)
        else:
            self.configuration = {}
        self.command_prefix = self.config_get('prefix', default='!')

        # Debounced messages are done through an event handler, so there must be a subscription
        # However, since this is a core feature, the subscription can't be added in a sub-bot
        @self.subscribe('debounce-send')
        async def _debounced_send_message(self, evt, dest, content):
            """
            Debounces outbound messages per-channel.
            If any kwargs are provided, this sends immediately (no logical way to
            concatenate the kwargs)
            Waits 1s before sending a message, then
            """
            async with self.channel_lock:
                if dest.id not in self.debounced_channels:
                    # print("DEBOUNCE: Starting new queue for", dest.id)
                    self.debounced_channels[dest.id] = content
                else:
                    # print("DEBOUNCE: Appending to queue for", dest.id)
                    self.debounced_channels[dest.id]+='\n'+content
                MSG_LEN = len(self.debounced_channels[dest.id])
            await asyncio.sleep(.5) # wait 500ms for other messages
            async with self.channel_lock:
                if MSG_LEN == len(self.debounced_channels[dest.id]):
                    # No other messages were added to the queue while waiting
                    # print("DEBOUNCE: Finally sending", dest.id)
                    content = self.debounced_channels[dest.id]
                    del self.debounced_channels[dest.id]
                    await self._bulk_send_message(dest, content)

        # Future dispatch events are handled as a task
        # But tasks must be added to an existing bot
        @self.add_task(30)
        async def check_future_dispatch(self):
            now = datetime.now()
            async with DBView('core_future_dispatch', core_future_dispatch=[]) as db:
                for event in db['core_future_dispatch']:
                    target = datetime.strptime(evt['date'], TIMESTAMP_FORMAT)
                    if target <= now:
                        overshoot = (now - target).total_seconds()
                        if overshoot > 1:
                            print("WARNING: Future dispatch", event['event'], "overshot by", overshoot)
                        self.dispatch(
                            event['event'],
                            *event['args'],
                            **event['kwargs']
                        )
                db['core_future_dispatch'] = [
                    evt for evt in db['core_future_dispatch']
                    if datetime.strptime(evt['date'], TIMESTAMP_FORMAT) > now
                ]
                if len(db['core_future_dispatch']):
                    check_future_dispatch.update_interval(
                        min(
                            ceil((datetime.strptime(event['date'], TIMESTAMP_FORMAT) - now).total_seconds())
                            for evt in db['core_future_dispatch']
                        ),
                        False
                    )


    def add_command(self, command, *spec, aliases=None, delimiter=None, **kwargs): #decorator. Attaches the decorated function to the given command(s)
        """
        Decorator. Registers the given function as the handler for the specified command.
        Arguments:
        command : The name of the command. Messages starting with this word (with the command prefix prepended) will run this function
        *spec : A variable number of Arg objects. These objects follow the argparse.add_argument syntax.
        aliases : (Optional) List of other words to accept as the command.
        delimiter : (Optional) A string to use to split individual arguments of the command, instead of whitespace
        **kwargs : (Optional) A set of keyword arguments to pass on the the argument parser

        The decorated function must be a coroutine (async def) and use one of the following call signatures:
        The first two arguments will be the bot object and the message object.
        * If empty is False and no spec is provided, the last argument will be a list of lowercase strings from splitting the message content by the delimiter
        * Otherwise, the last argument will be an argparse.Namespace object containing the arguments parsed from the message

        Note: The docstring of command functions is used as the command's help text.
        """
        if aliases is None:
            aliases = []
        for arg in spec:
            if isinstance(arg, str):
                raise TypeError("Please define command aliases using the aliases keyword")
        if self.config_get('use_shlex') and delimiter is not None:
            print(
                "Warning: (%s) The use of delimiters is discouraged in shlex mode. Instead, "
                "have users quote their arguments" % command
            )

        def wrapper(func):
            @wraps(func)
            async def on_cmd(self, cmd, message):
                if self.permissions.query(message.author, self.strip_prefix(cmd))[0]:
                    print("Command in channel", message.channel, "from", message.author, ":", message.content.strip().split())
                    argspec = Argspec(cmd, *spec, **kwargs)
                    if delimiter is not None and delimiter not in message.content:
                        delim = None
                    elif self.config_get('disable_delimiters'):
                        print("Warning: Ignoring delimiter")
                        delim = None
                    else:
                        delim = delimiter
                    if delim is None:
                        raw_args = message.content[len(cmd):].strip().split()
                    else:
                        raw_args = message.content[len(cmd):].strip().split(delim)
                    result, args = argspec(*raw_args, delimiter=delimiter)
                    if not result:
                        await self.send_message(
                            message.channel,
                            args
                        )
                        return
                    try:
                        # Extract arguments (args) into keyword args
                        await func(self, message, **vars(args))
                    except discord.DiscordException:
                        await self.trace()
                        await self.send_message(
                            message.channel,
                            "I've encountered an error communicating with Discord."
                            " This may be a transient issue, but if it occurs again"
                            " you should submit a bug report: `$!bug <Discord Exception> %s`"
                            % (message.content.replace('`', ''))
                        )
                    except:
                        await self.trace()
                        await self.send_message(
                            message.channel,
                            "I encountered unexpected error while processing your"
                            " command. Please submit a bug report: `$!bug <Python Exception> %s`"
                            % (message.content.replace('`', ''))
                        )
                    self.dispatch('command', cmd, message.author)
                else:
                    print("Denied", message.author, "using command", cmd, "in", message.channel)
                    await self.send_message(
                        message.channel,
                        "You do not have permissions to use this command\n" +
                        # Add additional message if this is a DM and they may actually
                        # have permissions for this command
                        (("If you have permissions granted to you by a role, "
                         "I cannot check those in private messages\n")
                         if isinstance(message.channel, discord.abc.PrivateChannel) and
                         self.primary_guild is None
                         else ""
                        ) +
                        "To check your permissions, use the `$!permissions` command"
                    )


            for cmd in [command] + aliases:
                if not cmd.startswith(self.command_prefix):
                    cmd = self.command_prefix + cmd
                on_cmd = self.subscribe(cmd)(on_cmd)
                self.commands[cmd] = {
                    'docstring': func.__doc__,
                    'args': spec,
                    'argspec': Argspec(cmd, *spec, **kwargs), # Should reuse
                    'delimiter': delimiter
                }
            return func

        return wrapper

    def add_task(self, interval): #decorator. Sets the decorated function to run on the specified interval
        """
        Decorator. Sets the decorated function to run on the specified interval.
        Arguments:
        interval : The interval in which to run the function, in seconds

        The decorated function must be a coroutine (async def) and take only the bot object as an argument
        """
        #FIXME: Add dynamic interval updates
        def wrapper(func):
            taskname = 'task:'+func.__name__
            if taskname in self.tasks:
                raise NameError("This task already exists! Change the name of the task function")
            self.tasks[taskname] = (interval, func.__qualname__)

            @self.subscribe(taskname)
            async def run_task(self, task):
                print("Running", taskname, func.__qualname__)
                # If the task set a temporary interval, check it here
                if isinstance(self.tasks[taskname][0], tuple):
                    print("Task", taskname, "Reverting interval to", self.tasks[taskname][0][1])
                    self.tasks[taskname] = (self.tasks[taskname][0][1], func.__qualname__)
                # Run task
                await func(self)
                # Update last executed time (Used for restoring task intervals after shutdown)
                async with DBView('tasks', tasks={'key': None, 'tasks': {}}) as db:
                    db['tasks']['tasks'][taskname] = time.time()

            def update_interval(next_interval, permanent=True):
                next_interval = max(1, next_interval)
                print("Task", taskname, "update task interval to", next_interval, "(persistent)" if permanent else "(temporary)")
                self.tasks[taskname] = (
                    next_interval if permanent else (next_interval, interval),
                    func.__qualname__
                )

            run_task.update_interval = update_interval

            return run_task
        return wrapper

    def add_special(self, check): #decorator. Sets the decorated function to run whenever the check is true
        """
        Decorator. Sets the decorated function to run whenever the given check function is True.
        Arguments:
        check : A function which takes a message argument and returns True if the decorated function should be run

        The decorated function must be a coroutine (async def) and take the three following arguments:
        * The bot object
        * The message object
        * A list of lowercased, whitespace delimited strings
        """
        def wrapper(func):
            event = 'special:'+func.__name__
            if event in self.special:
                raise NameError("This special event already exists! Change the name of the special function")
            self.special[event] = check
            self.special_order.append(event)

            @self.subscribe(event)
            async def run_special(self, evt, message, content):
                await func(self, message, content)

            return run_special
        return wrapper

    async def dispatch_future(self, when, event, *args, **kwargs):
        """
        Schedule the given event to be dispatched at a time in the future.
        When can be a datetime object, timedelta object, or integer (interpreted as seconds in the future).
        Event should be the string name of an event to dispatch.
        Remaining arguments will be passed to the event handler on dispatch.
        Note: Arguments and keyword arguments must be serializable.
        To save discord objects, use DB serializers (planned)
        """
        if isinstance(when, int):
            when = datetime.now() + timedelta(seconds=when)
        elif isinstance(when, timedelta):
            when = datetime.now() + when
        elif not isinstance(when, datetime):
            raise TypeError("When must be a datetime, timedelta, or int object, not {}".format(type(when)))
        async with DBView('core_future_dispatch', core_future_dispatch=[]) as db:
            db['core_future_dispatch'].append({
                'date': when.strftime(TIMESTAMP_FORMAT),
                'event': event,
                'args': args,
                'kwargs': kwargs
            })

    def migration(self, key):
        """
        Migrations run after the bot has connected to discord and has readied.
        Discord interactions will be ready
        """
        def wrapper(func):
            @self.subscribe('after:ready')
            async def run_migration(self, _):
                # check migration
                async with DBView('core_migrations') as db:
                    if key not in db['core_migrations']:
                        # run migration
                        await func(self)
                        # update db migration state
                        db['core_migrations'][key] = datetime.now().strftime(TIMESTAMP_FORMAT)
        return wrapper

    def subscribe(self, event): # decorator. Sets the decorated function to run on events
        """
        Decorator. Sets the decorated function to be run whenever the given event
        is dispatched.
        Arguments:
        event : A string argument name. WHen that argument is dispatched, the decorated function will run

        The decorated function must be a coroutine (async def). The function must take
        the event name as the first argument, and any additional arguments/keyword arguments
        are determined by the arguments to the dispatch() function
        """
        # event functions should take the event, followed by expected arguments
        def wrapper(func):
            if str(event) not in self.event_listeners:
                self.event_listeners[str(event)] = []
            self.event_listeners[str(event)].append(func)
            # func.unsubscribe will unsubscribe the function from the event
            # calling without args unsubscribes from the most recent event that this
            # function was subscribed to. An event can be specified to unsubscribe
            # from a specific event, if the function was subscribed to several
            func.unsubscribe = lambda x=str(event):self.event_listeners[x].remove(func)
            return func
        return wrapper

    def reserve_channel(self, name):
        """
        Call to declare a channel reference. The bot configuration can then map
        this reference to an actual channel. By default all undefined references
        map to general
        Arguments:
        name : A string channel reference to reserve
        """
        # creates a channel reference by that name
        # channel references can be changed in configuration
        self.channel_references[name] = None

    def fetch_channel(self, name):
        """
        Fetch the channel object for a given reference name. If the reference is
        undefined, it returns general
        Arguments:
        name : A string channel reference to lookup
        """
        channel = self.channel_references[name] if name in self.channel_references else None
        if channel is None:
            return self.fetch_channel('general')
        return channel

    def EnableAll(self, *bots): #convenience function to enable a bunch of subbots at once
        """
        Enables all of the given Enable_ sub-bot suites.
        Arguments:
        *bots : A set of functions which take the bot object. Each function should perform setup required to
            initialize a sub-bot, such as registering commands, tasks, and channel references
        """
        for bot in bots:
            if callable(bot):
                self = bot(self)
            else:
                raise TypeError("Bot is not callable")
        return self

    def strip_prefix(self, command):
        """
        Returns a string with the command prefix removed.
        Arguments:
        command : A string to remove the command prefix from
        """
        if command.startswith(self.command_prefix):
            return command[len(self.command_prefix):]
        return command

    def dispatch(self, event, *args, manual=False, **kwargs):
        """
        Manually dispatches an event (may be used to trigger tasks, commands, etc programatically).
        Arguments:
        event : The string event name to dispatch
        *args : Arguments to provide to the event handler
        manual : (Optional) If True, do not attempt to dispatch before: and after: events
        **kwargs : Keyword arguments to provide to the event handler

        By default, when dispatch is called:
        * Run any functions subscribed to before:{event}
        * Run any functions subscribed to the event in the base class (discord.Client)
        * Run any functions subscribed to the event
        * Run any functions subscribed to after:{event}
        """
        self.nt += 1
        output = []
        if not manual:
            while len(self._dbg_event_queue) >= 100:
                self._dbg_event_queue.pop(0)
            self._dbg_event_queue.append(event)
            if 'before:'+str(event) in self.event_listeners:
                output += self.dispatch_event('before:'+str(event), *args, **kwargs)
            super().dispatch(event, *args, **kwargs)
            if str(event) in self.event_listeners:
                output += self.dispatch_event(str(event), *args, **kwargs)
            if 'after:'+str(event) in self.event_listeners:
                output += self.dispatch_event('after:'+str(event), *args, **kwargs)
        else:
            if str(event) in self.event_listeners:
                output += self.dispatch_event(str(event), *args, **kwargs)
        return output

    def dispatch_event(self, event, *args, **kwargs):
        """
        Called internally. Sets the internal event loop to run event handlers for
        a given event
        """
        return [
            asyncio.ensure_future(listener(self, event, *args, **kwargs), loop=self.loop)
            for listener in self.event_listeners[event]
        ]



    def config_get(self, *keys, default=None):
        """
        Retrieve a given key from the configuration. A multiple keys may be given to retrieve a nested value.
        Arguments:
        *keys : List of nested keys to read from the configuration
        default : (Optional) The fallback value to return if the requested key path does not exist or is undefined. Defaults to None
        """
        obj = self.configuration
        for key in keys:
            try:
                if key in obj:
                    obj = obj[key]
                else:
                    return default
            except TypeError:
                return default
        return obj

    async def on_ready(self):
        """
        Coroutine. Default event handler for the bot going online.
        Handles core functions such as checking primary_guild configuration and
        parsing the permissions file into a set of rules.
        Do not override. Instead, use @bot.subsribe('ready') to add additional handling
        to this event
        """
        try:
            print("Connected to the following guilds")
            if 'primary_guild' in self.configuration:
                self.primary_guild = discord.utils.get(
                    self.guilds,
                    id=self.configuration['primary_guild']
                )
                if self.primary_guild is None:
                    sys.exit("Primary guild set, but no matching guild was found")
                else:
                    print("Validated primary guild:", self.primary_guild.name)
            else:
                print("Warning: No primary guild set in configuration. Role permissions cannot be validated in PM's")
            first = True
            for guild in list(self.guilds):
                print(guild.name, guild.id)
                await self.on_guild_join(guild)
            print("Commands:", [cmd for cmd in self.commands])
            print(
                "Tasks:",
                '\n'.join([
                    '%s every %d seconds (Runs %s)' % (
                        taskname,
                        *self.tasks[taskname]
                    ) for taskname in self.tasks
                ])
            )
            self._general = discord.utils.get(
                self.get_all_channels(),
                name='general',
                type=discord.ChannelType.text
            )
            async with DBView('tasks', tasks={'key': None, 'tasks': {}}) as db:
                taskkey = ''.join(sorted(self.tasks))
                if 'key' not in db['tasks'] or db['tasks']['key'] != taskkey:
                    print("Invalidating task time cache")
                    db['tasks'] = {'key':taskkey, 'tasks':{}}
                else:
                    print("Not invalidating task cache")

            self.channel_references['general'] = self._general
            if 'channels' in self.configuration:
                for name in self.channel_references:
                    if name in self.configuration['channels']:
                        channel = discord.utils.get(
                            self.get_all_channels(),
                            name=self.configuration['channels'][name],
                            type=discord.ChannelType.text
                        )
                        if channel is None:
                            channel = discord.utils.get(
                                self.get_all_channels(),
                                id=self.configuration['channels'][name],
                                type=discord.ChannelType.text
                            )
                        if channel is None:
                            raise NameError("No channel by name of "+self.configuration['channels'][name])
                        self.channel_references[name] = channel
                    else:
                        print("Warning: Channel reference", name, "is not defined")
            print(self.channel_references)
            # Preload server ignores. Readonly, but default to list
            async with DBView(ignores=[]) as db:
                self.ignored_users = set(db['ignores'])
            self.permissions = await PermissionsFile.load(self, 'permissions.yml')
            asyncio.ensure_future(self.task_runner(), loop=self.loop)

        except:
            traceback.print_exc()
            sys.exit("Unhandled exception during startup")

    async def trace(self, send=True):
        """
        Coroutine. Prints a stack trace to the console, and optionally sends it to the registered
        bugs channel
        Arguments:
        send : (Optional) If True (the default) post the stack trace to the bugs channel
        """
        x,y,z = sys.exc_info()
        if x is None and y is None and z is None:
            msg = traceback.format_stack()
        else:
            msg = traceback.format_exc()
        print(msg)
        if send and self.config_get('send_traces'):
            await self.send_message(
                self.fetch_channel('bugs'),
                msg,
                quote='```'
            )

    async def shutdown(self):
        """
        Coroutine. Use this function for a clean shutdown.
        Dispatches the 'cleanup' event, waits for all tasks to complete, then disconnects
        the bot
        """
        await self.change_presence(status=discord.Status.offline)
        tasks = self.dispatch('cleanup')
        if len(tasks):
            print("Waiting for ", len(tasks), "cleanup tasks to complete")
            await asyncio.wait(tasks)
        await self.close()

    async def send_message(self, destination, content, *, delim='\n', quote='', interp=None, skip_debounce=False, **kwargs):
        """
        Coroutine. Primary send-message function. Use to post a message to any channel.
        Arguments:
        destination : A channel or User object to specify where to send the message
        content : A string containing the message body to send
        Keyword Only arguments:
        delim : String to use to break up the content if it is too large to send in one message. Defaults to newline
        quote : String to use to quote the message content (prepend and append to content). Defaults to empty string
        interp : Object to use to interpolate substitutions in the message content. Interp may be any of the following:
            None : (Default) Build a default Interpolator object relative to the given destination to parse the message content
            False : Disable interpolation. Message will be sent as-is
            Interpolator instance : A premade Interpolator instance to use in addition to the default Interpolator for the channel.
                Substitutions from both Interpolators are used, but the user provided one takes priority when they both substitute a string
            discord.Channel instance : Build a default Interpolator but for a channel other than the current destination
            dict instance : Substitute each occurence of a key in the dictionary with the associated value
        skip_debounce : If set to True, send the message immediately without debouncing. By default, messages are debounced for 500ms
            so that messages going to the same channel can be concatenated to avoid rapidly sending short messages
        **kwargs : Additional keyword arguments to provide to the base class (discord.Client) send_message function.

        Setting quote or providing any kwargs will also disable message debouncing.
        """
        #built in chunking
        if interp is None:
            interp = Interpolator(self, destination)
        elif interp is False:
            interp = {}
        elif isinstance(interp, Interpolator):
            tmp = Interpolator(self, destination)
            tmp.update(**interp)
            interp = tmp
        elif isinstance(interp, discord.abc.Messageable):
            interp = Interpolator(self, interp)
        elif not isinstance(interp, dict):
            raise TypeError("Cannot infer interpolation settings from an object of type "+type(interp))
        try:
            for key in interp:
                content = content.replace(key, interp[key])
        except:
            traceback.print_exc()
            print("Interpolation Error: ", {**interp})
        for match in mention_pattern.finditer(content):
            uid = match.group(1)
            do_sub = isinstance(destination, discord.User) and destination.id != uid
            do_sub |= hasattr(destination, 'guild') and self.get_user(uid, destination.guild) is None
            do_sub |= hasattr(destination, 'recipients') and uid not in {user.id for user in destination.recipients}
            if do_sub:
                warnings.warn(
                    "Mention backup substitution will no longer be supported in the future",
                    DeprecationWarning
                )
                await self.trace()
                # have to replace the mention with a `@Username`
                user = self.get_user(uid)
                if user is not None:
                    content = content.replace(
                        match.group(0),
                        # '`@%s#%s`' % (user.name, str(user.discriminator)),
                        '`!{}#{}!`'.format(user.name, user.discriminator),
                        1
                    )
        if skip_debounce or quote != '' or len(kwargs):
            return await self._bulk_send_message(
                destination,
                content,
                delim=delim,
                quote=quote,
                **kwargs
            )
        else:
            self.dispatch('debounce-send', destination, content)
            # return await self._debounced_send_message(
            #     destination,
            #     content
            # )

    async def _bulk_send_message(self, destination, content, *, delim='\n', quote='', **kwargs):
        """
        Sends a pre-interpolated message
        Large messages are split according to the delimiter
        """
        body = content.split(delim)
        tmp = []
        last_msg = None
        for line in body:
            tmp.append(line)
            msg = delim.join(tmp)
            if len(msg) > 2048 and delim=='. ':
                # If the message is > 2KB and we're trying to split by sentences,
                # try to split it up by spaces
                last_msg = await self._bulk_send_message(
                    destination,
                    msg,
                    delim=' ',
                    interp=False,
                    **kwargs
                )
            elif len(msg) > 1536 and delim=='\n':
                # if the message is > 1.5KB and we're trying to split by lines,
                # try to split by sentences
                last_msg = await self._bulk_send_message(
                    destination,
                    msg,
                    delim='. ',
                    interp=False,
                    **kwargs
                )
            elif len(msg) > 1024:
                # Otherwise, send it if the current message has reached the
                # 1KB chunking target
                try:
                    last_msg = await destination.send(
                        quote+msg+quote,
                        **kwargs
                    )
                except discord.errors.HTTPException as e:
                    await self.trace()
                tmp = []
                await asyncio.sleep(1)
        if len(tmp):
            #send any leftovers (guaranteed <2KB)
            try:
                last_msg = await destination.send(
                    quote+msg+quote
                )
            except discord.errors.HTTPException as e:
                await self.trace()
        return last_msg

    async def send_rich_message(self, destination, *, content=None, author=None, author_url=None, author_icon_url=None, title=None, description=None, colour=None, footer=None, image=None, thumbnail=None, __video=None, url=None):
        """
        Coroutine. Send a message with rich content.
        Arguments:
        destination : A channel or user object to specify where to send the message.
        content (optional): Text to display above the rich embed
        author (optional): Creator. If a User object is passed, this will use the
        user's nickname or username. If a string is passed, the author name will be set to that string
        author_url (optional): Link to embed in the author's name
        author_icon_url (optional): Link to the author's icon. If this is None and
        author is a user object, this will use the user's avatar.
        title (optional): Bold title displayed below author
        description (optional): Main embed content
        colour (optional): Discord color object for sidebar
        footer (optional): Small text to display below embedded content
        image (optional): URL for an image to display
        thumbnail (optional): URL for thumbnail to display in the top right
        ~~video (optional): URL for video to embed~~
        url (optional): Large link to place in center of embed
        """
        if isinstance(author, CoreBot):
            author = author.user

        def apply_kwargs(func, **kwargs):
            return func(**{k:v for k,v in kwargs.items() if v is not None})

        embed = apply_kwargs(discord.Embed, colour=colour, title=title, url=url, description=description)
        if author_icon_url is None and isinstance(author, discord.abc.User):
            author_icon_url = 'https://cdn.discordapp.com/avatars/{}/{}'.format(
                author.id,
                author.default_avatar if author.avatar is None else author.avatar
            )
        if isinstance(author, discord.abc.User):
            author = getname(author)
        if author is not None or author_url is not None or author_icon_url is not None:
            embed = apply_kwargs(embed.set_author, name=author, url=author_url, icon_url=author_icon_url)
        if footer is not None:
            embed = embed.set_footer(text=footer)
        if image is not None:
            embed = embed.set_image(url=image)
        if thumbnail is not None:
            embed = embed.set_thumbnail(url=thumbnail)
        return await destination.send(content=content, embed=embed)


    def get_user(self, reference, *guilds):
        """
        Gets a user object given a form of reference. Optionaly provide a subset of guilds to check
        Arguments:
        reference : A string reference which can either be a user's id or a username to identify a user
        *guilds : A list of guilds to check. By default, this function checks the primary_guild, then all others

        Checks guilds for a user based on id first, then username. Returns the first match
        """
        if not len(guilds):
            guilds = list(self.guilds)
            if self.primary_guild is not None:
                guilds = [self.primary_guild]
        if isinstance(reference, int):
            for guild in guilds:
                result = guild.get_member(reference)
                if result is not None:
                    return result
        elif isinstance(reference, str):
            for guild in guilds:
                result = guild.get_member_named(reference)
                if result is not None:
                    return result
        elif reference is None:
            return None
        else:
            raise TypeError("Unacceptable reference type {}".format(type(reference)))


    def getid(self, username):
        """
        Gets the id of a user based on a reference.
        Arguments:
        username : A reference which may be the full discriminated username or their id
        """
        #Get the id of a user from an unknown reference (could be their username, fullname, or id)
        result = self.get_user(username)
        if result is not None:
            if result.id != username and '#' not in username:
                raise NameError("Username '%s' not valid, must containe #discriminator" % username)
            return result.id
        raise NameError("Unable to locate member '%s'. Must use a user ID, username, or username#discriminator" % username)

    async def on_message(self, message):
        """
        Coroutine. Default handler for incomming messages. Do not override.
        Immediately skips message handling and returns if:
        * The message was sent by this bot
        * The message was sent in a DM by a user who does not have any guilds in common with this bot
        * The message was sent by a user in this bot's ignore list

        Splits the message content by whitespace (or the shlex parser if enabled)

        If the first word starts with the command prefix and is in the list of registered
        commands, dispatch the command handler, which checks permissions then runs the command

        Otherwise, check if any registered special functions should run on this message

        If you wish to add additional handling for messages, use @bot.subscribe('message').
        """
        if message.author == self.user:
            return
        if self.get_user(message.author.id) is None:
            #User is not a member of any known guild
            #silently ignore
            return
        if message.author.id in self.ignored_users:
            print("Ignoring message from", message.author)
            return
        # build the user struct and update the users object
        try:
            content = message.content.strip().split()
            content[0] = content[0].lower()
        except:
            return
        if content[0] in self.commands: #if the first argument is a command
            # dispatch command event
            print("Dispatching command")
            self.dispatch(content[0], message)
        else:
            # If this was not a command, check if any of the special functions
            # would like to run on this message
            for event in self.special_order:
                if self.special[event](self, message):
                    print("Running special", event)
                    self.dispatch(event, message)
                    break

    async def task_runner(self):
        """
        Background worker to run tasks. At most every 30 seconds, while the bot is online,
        check if it is time for any registered tasks to run
        """
        wait_time = 30
        while True:
            if wait_time != 30:
                print("Task runner using dynamic sleep of", wait_time)
            await asyncio.sleep(max(0, wait_time))
            wait_time = 30
            # Check if it is time to run any tasks
            #
            current = time.time()
            # db[tasks] is updated after each task is dispatched. Just get a r/o
            # export to check times.
            taskdata = DBView.readonly_view('tasks', tasks={'tasks': {}})['tasks']['tasks']
            handles = []
            for task, (interval, qualname) in self.tasks.items():
                if isinstance(interval, tuple):
                    interval = interval[0]
                last = 0
                if task in taskdata:
                    last = taskdata[task]
                if (current - last) >= interval:
                    handles += self.dispatch(task)
            start_wait = time.monotonic()
            if len(handles):
                await asyncio.wait(handles)
            taskdata = DBView.readonly_view('tasks', tasks={'tasks': {}})['tasks']['tasks']
            current = time.time()
            wait_time = ceil(min(
                30 + start_wait - time.monotonic(),
                *(
                    (taskdata[task] if task in taskdata else 0) + (
                        interval[0] if isinstance(interval, tuple) else interval
                    ) - current
                    for task, (interval, qualname) in self.tasks.items()
                )
            ))

    async def on_guild_join(self, guild):
        """
        Coroutine. Handler for joining guilds. Do not override.
        If you wish to add handling for joining guilds use @bot.subscribe('guild_join')

        If a primary guild is defined and this is not the primary guild, leave it.
        Otherwise, print a warning that a primary guild is not defined
        """
        if self.primary_guild is not None and self.primary_guild != guild:
            try:
                await self.send_message(
                    discord.utils.get(
                        guild.channels,
                        name='general',
                        type=discord.ChannelType.text
                    ),
                    "Unfortunately, this instance of $NAME is not configured"
                    " to run on multiple guilds. Please contact the owner"
                    " of this instance, or run your own instance of $NAME."
                    " Goodbye!"
                )
            except:
                pass
            await guild.leave()
        elif len(self.guilds) > 1:
            print("Warning: Joining to multiple guilds is not supported behavior")

def EnableUtils(bot): #prolly move to it's own bot
    """
    A sub-bot to enable utility functions
    """
    #add some core commands
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.reserve_channel('dev') # Reserve a reference for a development channel

    @bot.add_command('_task', Arg('task', remainder=True, help='task name'))
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

    @bot.add_command('_nt')
    async def cmd_nt(self, message):
        await self.send_message(
            message.channel,
            '%d events have been dispatched' % self.nt
        )

    @bot.add_command('_announce', Arg('destination', type=ChannelType(bot, by_name=False, nullable=True), nargs='?', help="Direct output to specific channel (provide a channel mention)", default=None), Arg('content', remainder=True, help="Message to echo"))
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

    @bot.add_command('permissions')
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

    @bot.add_command('ignore', Arg('user', type=UserType(bot, by_nick=False), help="Username or ID"))
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

    @bot.add_command('pardon', Arg('user', type=UserType(bot, by_nick=False), help="Username or ID"))
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

    @bot.add_command('idof', Arg('query', remainder=True, help="Entity to search for"))
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

    @bot.add_command('timer', Arg('minutes', type=int, help="How many minutes"))
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

    @bot.add_command('_viewdb', Arg('scopes', help='Optional list of DB scopes to view', nargs='*', default=None))
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
                        sort_keys=True
                    )
                )
            else:
                await self.send_message(
                    message.channel,
                    json.dumps(
                        {key:DBView.serializable(db[key]) for key in scopes if key in db},
                        indent=2,
                        sort_keys=True
                    )
                )
    @bot.add_command("remind", Arg('date', type=DateType, help="When should I remind you"))
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

    @bot.subscribe('timer-reminder-expired')
    async def test_reminders(self, _, userID, channelID, messageID, text):
        for guild in self.guilds:
            channel = guild.get_channel(channelID)
            user = self.get_user(userID)
            message = await channel.fetch_message(messageID)
            await channel.send(
                text,
                reference=message.to_reference()
            )

    return bot
