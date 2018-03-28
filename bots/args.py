import argparse
from collections import namedtuple

#Syntax:
# spec = Argspec(
#     '!command',
#     Arg(
#         'arg1',
#         type=str,
#         help="Other Argparse Args"
#     ),
#     Arg(
#         'foo',
#         help='bar'
#     ),
#     #Note: Don't use optionals unless you expect users to use --flags in commands
#     #Use positionals with Nargs
#     add_help=False
# )
#
# result, args = spec(content[1:])
# if not result:
#     await self.send_message(
#         channel,
#         spec.fail(args)
#     )
#     return
# # otherwise, use args as normal

# standard types:
# (syntax) Type(client, *args, **kwargs)
# ServerType, RoleType, ChannelType, UserType
# Types search all servers and channels by names, ids, and nicks (for users)

def ljoin(args, op='or'):
    output = ', '.join(args[:-1])
    if len(args) > 2:
        output += ','
    if len(args) > 1:
        output += ' %s ' % op
    return output + args[-1]

class EType(object):
    def __init__(self, client, by_name=True, by_id=True):
        self.client = client
        self.name = by_name
        self.id = by_id
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
    def __init__(self, client, by_name=True, by_id=True, by_nick=True):
        super().__init__(client, by_name=by_name, by_id=by_id)
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

class PrebuiltException(Exception):
    def __init__(self, message):
        self.message = message

Argtuple = namedtuple('Arg', ['args', 'kwargs'])

def Arg(*args, remainder=False, **kwargs):
    if remainder:
        kwargs['nargs'] = argparse.REMAINDER
    return Argtuple(args, kwargs)

class Argspec(argparse.ArgumentParser):
    def __init__(self, name, *args, **kwargs):
        super().__init__(name, add_help=False, **kwargs)
        for arg in args:
            self.add_argument(*arg.args, **arg.kwargs)

    def _parse_known_args(self, arg_strings, namespace):
        try:
            return super()._parse_known_args(arg_strings, namespace)
        except argparse.ArgumentError as error:
            raise PrebuiltException(
                '{usage}\nArgument {arg}{help}\n{message}'.format(
                    usage=self.format_usage(),
                    arg=error.argument_name,
                    help=': '+error.args[0].help if error.args[0].help is not None else '',
                    message=error.message
                )
            )

    def error(self, message):
        raise PrebuiltException(
            self.format_usage()+"\n"+message
        )

    def __call__(self, *args, delimiter=None):
        if delimiter is not None:
            args = ' '.join(args).split(delimiter)
        try:
            return (True, super().parse_args(args))
        except PrebuiltException as e:
            return (False, e.message)
