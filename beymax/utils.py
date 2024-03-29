import pickle
import sys
import os
import asyncio
import warnings
import traceback
import discord
import json

DATABASE = {
    'lock': asyncio.Lock(),
    'scope_locks': {},
    'data': None
}

TIMESTAMP_FORMAT = "%m/%d/%Y - %H:%M:%S"

# Move this to the database provider settings when that change is made
DB_PATH = os.environ.get('BEYMAX_FIXME_DB_PKL_PATH', 'db.pkl')

# def parse_id_keys(obj):
#     if isinstance(obj, dict):
#         try:
#             return {
#                 int(key):parse_id_keys(val) for key,val in obj.items()
#             }
#         except ValueError:
#             return {key:parse_id_keys(val) for key,val in obj.items()}
#     elif isinstance(obj, list):
#         return [parse_id_keys(elem) for elem in obj]
#     return obj

def keycap_emoji(num):
    if num < 0 or num > 10:
        raise ValueError("Only the range [0-10] is supported")
    if num == 10:
        return u"\U0001F51F"
    return "{}\N{COMBINING ENCLOSING KEYCAP}".format(num)

class Defaultable(object):
    """
    Useful for defining function defaults with mutable objects,
    while disconnecting the default from the underlying
    """
    pass

class FrozenList(list):
    def __init__(self, scope, data):
        super().__init__([
            FrozenDict(scope, value) if isinstance(value, dict) else (
                FrozenList(scope, value) if isinstance(value, list) else value
            )
            for value in data
        ])
        self._scope = scope

    def __setitem__(self, idx, value):
        raise TypeError("Read-Only access to this scope: {}".format(self._scope))

class FrozenDict(dict):
    def __init__(self, scope, data):
        super().__init__({
            key: FrozenDict(scope, value) if isinstance(value, dict) else (
                FrozenList(scope, value) if isinstance(value, list) else value
            )
            for key, value in data.items()
        })
        self._scope = scope

    def __setitem__(self, key, value):
        raise TypeError("Read-Only access to this scope: {}".format(self._scope))

class DBView(object):
    """
    A view to the centralized database file.

    Allows read-access to full database. Write-access is protected through
    asyncronous context management
    """

    @staticmethod
    def serializable(value):
        if isinstance(value, FrozenDict):
            return {
                k: DBView.serializable(v) for k,v in value.items()
            }
        elif isinstance(value, FrozenList):
            return [
                DBView.serializable(v) for v in value
            ]
        elif isinstance(value, DBView):
            return {
                scope: DBView.serializable(value[scope]) for scope in iter(value)
            }
        elif isinstance(value, set):
            return "(set) {{{}}}".format(
                ', '.join(json.dumps(DBView.serializable(item)) for item in value)
            )
        try:
            json.dumps(value)
            return value
        except TypeError:
            return repr(value)

    @staticmethod
    def readonly_view(*scopes, read_persistent=False, **defaults):
        """
        Used for accessing a partial view of the database in read-only mode.
        Useful for database checks outside of coroutines.
        Does not guarantee consistency
        """
        if read_persistent and os.path.isfile('BEYMAX_FIXME_DB_PKL_PATH') and os.path.getsize('BEYMAX_FIXME_DB_PKL_PATH') > 0:
            with open('BEYMAX_FIXME_DB_PKL_PATH', 'rb') as r:
                fallback = pickle.load(r)
        else:
            fallback = {}
        view = DBView()
        return FrozenDict(
            'root',
            {
                scope: view[scope] if scope in view else (
                    fallback[scope] if scope in fallback else
                    defaults[scope]
                )
                for scope in scopes
                if scope in view or scope in fallback or scope in defaults
            }
        )

    @staticmethod
    async def overwrite(**data):
        """
        Saves the provided data (scope:value) pairs
        without checking current value
        """
        async with DBView(*data) as db:
            for key, value in data.items():
                db[key] = value

    def __init__(self, *scopes, _add_scope_to_defaults=True, **defaults):
        self.scopes = sorted(set(scopes)) # Enforce lock ordering
        if _add_scope_to_defaults:
            self._defaults = {
                **{scope: {} for scope in scopes},
                **{k:v for k,v in defaults.items()}
            }
        else:
            self._defaults = {k:v for k,v in defaults.items()}
        self._entered = False
        self._dirty = False

    async def __aenter__(self):
        if len(self._defaults):
            # If we provided defaults, quickly update them
            async with DBView(*self._defaults, _add_scope_to_defaults=False) as db:
                for key, value in self._defaults.items():
                    if key not in db:
                        db[key] = value
        async with DATABASE['lock']:
            if DATABASE['data'] is None:
                if os.path.isfile('BEYMAX_FIXME_DB_PKL_PATH') and os.path.getsize('BEYMAX_FIXME_DB_PKL_PATH') > 0:
                    with open('BEYMAX_FIXME_DB_PKL_PATH', 'rb') as r:
                        DATABASE['data'] = pickle.load(r)
                else:
                    DATABASE['data'] = {}
            for scope in self.scopes:
                if scope not in DATABASE['scope_locks']:
                    DATABASE['scope_locks'][scope] = asyncio.Lock()
                await DATABASE['scope_locks'][scope].acquire()
            self._entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, tb):
        if self._dirty and (exc_type is not None or exc_val is not None or tb is not None):
            traceback.print_exc()
            print("Database connection exiting uncleanly. Aborting changes")
            await self.abort() # sets dirty to false so all that happens afterwards is __aexit__ releases locks
        async with DATABASE['lock']:
            self._entered = False
            if self._dirty:
                # Load current state from file
                # We should only save scopes we have access to
                # even if other scopes have changed
                # This avoids accidentally leaking changes that will later be aborted
                # by another view
                if os.path.isfile('BEYMAX_FIXME_DB_PKL_PATH') and os.path.getsize('BEYMAX_FIXME_DB_PKL_PATH') > 0:
                    with open('BEYMAX_FIXME_DB_PKL_PATH', 'rb') as r:
                        prev = pickle.load(r)
                else:
                    prev = {}
                with open('BEYMAX_FIXME_DB_PKL_PATH', 'wb') as w:
                    prev.update({
                        key: DATABASE['data'][key]
                        for key in self.scopes
                        if key in DATABASE['data']
                    })
                    pickle.dump(prev, w)
            # Release locks in reverse order
            for scope in reversed(self.scopes):
                DATABASE['scope_locks'][scope].release()

    def __getitem__(self, key):
        if key not in DATABASE['data']:
            raise KeyError(key)
        if key in self.scopes and not key in self:
            raise KeyError("Value Deleted")
        val = DATABASE['data'][key]
        if not (self._entered and key in self.scopes):
            # If we're not scoped, ensure that dicts or lists are frozen
            if isinstance(val, dict):
                return FrozenDict(key, val)
            elif isinstance(val, list):
                return FrozenList(key, val)
        # Otherwise return val because either it's a singleton object or
        # we're scoped and it's allowed to be mutable
        if self._entered and key in self.scopes and isinstance(val, (dict, list)):
            # If we're scoped and this is a mutable object, just set the state
            # to dirty
            self._dirty = True
        return val

    def __setitem__(self, key, value):
        if not (self._entered and key in self.scopes):
            raise TypeError("Scope {} is currently frozen".format(key))
        if isinstance(value, (FrozenDict, FrozenList)):
            raise TypeError("Frozen")
        self._dirty = True
        DATABASE['data'][key] = value
        # if key == 'players':
        #     import pdb; pdb.set_trace()

    async def delete_scope(self, key):
        if not (self._entered and key in self.scopes):
            raise TypeError("Scope {} is currently frozen".format(key))

        async with DATABASE['lock']:
            del DATABASE['data'][key]
            if os.path.isfile('BEYMAX_FIXME_DB_PKL_PATH') and os.path.getsize('BEYMAX_FIXME_DB_PKL_PATH') > 0:
                with open('BEYMAX_FIXME_DB_PKL_PATH', 'rb') as r:
                    prev = pickle.load(r)
            else:
                prev = {}
            with open('BEYMAX_FIXME_DB_PKL_PATH', 'wb') as w:
                del prev[key]
                pickle.dump(prev, w)
            self.scopes.remove(key)
            self._dirty = True

    def __contains__(self, key):
        return key in DATABASE['data']

    def __iter__(self):
        yield from DATABASE['data']

    def __repr__(self):
        return repr(DATABASE['data'])

    async def abort(self):
        """
        Abort any pending changes
        """
        async with DATABASE['lock']:
            self._entered = False
            if self._dirty:
                # Reload our scopes from disk
                # Remember, we have exclusive write access so we're only discarding
                # our own changes
                if os.path.isfile('BEYMAX_FIXME_DB_PKL_PATH') and os.path.getsize('BEYMAX_FIXME_DB_PKL_PATH') > 0:
                    with open('BEYMAX_FIXME_DB_PKL_PATH', 'rb') as r:
                        prev = pickle.load(r)
                else:
                    prev = {}
                for key, value in prev.items():
                    DATABASE['data'][key] = value
            self._dirty = False
            self._entered = True

class VolatileDBView(DBView):
    async def __aenter__(self):
        if len(self._defaults):
            # If we provided defaults, quickly update them (volatile)
            async with VolatileDBView(*self._defaults, _add_scope_to_defaults=False) as db:
                for key, value in self._defaults.items():
                    if key not in db:
                        db[key] = value
        async with DATABASE['lock']:
            if DATABASE['data'] is None:
                if os.path.isfile('BEYMAX_FIXME_DB_PKL_PATH') and os.path.getsize('BEYMAX_FIXME_DB_PKL_PATH') > 0:
                    with open('BEYMAX_FIXME_DB_PKL_PATH', 'rb') as r:
                        DATABASE['data'] = pickle.load(r)
                else:
                    DATABASE['data'] = {}
            for scope in self.scopes:
                if scope not in DATABASE['scope_locks']:
                    DATABASE['scope_locks'][scope] = asyncio.Lock()
                await DATABASE['scope_locks'][scope].acquire()
            self._entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, tb):
        if self._dirty and (exc_type is not None or exc_val is not None or tb is not None):
            traceback.print_exc()
            print("Database connection exiting uncleanly. Aborting changes")
            await self.abort() # sets dirty to false so all that happens afterwards is __aexit__ releases locks
        async with DATABASE['lock']:
            self._entered = False
            # Do not save changes to disk
            # Release locks in reverse order
            for scope in reversed(self.scopes):
                DATABASE['scope_locks'][scope].release()

class Interpolator(dict):
    def __init__(self, bot, channel):
        NAME = bot.config_get(
            'name',
            default=bot.user.name
        )
        NICK = (
            bot.get_user(bot.user.id, channel.guild)
            if hasattr(channel, 'guild')
            else (
                bot.get_user(bot.user.id)
                if bot.primary_guild is not None
                else None
            )
        )
        if NICK is not None:
            NICK = getname(NICK)
        if NICK is None:
            NICK = NAME
        super().__init__(**{
            '$NAME': NAME,
            '$EMOJIFY': '', # dummy
            '$MENTION': bot.user.mention,
            '$FULLNAME': '%s#%s' % ( bot.user.name, str(bot.user.discriminator)),
            '$ID': str(bot.user.id),
            '$NICK': NICK,
            '$CHANNEL': (
                channel.name if hasattr(channel, 'name') and channel.name is not None
                else (
                    ', '.join([r.name for r in channel.recipients])
                    if hasattr(channel, 'recipients')
                    else "<Unknown Channel>"
                )
            ),
            '$PREFIX': bot.command_prefix,
            '$!': bot.command_prefix
        })


def sanitize(string, illegal, replacement=''):
    for char in illegal:
        string = string.replace(char, replacement)
    return string

def getname(user):
    if user is None:
        return 'someone'
    if 'nick' in dir(user) and type(user.nick) is str and len(user.nick):
        return user.nick
    return user.name

def get_attr(obj, attr, default):
    if hasattr(obj, attr):
        return getattr(obj,attr)
    return default

def standard_intents():
    return discord.Intents(
        guilds=True,
        members=True,
        bans=True,
        emojis=True,
        integrations=False,
        webhooks=False,
        invites=False,
        voice_states=False,
        presences=False,
        messages=True,
        guild_messages=True,
        dm_messages=True,
        reactions=True,
        guild_reactions=True,
        dm_reactions=True,
        typing=False,
        guild_typing=False,
        dm_typing=False
    )
