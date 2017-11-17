import json
import sys

def load_db(filename, default=None):
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
