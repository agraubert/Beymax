import argparse
from collections import namedtuple
from datetime import datetime
import re

def ljoin(args, op='or'):
    output = ', '.join(args[:-1])
    if len(args) > 2:
        output += ','
    if len(args) > 1:
        output += ' %s ' % op
    return output + args[-1]

class EType(object):
    def __init__(self, client, by_name=True, by_id=True, nullable=False):
        self.client = client
        self.name = by_name
        self.id = by_id
        self.null = nullable
        self.fields = []
        if self.id:
            self.fields.append('id')
        if self.name:
            self.fields.append('name')

    def search_iter(self, iterable, arg):
        for field in self.fields:
            for item in iterable:
                if hasattr(item, field) and getattr(item, field) == arg:
                    return item
        if self.null:
            return False

class ServerType(EType):
    def __call__(self, arg):
        server = self.search_iter(self.client.servers, arg)
        if server is not None:
            return server
        raise argparse.ArgumentTypeError(
            "No server matching `%s` by %s" % (
                arg,
                ljoin(self.fields)
            )
        )

class ServerComponentType(EType):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def servers(self):
        if self.client.primary_server is not None:
            yield self.client.primary_server
        yield from self.client.servers

class RoleType(ServerComponentType):
    def __call__(self, arg):
        role = self.search_iter(
            [role for server in self.servers() for role in server.roles],
            arg
        )
        if role is not None:
            return role
        raise argparse.ArgumentTypeError(
            "No role matching `%s` by %s" % (
                arg,
                ljoin(self.fields)
            )
        )

class ChannelType(ServerComponentType):
    def __call__(self, arg):
        channel = self.search_iter(
            [channel for server in self.servers() for channel in server.channels],
            arg
        )
        if channel is not None:
            return channel
        raise argparse.ArgumentTypeError(
            "No channel matching `%s` by %s" % (
                arg,
                ljoin(self.fields)
            )
        )

class UserType(ServerComponentType):
    def __init__(self, client, by_name=True, by_id=True, by_nick=True, nullable=False):
        super().__init__(client, by_name=by_name, by_id=by_id, nullable=nullable)
        self.nick = by_nick
        if self.nick:
            self.fields.append('nick')

    def __call__(self, arg):
        member = self.search_iter(
            [member for server in self.servers() for member in server.members],
            arg
        )
        if member is not None:
            return member
        raise argparse.ArgumentTypeError(
            "No user matching `%s` by %s" % (
                arg,
                ljoin(self.fields)
            )
        )

def DateType(arg):
    try:
        return datetime.strptime(arg, '%d/%m/%Y')
    except:
        raise argparse.ArgumentTypeError('`%s` not in MM/DD/YYYY format' % arg)

def DollarType(arg):
    if arg[0] == '$':
        arg = arg[1:]
    try:
        return float(arg)
    except:
        pass
    raise argparse.ArgumentTypeError('`%s` not in $0.00 format' % arg)

class PrebuiltException(Exception):
    def __init__(self, message):
        self.message = message

Argtuple = namedtuple('Arg', ['args', 'kwargs'])

def Arg(*args, remainder=False, **kwargs):
    if remainder:
        kwargs['nargs'] = argparse.REMAINDER
    if 'metavar' in kwargs and kwargs['metavar'] != '':
        kwargs['metavar'] = '<%s>' % kwargs['metavar']
    elif 'metavar' not in kwargs:
        kwargs['metavar'] = '<%s>' % args[0]
    return Argtuple(args, kwargs)

class Argspec(argparse.ArgumentParser):
    def __init__(self, name, *args, **kwargs):
        super().__init__(name, add_help=False, **kwargs)
        for arg in args:
            if 'type' in arg.kwargs and arg.kwargs['type'] == 'extra':
                del arg.kwargs['type']
                self.add_argument(*arg.args, **arg.kwargs)
                self.add_argument(
                    'extra',
                    nargs=argparse.REMAINDER,
                    metavar=''
                )
            else:
                self.add_argument(*arg.args, **arg.kwargs)

    def _parse_known_args(self, arg_strings, namespace):
        try:
            return super()._parse_known_args(arg_strings, namespace)
        except argparse.ArgumentError as error:
            raise PrebuiltException(
                '{usage}`\nArgument **{arg}**{help}\n{message}'.format(
                    usage=self.format_usage().replace('usage: ', 'usage: `'),
                    arg=re.sub(r'[<>]','',error.argument_name),
                    help=': '+error.args[0].help if error.args[0].help is not None else '',
                    message=error.message
                )
            )

    def error(self, message):
        raise PrebuiltException(
            self.format_usage().replace('usage: ', 'usage: `')+"`\n"+re.sub(r'[<>]','',message)
        )

    def __call__(self, *args, delimiter=None):
        if delimiter is not None:
            args = ' '.join(args).split(delimiter)
        try:
            return (True, super().parse_args(args))
        except PrebuiltException as e:
            if delimiter is not None:
                e.message += (
                    '\nPlease note: This command uses `%s` to separate arguments'
                    ' instead of regular spaces' % delimiter
                )
            return (False, e.message)
