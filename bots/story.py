from .core import CoreBot
from .utils import getname, load_db, save_db
import discord
import asyncio
import os
import subprocess
import queue
import threading
import re

more_patterns = [
    re.compile(r'\*+(MORE|more)\*+')
]

score_patterns = [
    re.compile(r'([0-9]+)/[0-9+]'),
    re.compile(r'Score:[ ]*([-]*[0-9]+)'),
    re.compile(r'([0-9]+):[0-9]+ [AaPp][Mm]')
]

clean_patterns = [
    # re.compile(r'[0-9]+/[0-9+]'),
    # re.compile(r'Score:[ ]*[-]*[0-9]+'),
    re.compile(r'Moves:[ ]*[0-9]+'),
    re.compile(r'Turns:[ ]*[0-9]+'),
    # re.compile(r'[0-9]+:[0-9]+ [AaPp][Mm]'),
    re.compile(r' [0-9]+ \.')
] + more_patterns + score_patterns

def multimatch(text, patterns):
    for pattern in patterns:
        result = pattern.search(text)
        if result:
            return result
    return False

class Player:
    def __init__(self, game):
        (self.stdinRead, self.stdinWrite) = os.pipe()
        (self.stdoutRead, self.stdoutWrite) = os.pipe()
        self.buffer = queue.Queue()
        self.remainder = b''
        self.score = 0
        self.proc = subprocess.Popen(
            'dfrotz games/%s.z5' % game,
            universal_newlines=False,
            shell=True,
            stdout=self.stdoutWrite,
            stdin=self.stdinRead
        )
        self._reader = threading.Thread(
            target=Player.reader,
            args=(self,),
            daemon=True,
        )
        self._reader.start()

    def write(self, text):
        if not text.endswith('\n'):
            text+='\n'
        os.write(self.stdinWrite, text.encode())

    def reader(self):
        while True:
            self.buffer.put(self.readline())

    def readline(self):
        intake = self.remainder
        while b'\n' not in intake:
            intake += os.read(self.stdoutRead, 64)
        lines = intake.split(b'\n')
        self.remainder = b'\n'.join(lines[1:])
        return lines[0].decode().rstrip()

    def readchunk(self, clean=True):
        content = [self.buffer.get()]
        try:
            while not self.buffer.empty():
                content.append(self.buffer.get(timeout=0.5))
        except queue.Empty:
            pass

        # clean metadata
        if multimatch(content[-1], more_patterns):
            self.write('\n')
            content += self.readchunk(False)

        if clean:
            for i in range(len(content)):
                line = content[i]
                result = multimatch(line, score_patterns)
                if result:
                    self.score = int(result.group(1))
                result = multimatch(line, clean_patterns)
                while result:
                    line = result.re.sub('', line)
                    result = multimatch(line, clean_patterns)
                content[i] = line
        return '\n'.join(line for line in content if len(line.rstrip()))

    def quit(self):
        self.write('quit')
        self.write('y')
        try:
            self.proc.wait(1)
        except:
            self.proc.kill()
        os.close(self.stdinRead)
        os.close(self.stdinWrite)
        os.close(self.stdoutRead)
        os.close(self.stdoutWrite)


def EnableStory(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command('!_stories')
    def cmd_story(self, message, content):
        games = [
            f[:-3] for f in os.listdir('games') if f.endswith('.z5')
        ]
        await self.send_message(
            message.channel,
            '\n'.join(
                "Here are the stories thar are available:",
                *games
            )
        )

    def checker(self, message):
        state = load_db('game.json', {'user':'~<IDLE>'})
        return state['user'] != '~<IDLE>'

    @bot.add_special(checker)
    def state_router(self, message, content):
        # Routes messages depending on the game state
        state = load_db('game.json', {'user':'~<IDLE>'})
        if state['user'] == message.author.id:
            content = message.content.strip().lower()
            if content == '$':
                content = '\n'
                self.player.write('\n')
            elif content == '$quit':
                self.player.quit()
                await self.send_message(
                    message.channel,
                    'You have quit your game.'
                )
                state['user'] = '~<IDLE>'
                del self.player
                save_db(state, 'game.json')
            else:
                self.player.write(content)
                await self.send_message(
                    message.channel,
                    self.player.readchunk()
                )
        else:
            await self.send_message(
                message.author,
                "Please refrain from posting messages in the story channel"
                " while someone else is playing"
            )

    @bod.add_command('!_start')
    def cmd_start(self, message, content):
        state = load_db('game.json', {'user':'~<IDLE>'})
        if state['user'] != '~<IDLE>':
            games = {
                f[:-3] for f in os.listdir('games') if f.endswith('.z5')
            }
            if content[1] in games:
                state['user'] = message.author.id
                save_db(state, 'game.json')
                self.player = Player(content[1])
                # in future:
                # 1) use a reserved channel so other users can watch
                # 2) Post to general that a game is starting
                # 3) Mention in game channel to get user's attention
                # 4) Lock permissions in game channel to prevent non-players from posting messages
                await self.send_message(
                    message.channel,
                    self.player.readchunk()
                )
            else:
                await self.send_message(
                    message.channel,
                    "That is not a valid game"
                )
        else:
            await self.send_message(
                message.channel,
                "Please wait until the current player finishes their game"
            )
