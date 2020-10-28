import argparse
from collections import namedtuple
from datetime import datetime
import re

mention_pattern = re.compile(r'<@\D?(\d+)>')

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

class GuildType(EType):
    def __call__(self, arg):
        guild = self.search_iter(self.client.guilds, arg)
        if guild is not None:
            return guild
        raise argparse.ArgumentTypeError(
            "No guild matching `%s` by %s" % (
                arg,
                ljoin(self.fields)
            )
        )

class GuildComponentType(EType):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def guilds(self):
        if self.client.primary_guild is not None:
            yield self.client.primary_guild
        yield from self.client.guilds

class RoleType(GuildComponentType):
    def __call__(self, arg):
        role = self.search_iter(
            [role for guild in self.guilds() for role in guild.roles],
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

class ChannelType(GuildComponentType):
    def __call__(self, arg):
        channel = self.search_iter(
            [channel for guild in self.guilds() for channel in guild.channels],
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

class UserType(GuildComponentType):
    def __init__(self, client, by_name=True, by_id=True, by_nick=True, nullable=False, mentions=True):
        super().__init__(client, by_name=by_name, by_id=by_id, nullable=nullable)
        self.nick = by_nick
        self.mentions = mentions
        if self.nick:
            self.fields.append('nick')

    def __call__(self, arg):
        if self.mentions:
            result = mention_pattern.match(arg)
            if result:
                arg = result.group(1)
                print("Matched Mention")
        member = self.search_iter(
            [member for guild in self.guilds() for member in guild.members],
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
        return datetime.strptime(arg, '%m/%d/%Y')
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


# FIXME: Extra is useful, but adding it as separate arguments seems dumb
# Everywhere I use extra, i'm concatenating arg + extra
def Arg(*args, remainder=False, **kwargs):
    """
    Takes arguments and keyword arguments exactly like the argparse.ArgumentParser.add_argument
    method with two exceptions:

    * Setting remainder to True, sets the value of the 'nargs' keyword argument to be
    argparse.REMAINDER. This is simply a convenience to avoid having to import argparse
    * If the 'type' keyword argument is set to 'extra', this argument will be defined
    exactly as expected (given the arguments) except that 'type' is set to the default str.
    Additionally, another argument will be added with the name 'extra', 'nargs' set to
    argparse.REMAINDER, and the 'metavar' will be set to the empty string. This attains
    a similar result to setting 'nargs' to '+', but allows special handling of the first
    word

    Note: The first argument is the name of this argument, and will specify the attribute
    on the Namespace where the argument value can be obtained
    """
    if remainder:
        kwargs['nargs'] = argparse.REMAINDER
    if 'metavar' in kwargs and kwargs['metavar'] != '':
        kwargs['metavar'] = '<%s>' % kwargs['metavar']
    elif 'metavar' not in kwargs:
        kwargs['metavar'] = '<%s>' % args[0]
    return Argtuple(args, kwargs)

class Argspec(argparse.ArgumentParser):
    def __init__(self, name, *args, allow_redirection=True, **kwargs):
        super().__init__(name, add_help=False, **kwargs)
        for arg in args:
            if 'type' in arg.kwargs and arg.kwargs['type'] == 'extra':
                self.add_argument(
                    *arg.args,
                    **{k:v for k,v in arg.kwargs.items() if k != 'type'}
                )
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
            args = [
                arg for arg in ' '.join(args).split(delimiter)
                if len(arg)
            ]
        try:
            return (True, super().parse_args(args))
        except PrebuiltException as e:
            if delimiter is not None:
                e.message += (
                    '\nPlease note: This command uses `%s` to separate arguments'
                    ' instead of regular spaces' % delimiter
                )
            return (False, e.message)
