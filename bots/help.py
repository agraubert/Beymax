from .core import CoreBot
from .utils import sanitize, VolatileDBView
import discord
import asyncio
import sys
import math

def trim(docstring):
    if not docstring:
        return ''
    # Convert tabs to spaces (following the normal Python rules)
    # and split into a list of lines:
    lines = docstring.expandtabs().splitlines()
    # Determine minimum indentation (first line doesn't count):
    indent = sys.maxsize
    for line in lines[1:]:
        stripped = line.lstrip()
        if stripped:
            indent = min(indent, len(line) - len(stripped))
    # Remove indentation (first line is special):
    trimmed = [lines[0].strip()]
    if indent < sys.maxsize:
        for line in lines[1:]:
            trimmed.append(line[indent:].rstrip())
    # Strip off trailing and leading blank lines:
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    while trimmed and not trimmed[0]:
        trimmed.pop(0)
    # Return a single string:
    return '\n'.join(trimmed)

def EnableHelp(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.help_sessions = {}

    @bot.add_special(lambda b,m:b.config_get('dm_help') and isinstance(m.channel, (discord.DMChannel, discord.GroupChannel)) and not m.content.startswith(b.command_prefix))
    async def start_help(self, message, content):
        """
        Small condition to trigger a help session if the user DMs beymax
        """
        async with VolatileDBView('help', help=set()) as db:
            if message.author.id in db['help']:
                return # already being helped
            self.dispatch('{}ouch'.format(self.command_prefix), message)

    @bot.add_command('ouch')
    async def cmd_help(self, message):
        """`$!ouch` : Asks for my help"""
        # await self.send_message(
        #     message.author,
        #     "Hello! I am Beymax, your personal ~~healthcare~~ **server** companion.\n"+
        #     "It's my job to make sure you have a good time and understand the various tools at your disposal in this server\n"+
        #     "You can ask me for help with the bots, or the channels, but\n"+
        #     "if you're not sure what sort of things I can do, just say `help`\n"+
        #     "What seems to be the problem?"
        # )
        async with VolatileDBView('help', help=set()) as db:
            if message.author.id in db['help']:
                return # already being helped
            db['help'].add(message.author.id)
        try:
            await self.send_message(
                message.author,
                "Hello! I am $NAME, your personal ~~healthcare~~ **server** companion.\n"
                "Simply type the name of a command (without $!) to get help with that command.\n"
                "If you'd like a list of commands that you can use, type `all`.\n"
                "What can I help you with?"
            )
            chain = self.permissions.query(message.author)
            commands = {
                self.strip_prefix(cmd):(
                    "`{}`\n{}Additional details:\n{}".format(
                        self.commands[cmd]['argspec'].format_help(),
                        '**NOTE:** This command uses `{}` to separate arguments instead of spaces\n'.format(
                            self.commands[cmd]['delimiter']
                        ) if self.commands[cmd]['delimiter'] is not None else '',
                        trim(self.commands[cmd]['docstring'])
                    )
                )
                for cmd in self.commands
                if self.permissions.query(message.author, self.strip_prefix(cmd), _chain=chain)
            }
            response = await self.wait_for(
                'message',
                check=lambda m: m.author == message.author and m.channel == message.author.dm_channel and not m.content.startswith(self.command_prefix)
            )
            if response.content.lower() in commands:
                await self.send_message(
                    message.author,
                    "Here's the help text for that command:\n" + commands[response.content.lower()]
                )
            elif response.content.lower() == 'all':
                self.dispatch('{}permissions'.format(self.command_prefix), message)
            else:
                await self.send_message(
                    message.channel,
                    "That command doesn't exist or you don't have permissions to use it"
                )
        finally:
            async with VolatileDBView('help', help=set()) as db:
                # Help is concluded
                db['help'].remove(message.author.id)

        # self.help_sessions[message.author.id] = HelpSession(self, message.author)

    # def should_help(self, message):
    #     return isinstance(message.channel, discord.PrivateChannel) and message.author.id in self.help_sessions
    #
    # @bot.add_special(should_help)
    # async def help_digest(self, message, content):
    #     await self.help_sessions[message.author.id].digest(message.content)
    #     self.help_sessions = {user:session for user,session in self.help_sessions.items() if session.active}

    # def confused(self, message):
    #     return isinstance(message.channel, discord.PrivateChannel) and message.author.id not in self.help_sessions
    #
    # @bot.add_special(confused)
    # async def suggest_help(self, message, content):
    #     await self.send_message(
    #         message.channel,
    #         "I can't tell if you're asking for my help or not. If you would like"
    #         " to start a help session, say `!ouch`"
    #     )

    return bot
