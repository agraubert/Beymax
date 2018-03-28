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
