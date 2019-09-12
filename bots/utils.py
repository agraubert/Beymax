import json
import sys
import asyncio
import warnings
import traceback

db_lock = asyncio.Lock()
locks = {}

def parse_id_keys(obj):
    if isinstance(obj, dict):
        try:
            return {
                int(key):parse_id_keys(val) for key,val in obj.items()
            }
        except ValueError:
            return {key:parse_id_keys(val) for key,val in obj.items()}
    elif isinstance(obj, list):
        return [parse_id_keys(elem) for elem in obj]
    return obj

class Database(dict):
    def __init__(self, filename, default=None):
        super().__init__(self)
        if default is not None and not isinstance(default, dict):
            raise TypeError("Cannot use a Database object on non-dictionary type")
        self.filename = filename
        self.default=default

    async def __aenter__(self):
        global db_lock
        global locks
        # print("A database has been acquired:", self.filename)
        async with db_lock:
            if self.filename not in locks:
                locks[self.filename] = asyncio.Lock()
        await locks[self.filename].acquire()
        try:
            with open(self.filename) as reader:
                self.update(parse_id_keys(json.load(reader)))
        except FileNotFoundError:
            self.update({} if self.default is None else self.default)
        return self

    def save(self):
        with open(self.filename, 'w') as writer:
            return json.dump(self, writer)

    async def save_to(self, filename):
        async with Database(filename) as tmp:
            for k in list(tmp):
                del tmp[k]
            tmp.update(self)
            tmp.save()

    async def __aexit__(self, *args):
        global locks
        # print("A database has been released:", self.filename)
        locks[self.filename].release()

class ListDatabase(list):
    def __init__(self, filename, default=None):
        super().__init__(self)
        if default is not None and not isinstance(default, list):
            raise TypeError("Cannot use a ListDatabase object on non-list type")
        self.filename = filename
        self.default=default

    async def __aenter__(self):
        global db_lock
        global locks
        async with db_lock:
            if self.filename not in locks:
                locks[self.filename] = asyncio.Lock()
        await locks[self.filename].acquire()
        try:
            with open(self.filename) as reader:
                self += parse_id_keys(json.load(reader))
        except FileNotFoundError:
            self += ([] if self.default is None else self.default)
        return self

    def save(self):
        with open(self.filename, 'w') as writer:
            return json.dump(self, writer)

    async def save_to(self, filename):
        async with ListDatabase(filename) as tmp:
            while len(tmp):
                tmp.pop()
            tmp += self
            tmp.save()

    def update(self, data):
        while len(self):
            self.pop()
        self += [item for item in data]

    async def __aexit__(self, *args):
        global locks
        locks[self.filename].release()

def load_db(filename, default=None):
    warnings.warn(
        "load_db is deprecated as it is not async safe",
        DeprecationWarning,
        2
    )
    try:
        with open(filename) as reader:
            return json.load(reader)
    except FileNotFoundError:
        return {} if default is None else default

def save_db(data, filename):
    with open(filename, 'w') as writer:
        return json.dump(data, writer)

class Interpolator(dict):
    def __init__(self, bot, channel):
        NAME = bot.config_get(
            'name',
            default=bot.user.name
        )
        NICK = (
            bot.get_user(bot.user.id, channel.guild)
            if hasattr(channel, 'server')
            else (
                bot.get_user(bot.user.id)
                if bot.primary_server is not None
                else None
            )
        )
        if NICK is not None:
            NICK = getname(NICK)
        if NICK is None:
            NICK = NAME
        super().__init__(**{
            '$NAME': NAME,
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

def validate_permissions(obj, is_default=False):
    if is_default:
        if 'role' in obj or 'users' in obj:
            sys.exit("role and users cannot be set on default permissions")
    else:
        if not (('role' in obj) ^ ('users' in obj)):
            sys.exit("role or users must be set on each permissions object")
    if not ('allow' in obj or 'deny' in obj  or 'underscore' in obj):
        sys.exit("Permissions object must set some permission (allow, deny, or underscore)")
    return
