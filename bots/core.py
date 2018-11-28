from .utils import load_db, save_db, Database, getname, validate_permissions, Interpolator
from .args import Arg, Argspec, UserType
import discord
from discord.compat import create_task
import asyncio
import time
import os
import yaml
import sys
import threading
import shlex
from functools import wraps
import re
import traceback

mention_pattern = re.compile(r'<@.*?(\d+)>')

class CoreBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nt = 0
        self.configuration = {}
        self.primary_server = None
        self.channel_references = {} # reference name -> channel name/id
        self.event_listeners = {} # event name -> [listener functions (self, event)]
        # changed to set in favor of event API
        self.commands = {} # !cmd -> docstring. Functions take (self, message, content)
        self.ignored_users = set()
        self.users = {} # id/fullname -> {id, fullname, mention, name}
        self.tasks = {} # taskname (auto generated) -> [interval(s), qualname] functions take (self)
        self.special = {} # eventname -> checker. callable takes (self, message) and returns True if function should be run. Func takes (self, message, content)
        self.special_order = []
        self._dbg_event_queue = []
        self.debounced_channels = {}
        self.channel_lock = asyncio.Lock()
        if os.path.exists('config.yml'):
            with open('config.yml') as reader:
                self.configuration = yaml.load(reader)
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
                # else:
                #     # Other messages were added, so just wait for a message to return
                #     print("DEBOUNCE: Waiting for", dest.id)
                #     return await self.wait_for_message(
                #         timeout=10, # Max 10s delay before giving up
                #         author=self.user,
                #         check=lambda msg:len({line for line in content.split('\n')} & {line for line in msg.content.split('\n')}) > 0
                #     )

    def add_command(self, command, *spec, aliases=None, delimiter=None, empty=False, **kwargs): #decorator. Attaches the decorated function to the given command(s)
        """
        Decorator. Registers the given function as the handler for the specified command.
        Arguments:
        command : The name of the command. Messages starting with this word (with the command prefix prepended) will run this function
        *spec : (Optional) A variable number of Arg objects. These objects follow the argparse.add_argument syntax.
        aliases : (Optional) List of other words to accept as the command.
        delimiter : (Optional) A string to use to split individual arguments of the command, instead of whitespace
        empty : (Optional) If true, the command will not accept any arguments (only the command word itself)
        **kwargs : (Optional) A set of keyword arguments to pass on the the argument parser

        If at least one spec is provided, user messages will be passed through the argparse API and
        the third argument to the command function will be an argparse Namespace argument instead
        of a list of words in the message.

        Setting empty to True will also use the argparse API but require 0 arguments.

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
            async def on_cmd(self, cmd, message, content):
                if self.check_permissions_chain(self.strip_prefix(cmd), message.author)[0]:
                    print("Command in channel", message.channel, "from", message.author, ":", content)
                    if len(spec) or empty:
                        argspec = Argspec(cmd, *spec, **kwargs)
                        if not self.config_get('use_shlex'):
                            delim = delimiter
                        elif delimiter is not None and delimiter not in message.content:
                            delim = None
                        elif self.config_get('disable_delimiters'):
                            print("Warning: Ignoring delimiter")
                            delim = None
                        else:
                            delim = delimiter
                        result, content = argspec(*content[1:], delimiter=delim)
                        if not result:
                            await self.send_message(
                                message.channel,
                                content
                            )
                            return
                    try:
                        await func(self, message, content)
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
                         if isinstance(message.channel, discord.PrivateChannel) and
                         self.primary_server is None
                         else ""
                        ) +
                        "To check your permissions, use the `$!permissions` command"
                    )
            for cmd in [command] + aliases:
                if not cmd.startswith(self.command_prefix):
                    cmd = self.command_prefix + cmd
                on_cmd = self.subscribe(cmd)(on_cmd)
                self.commands[cmd] = func.__doc__
            return on_cmd

        return wrapper

    def add_task(self, interval): #decorator. Sets the decorated function to run on the specified interval
        """
        Decorator. Sets the decorated function to run on the specified interval.
        Arguments:
        interval : The interval in which to run the function, in seconds

        The decorated function must be a coroutine (async def) and take only the bot object as an argument
        """
        def wrapper(func):
            taskname = 'task:'+func.__name__
            if taskname in self.tasks:
                raise NameError("This task already exists! Change the name of the task function")
            self.tasks[taskname] = (interval, func.__qualname__)

            @self.subscribe(taskname)
            async def run_task(self, task):
                await func(self)
                if 'tasks' not in self.update_times:
                    self.update_times['tasks'] = {}
                self.update_times['tasks'][taskname] = time.time()
                save_db(self.update_times, 'tasks.json')


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
            create_task(listener(self, event, *args, **kwargs), loop=self.loop)
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
            if key in obj:
                obj = obj[key]
            else:
                return default
        return obj

    async def on_ready(self):
        """
        Coroutine. Default event handler for the bot going online.
        Handles core functions such as checking primary_server configuration and
        parsing the permissions file into a set of rules.
        Do not override. Instead, use @bot.subsribe('ready') to add additional handling
        to this event
        """
        print("Connected to the following servers")
        if 'primary_server' in self.configuration:
            self.primary_server = discord.utils.get(
                self.servers,
                id=str(self.configuration['primary_server'])
            )
            if self.primary_server is None:
                sys.exit("Primary server set, but no matching server was found")
            else:
                print("Validated primary server:", self.primary_server.name)
        else:
            print("Warning: No primary server set in configuration. Role permissions cannot be validated in PM's")
        first = True
        for server in list(self.servers):
            print(server.name, server.id)
            await self.on_server_join(server)
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
        self.update_times = load_db('tasks.json')
        taskkey = ''.join(sorted(self.tasks))
        if 'key' not in self.update_times or self.update_times['key'] != taskkey:
            print("Invalidating task time cache")
            self.update_times = {'key':taskkey, 'tasks':{}}
            save_db(self.update_times, 'tasks.json')
        else:
            print("Not invalidating cache")
        self.permissions = None
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
                    [_role for server in self.servers for _role in server.roles]
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
        self.task_worker = threading.Thread(
            target=CoreBot._run_tasks,
            args=(self,),
            daemon=True,
            name="CoreBot Background Task Thread"
        )

        self.task_worker.start()

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
        elif isinstance(interp, discord.Channel):
            interp = Interpolator(self, interp)
        elif not isinstance(interp, dict):
            raise TypeError("Cannot infer interpolation settings from an object of type "+type(interp))
        try:
            for key in interp:
                content = content.replace(key, interp[key])
        except:
            print("Interpolation Error: ", {**interp})
        for match in mention_pattern.finditer(content):
            uid = match.group(1)
            do_sub = isinstance(destination, discord.User) and destination.id != uid
            do_sub |= hasattr(destination, 'server') and self.get_user(uid, destination.server) is None
            do_sub |= hasattr(destination, 'recipients') and uid not in {user.id for user in destination.recipients}
            if do_sub:
                # have to replace the mention with a `@Username`
                user = self.get_user(uid)
                if user is not None:
                    content = content.replace(
                        match.group(0),
                        '`@%s#%s`' % (user.name, str(user.discriminator)),
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
                    last_msg = await super().send_message(
                        destination,
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
                last_msg = await super().send_message(
                    destination,
                    quote+msg+quote
                )
            except discord.errors.HTTPException as e:
                await self.trace()
        return last_msg


    def get_user(self, reference, *servers):
        """
        Gets a user object given a form of reference. Optionaly provide a subset of servers to check
        Arguments:
        reference : A string reference which can either be a user's id or a username to identify a user
        *servers : A list of servers to check. By default, this function checks the primary_server, then all others

        Checks servers for a user based on id first, then username. Returns the first match
        """
        if not len(servers):
            servers = list(self.servers)
            if self.primary_server is not None:
                servers = [self.primary_server] + servers
                #it's okay that the primary_server is duplicated
                #But at least this gives it priority
        for server in servers:
            result = server.get_member(reference)
            if result is not None:
                return result
        for server in servers:
            result = server.get_member_named(reference)
            if result is not None:
                return result

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

    def build_permissions_chain(self, user):
        """
        Used to assemble the chain of permissions rules for the given user
        Arguments:
        user : A user object

        Returns a list of permissions rules which apply to the given user, in order
        of highest to lowest priority
        """
        # Assemble the chain of permissions rules for a given user
        chain = []
        if user.id in self.permissions['users']:
            chain += self.permissions['users'][user.id]
        if self.primary_server is not None:
            user = self.primary_server.get_member(user.id)
        if hasattr(user, 'roles') and hasattr(user, 'server'):
            user_roles = set(user.roles)
            for role in user.server.role_hierarchy:
                if role in user_roles and role.id in self.permissions['roles']:
                    chain.append(self.permissions['roles'][role.id])
        return [item for item in chain] + [self.permissions['defaults']]

    def has_underscore_permissions(self, user, chain=None):
        """
        Used to check if a user has permissions to use underscore (administrator) commands.
        Arguments:
        user : A user object to check for underscore permissions
        chain : (Optional) a prebuilt permissions chain from build_permissions_chain. By default,
            the permissions chain is rebuilt
        """
        # Check the permissions chain for a user to see if they can use
        # Administrative (underscore) commands
        if chain is None:
            #build the chain, if it wasn't given as an argument
            chain = self.build_permissions_chain(user)
        for obj in chain:
            if 'underscore' in obj:
                return obj['underscore']

    def check_permissions_chain(self, cmd, user, chain=None):
        """
        Used to check if a user's permissions chain allows the use of a given command
        Arguments:
        cmd : The string command word to check. Cannot start with the command prefix (use strip_prefix)
        user : The user object to check
        chain : (Optional) a prebuilt permissions chain from build_permissions_chain. By default,
            the permissions chain is rebuilt
        """
        #Important note: cmd argument does not include the leading ! of a command
        # Permissions.yml file contains commands without prefix, and we check them
        # here without the prefix
        if chain is None:
            #build the chain, if it wasn't given as an argument
            chain = self.build_permissions_chain(user)
        for obj in chain:
            if 'allow' in obj and (cmd in obj['allow'] or '$all' in obj['allow']):
                return True, obj['_grant']
            elif 'deny' in obj and (cmd in obj['deny'] or '$all' in obj['deny']):
                return False, obj['_grant']
            elif cmd.startswith('_') and 'underscore' in obj:
                return obj['underscore'], obj['_grant']
        return (not cmd.startswith('_'), 'by default') #default behavior

    async def on_message(self, message):
        """
        Coroutine. Default handler for incomming messages. Do not override.
        Immediately skips message handling and returns if:
        * The message was sent by this bot
        * The message was sent in a DM by a user who does not have any servers in common with this bot
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
            #User is not a member of any known server
            #silently ignore
            return
        if message.author.id in self.ignored_users:
            print("Ignoring message from", message.author,":", content)
            return
        # build the user struct and update the users object
        if self.config_get('use_shlex'):
            try:
                lex = shlex.shlex(message.content.strip(), posix=True)
                lex.whitespace_split = True
                content = list(lex)
                content[0] = content[0].lower()
            except:
                return
        else:
            try:
                content = message.content.strip().split()
                content[0] = content[0].lower()
            except:
                return
        if content[0] in self.commands: #if the first argument is a command
            # dispatch command event
            print("Dispatching command")
            self.dispatch(content[0], message, content)
        else:
            # If this was not a command, check if any of the special functions
            # would like to run on this message
            for event in self.special_order:
                if self.special[event](self, message):
                    print("Running special", event)
                    self.dispatch(event, message, content)
                    break

    def _run_tasks(self):
        """
        Background worker to run tasks. Every 60 seconds, while the bot is online,
        check if it is time for any registered tasks to run
        """
        while True:
            time.sleep(60)
            # Check if it is time to run any tasks
            #
            current = time.time()
            ran_task = False
            for task, (interval, qualname) in self.tasks.items():
                last = 0
                if 'tasks' in self.update_times and task in self.update_times['tasks']:
                    last = self.update_times['tasks'][task]
                if current - last > interval:
                    print("Running task", task, '(', qualname, ')')
                    self.dispatch(task)

    async def on_server_join(self, server):
        """
        Coroutine. Handler for joining servers. Do not override.
        If you wish to add handling for joining servers use @bot.subscribe('server_join')

        If a primary server is defined and this is not the primary server, leave it.
        Otherwise, print a warning that a primary server is not defined
        """
        if self.primary_server is not None and self.primary_server != server:
            try:
                await self.send_message(
                    discord.utils.get(
                        server.channels,
                        name='general',
                        type=discord.ChannelType.text
                    ),
                    "Unfortunately, this instance of $NAME is not configured"
                    " to run on multiple servers. Please contact the owner"
                    " of this instance, or run your own instance of $NAME."
                    " Goodbye!"
                )
            except:
                pass
            await self.leave_server(server)
        elif len(self.servers) > 1:
            print("Warning: Joining to multiple servers is not supported behavior")

def EnableUtils(bot): #prolly move to it's own bot
    """
    A sub-bot to enable utility functions
    """
    #add some core commands
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.reserve_channel('dev') # Reserve a reference for a development channel

    @bot.add_command('_task', Arg('task', type='extra', help='task_name'))
    async def cmd_task(self, message, args):
        """
        `$!_task <task name>` : Manually runs the named task
        """
        key = ' '.join([args.task] + args.extra)
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

    @bot.add_command('_nt', empty=True)
    async def cmd_nt(self, message, content):
        await self.send_message(
            message.channel,
            '%d events have been dispatched' % self.nt
        )

    @bot.add_command('output-dev', empty=True)
    async def cmd_dev(self, message, content):
        """
        `$!output-dev` : Any messages that would always go to general will go to testing grounds
        """
        self._channel_references = {k:v for k,v in self.channel_references.items()}
        self.channel_references = {k:self.fetch_channel('dev') for k in self.channel_references}
        await self.send_message(
            self.fetch_channel('dev'),
            "Development mode enabled. I will send any messages which are not replies to $CHANNEL",
        )

    @bot.add_command('output-prod', empty=True)
    async def cmd_prod(self, message, content):
        """
        `$!output-prod` : Restores normal message routing
        """
        self.channel_references = {k:v for k,v in self._channel_references.items()}
        await self.send_message(
            self.fetch_channel('dev'),
            "Production mode enabled. All messages will be directed normally"
        )

    #Not using argparse API as it does not preserve whitespace
    @bot.add_command('_announce')
    async def cmd_announce(self, message, content):
        """
        `$!_announce <message>` : Forces me to say the given message in general.
        Example: `$!_announce I am really cool`
        """
        await self.send_message(
            self.fetch_channel('general'),
            message.content.strip().replace(self.command_prefix+'_announce', '', 1)
        )

    @bot.add_command('permissions', empty=True)
    async def cmd_perms(self, message, content):
        """
        `$!permissions` : Gets a list of commands you have permissions to use
        """
        chain = self.build_permissions_chain(message.author)
        cmds = []
        for command in sorted(self.commands):
            (allow, rule) = self.check_permissions_chain(self.strip_prefix(command), message.author, chain)
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
        if isinstance(message.channel, discord.PrivateChannel) and self.primary_server is None:
            body.append(
                "You may have additional permissions granted to you by a role"
                " but I cannot check those within a private chat. Try the"
                " `$!permissions` command in a server channel"
            )
        await self.send_message(
            message.author,
            '\n'.join(body)
        )

    @bot.add_command('ignore', Arg('user', type=UserType(bot, by_nick=False), help="Username or ID"))
    async def cmd_ignore(self, message, args):
        """
        `$!ignore <user id or user#tag>` : Ignore all commands by the given user
        until the next time I'm restarted
        Example: `$!ignore Username#1234` Ignores all commands from Username#1234
        """
        uid = args.user.id
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
        for server in self.servers:
            user = server.get_member(uid)
            if user is not None:
                general = self.fetch_channel('general')
                if general.server != server:
                    general = discord.utils.get(
                        server.channels,
                        name='general',
                        type=discord.ChannelType.text
                    )
                if self.config_get('ignore_role') != None:
                    blacklist_role = self.config_get('ignore_role')
                    for role in server.roles:
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
            args.user,
            "I have been asked to ignore you by %s. Please contact them"
            " to petition this decision." % (str(message.author))
        )

    @bot.add_command('pardon', Arg('user', type=UserType(bot, by_nick=False), help="Username or ID"))
    async def cmd_pardon(self, message, args):
        """
        `$!pardon <user id or user#tag>` : Pardons the user and allows them to issue
        commands again.
        Example: `$!pardon Username#1234` pardons Username#1234
        """
        uid = args.user.id
        if uid not in self.ignored_users:
            await self.send_message(
                message.channel,
                "This user is not currently ignored"
            )
            return
        self.ignored_users.remove(uid)
        save_db(
            list(self.ignored_users),
            'ignores.json'
        )
        for server in self.servers:
            user = server.get_member(uid)
            if user is not None:
                general = self.fetch_channel('general')
                if general.server != server:
                    general = discord.utils.get(
                        server.channels,
                        name='general',
                        type=discord.ChannelType.text
                    )
                if self.config_get('ignore_role') != None:
                    blacklist_role = self.config_get('ignore_role')
                    for role in server.roles:
                        if role.id == blacklist_role or role.name == blacklist_role:
                            await self.remove_roles(
                                user,
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
            args.user,
            "You have been pardoned by %s. I will resume responding to "
            "your commands." % (str(message.author))
        )

    @bot.add_command('idof', Arg('query', type='extra', help="Entity to search for"))
    async def cmd_idof(self, message, args):
        """
        `$!idof <entity>` : Gets a list of all known entities by that name
        Example: `$!idof general` would list all users, channels, and roles with that name
        """
        servers = [message.server] if message.server is not None else self.servers
        result = []
        query = ' '.join([args.query] + args.extra).lower()
        for server in servers:
            first = True
            if query in server.name.lower():
                if first:
                    first = False
                    result.append('From server `%s`' % server.name)
                result.append('Server `%s` : %s' % (server.name, server.id))
            for channel in server.channels:
                if query in channel.name.lower():
                    if first:
                        first = False
                        result.append('From server `%s`' % server.name)
                    result.append('Channel `%s` : %s' % (channel.name, channel.id))
            for role in server.roles:
                if query in role.name.lower():
                    if first:
                        first = False
                        result.append('From server `%s`' % server.name)
                    result.append('Role `%s` : %s' % (role.name, role.id))
            for member in server.members:
                if member.nick is not None and query in member.nick.lower():
                    if first:
                        first = False
                        result.append('From server `%s`' % server.name)
                    result.append('Member `%s` aka `%s` : %s' % (
                        str(member),
                        member.nick,
                        member.id
                    ))
                elif query in member.name.lower():
                    if first:
                        first = False
                        result.append('From server `%s`' % server.name)
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
    async def cmd_timer(self, message, args):
        """
        `$!timer <minutes>` : Sets a timer to run for the specified number of minutes
        """
        await self.send_message(
            message.channel,
            "Okay, I'll remind you in %d minute%s" % (
                args.minutes,
                '' if args.minutes == 1 else 's'
            )
        )
        await asyncio.sleep(60 * args.minutes)
        await self.send_message(
            message.channel,
            message.author.mention + " Your %d minute timer is up!" % args.minutes
        )

    return bot
