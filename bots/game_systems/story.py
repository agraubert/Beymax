import re
from string import printable
import os
import queue
import subprocess
import discord
import asyncio
import threading
import time
from ..utils import Database, load_db

printable_set = set(printable)

def avg(n):
    return sum(n)/len(n)

class GameEnded(OSError):
    pass

more_patterns = [
    re.compile(r'\*+(MORE|more)\*+')
]

score_patterns = [
    re.compile(r'([0-9]+)/[0-9]+'),
    re.compile(r'Score:[ ]*([-]*[0-9]+)'),
    re.compile(r'([0-9]+):[0-9]+ [AaPp][Mm]')
]

clean_patterns = [
    # re.compile(r'[0-9]+/[0-9+]'),
    # re.compile(r'Score:[ ]*[-]*[0-9]+'),
    re.compile(r'Moves:[ ]*[0-9]+'),
    re.compile(r'Turns:[ ]*[0-9]+'),
    # re.compile(r'[0-9]+:[0-9]+ [AaPp][Mm]'),
    re.compile(r' [0-9]+ \.'),
    re.compile(r'^([>.][>.\s]*)'),
    re.compile(r'Warning: @[\w_]+ called .*? \(PC = \w+\) \(will ignore further occurrences\)')
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
            './dfrotz games/%s.z5' % game,
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
        # intake = self.remainder
        # while b'\n' not in intake:
        #     intake += os.read(self.stdoutRead, 64)
        #     print("Buffered intake:", intake)
        # lines = intake.split(b'\n')
        # self.remainder = b'\n'.join(lines[1:])
        # return lines[0].decode().rstrip()
        return os.read(self.stdoutRead, 256).decode()

    def readchunk(self, clean=True, timeout=None):
        if timeout is not None:
            print("The timeout parameter is deprecated")
        if self.proc.returncode is not None:
            raise GameEnded()
        try:
            content = [self.buffer.get(timeout=10)]
        except queue.Empty:
            raise GameEnded()
        try:
            while not self.buffer.empty():
                content.append(self.buffer.get(timeout=0.5))
        except queue.Empty:
            pass

        #now merge up lines
        # print("Raw content:", ''.join(content))
        # import pdb; pdb.set_trace()
        content = [line.rstrip() for line in ''.join(content).split('\n')]

        # clean metadata
        if multimatch(content[-1], more_patterns):
            self.write('\n')
            time.sleep(0.25)
            content += self.readchunk(False)

        # print("Merged content:", content)

        if not clean:
            return content

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

class StorySystem(object):

    def __init__(self, bot, game):
        self.bot = bot
        self.player = Player(game)

    @classmethod
    def query(cls):
        return (
            'Interactive Story',
            [f[:-3] for f in os.listdir('games') if f.endswith('.z5')]
        )

    @classmethod
    async def restore(cls, bot):
        # Attempt to restore the game state
        # Return StorySystem if successful
        # Return None if unable to restore state
        try:
            async with Database('game.json', {'user':'~<IDLE>'}) as state:
                system = StorySystem(bot, state['game'])
                for msg in state['transcript']:
                    system.player.write(msg)
                    await asyncio.sleep(0.5)
                    system.player.readchunk()
                    if system.player.proc.returncode is None:
                        return system
        except:
            pass
        return None

    def is_playing(self, user):
        state = load_db('game.json', {'user':'~<IDLE>'})
        return user.id == state['user']

    async def on_message(self, message, content):
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            try:
                content = message.content.strip().lower()
                if content == 'save':
                    await self.bot.send_message(
                        self.bot.fetch_channel('games'),
                        "Unfortunately, saved games are not supported by "
                        "the story system at this time."
                    )
                elif content == 'score':
                    self.player.write('score')
                    self.player.readchunk()
                    await self.bot.send_message(
                        self.bot.fetch_channel('games'),
                        'Your score is %d' % self.player.score
                    )
                    if self.player.proc.returncode is not None:
                        await self.bot.send_message(
                            self.bot.fetch_channel('games'),
                            "The game has ended"
                        )
                        self.bot.dispatch('endgame', self.bot.get_user(state['user']))
                elif content == 'quit':
                    self.bot.dispatch('endgame', self.bot.get_user(state['user']))
                else:
                    unfiltered_len = len(content)
                    content = ''.join(
                        char for char in content if char in printable_set
                    )
                    if len(content) != unfiltered_len:
                        await self.bot.send_message(
                            self.bot.fetch_channel('games'),
                            "I had to filter out part of your command. "
                            "Here's what I'm actually sending to the game: "
                            "`%s`" % content
                        )
                    if content == '$':
                        content = '\n'
                    state['played'] = True
                    state['transcript'].append(content)
                    state.save()
                    self.player.write(content)
                    await self.bot.send_message(
                        self.bot.fetch_channel('games'),
                        self.player.readchunk(),
                        quote='```'
                    )
                    if self.player.proc.returncode is not None:
                        await self.bot.send_message(
                            self.bot.fetch_channel('games'),
                            "The game has ended"
                        )
                        self.bot.dispatch('endgame', self.bot.get_user(state['user']))
            except GameEnded:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "It looks like this game has ended!"
                )
                self.bot.dispatch('endgame', self.bot.get_user(state['user']))

    async def startgame(self, user):
        async with Database('game.json', {'user':'~<IDLE>', 'bids':[]}) as state:
            state['transcript'] = []
            await self.bot.send_message(
                user,
                'Here are the controls for the story-mode system:\n'
                '`$` : Simply type `$` to enter a blank line to the game\n'
                'That can be useful if the game is stuck or '
                'if it ignored your last input\n'
                'Some menus may ask you to type a space to continue.\n'
                '`quit` : Quits the game in progress\n'
                'This is also how you end the game if you finish it\n'
                '`score` : View your score\n'
                'Some games may have their own commands in addition to these'
                ' ones that I handle personally\n'
                'Lastly, if you want to make a comment in the channel'
                ' without me forwarding your message to the game, '
                'simply start the message with `$!`, for example:'
                ' `$! Any ideas on how to unlock this door?`'
            )
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                self.player.readchunk(),
                quote='```'
            )

    async def endgame(self, user):
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            async with Database('players.json') as players:
                try:
                    self.player.write('score')
                    self.player.readchunk()
                except GameEnded:
                    pass
                finally:
                    self.player.quit()
                async with Database('scores.json') as scores:
                    if state['game'] not in scores:
                        scores[state['game']] = []
                    scores[state['game']].append([
                        self.player.score,
                        state['user']
                    ])
                    scores.save()
                    modifier = avg(
                        [score[0] for game in scores for score in scores[game]]
                    ) / max(1, avg(
                        [score[0] for score in scores[state['game']]]
                    ))
                norm_score = ceil(self.player.score * modifier)
                norm_score += floor(
                    len(state['transcript']) / 25 * min(
                        modifier,
                        1
                    )
                )
                if self.player.score > 0:
                    norm_score = max(norm_score, 1)
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    'Your game has ended. Your score was %d\n'
                    'Thanks for playing! You will receive %d tokens' % (
                        self.player.score,
                        norm_score
                    )
                )
                if self.player.score > max([score[0] for score in scores[state['game']]]):
                    await self.bot.send_message(
                        self.bot.fetch_channel('games'),
                        "%s has just set the high score on %s at %d points" % (
                            user.mention,
                            state['game'],
                            self.player.score
                        )
                    )
                if norm_score > 0:
                    players[state['user']]['balance'] += norm_score
                    # print("Granting xp for score payout")
                    self.bot.dispatch(
                        'grant_xp',
                        user,
                        norm_score * 10
                    )
                state.save()
                players.save()
