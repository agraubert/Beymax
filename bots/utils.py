import json

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
