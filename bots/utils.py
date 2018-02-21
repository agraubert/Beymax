import json
import sys
import asyncio
import warnings

db_lock = asyncio.Lock()
locks = {}

class Database(dict):
    def __init__(self, filename, default=None):
        super().__init__(self)
        if default is not none and not isinstance(default, dict):
            raise TypeError("Cannot use a Database object on non-dictionary type")
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
                self.update(json.load(reader))
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
        locks[self.filename].release()

class ListDatabase(list):
    def __init__(self, filename, default=None):
        super().__init__(self)
        if default is not none and not isinstance(default, list):
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
                self += json.load(reader)
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
        warnings.DeprecationWarning,
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

def sanitize(string, illegal, replacement=''):
    for char in illegal:
        string = string.replace(char, replacement)
    return string

def getname(user):
    if 'nick' in dir(user) and type(user.nick) is str and len(user.nick):
        return user.nick
    return user.name

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
