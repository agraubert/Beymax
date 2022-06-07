import re
from string import printable
import os
import queue
import subprocess
import discord
import asyncio
import threading
import time
from ...utils import DBView
from .base import GameSystem, GameError, JoinLeaveProhibited, GameEndException
from math import ceil, floor

printable_set = set(printable)
printable_bytes = printable.encode()

def avg(n):
    return sum(n)/len(n)

class BackgroundGameExit(GameError):
    pass

more_patterns = [
    re.compile(r'\*+(MORE|more)\*+'), # Match ****MORE****
    re.compile(r'.*\.\.\.+\s*$') # Match ....
]

score_patterns = [
    re.compile(r'([0-9]+)/[0-9]+'),
    re.compile(r'Score:[ ]*([-]*[0-9]+)'),
    re.compile(r'([0-9]+):[0-9]+ [AaPp][Mm]'),
    re.compile(r'Your score is (\d+)')
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

class Player(object):
    def __init__(self, frotz, game):
        (self.stdinRead, self.stdinWrite) = os.pipe()
        (self.stdoutRead, self.stdoutWrite) = os.pipe()
        self.buffer = queue.Queue()
        self.remainder = b''
        self.score = 0
        self.closed = False
        self.proc = subprocess.Popen(
            [frotz, 'games/{}.z5'.format(game)],
            universal_newlines=False,
            # shell=True,
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
        while not self.closed:
            # self.buffer.put(self.readline())
            try:
                line = self.readline()
                self.buffer.put(line)
            except OSError:
                self.closed = True

    def readline(self):
        # intake = self.remainder
        # while b'\n' not in intake:
        #     intake += os.read(self.stdoutRead, 64)
        #     print("Buffered intake:", intake)
        # lines = intake.split(b'\n')
        # self.remainder = b'\n'.join(lines[1:])
        # return lines[0].decode().rstrip()
        return os.read(self.stdoutRead, 256).decode()

    def readchunk(self, clean=True):
        if self.proc.returncode is not None:
            raise BackgroundGameExit(
                "Player exited with returncode %d" % self.proc.returncode
            )
        try:
            content = [self.buffer.get(timeout=5)]
        except queue.Empty:
            raise BackgroundGameExit(
                "No content in buffer"
            )
        time.sleep(1)
        while not self.buffer.empty():
            try:
                while not self.buffer.empty():
                    content.append(self.buffer.get(timeout=1))
            except queue.Empty:
                pass
            time.sleep(1)

        #now merge up lines
        # print("Raw content:", ''.join(content))
        # import pdb; pdb.set_trace()
        content = [line.rstrip() for line in ''.join(content).split('\n')]

        # clean metadata
        if multimatch(content[-1], more_patterns):
            self.write('\n')
            time.sleep(0.5)
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
        try:
            self.write('quit')
            self.write('y')
            self.closed = True
            try:
                self.proc.wait(1)
            except:
                self.proc.kill()
            os.close(self.stdinRead)
            os.close(self.stdinWrite)
            os.close(self.stdoutRead)
            os.close(self.stdoutWrite)
        except OSError:
            pass

class StorySystem(GameSystem):
    name = 'Interactive Story'
    instructions = (
        'Here are the controls for the Interactive Story system:\n'
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
        'simply start the message with `$! `, for example:'
        ' `$! Any ideas on how to unlock this door?`'
    )

    def __init__(self, bot, game):
        super().__init__(bot, game)
        self.player = Player(bot.config_get('zmachine', default='dfrotz'), game)
        self.state = {}

    @classmethod
    def games(cls):
        return (
            [f[:-3] for f in os.listdir('games') if f.endswith('.z5')]
            if os.path.isdir('games')
            else []
        )

    @classmethod
    async def restore(cls, bot, game):
        # Attempt to restore the game state
        # Return StorySystem if successful
        # Return None if unable to restore state
        try:
            async with DBView(story={'host': None, 'game': ''}) as db:
                if db['story']['host'] is None:
                    raise GameError("No primary player defined in state")
                system = StorySystem(bot, db['story']['game'])
                system.state.update(db['story'])
                if 'transcript' in db['story']:
                    for msg in db['story']['transcript']:
                        print("Replaying", msg)
                        system.player.write(msg)
                        await asyncio.sleep(0.5)
                        print(system.player.readchunk())
                        if system.player.proc.returncode is not None:
                            break
                return system
        except Exception as e:
            raise GameEndException("Unable to restore") from e

    @property
    def played(self):
        return (
            'transcript' in self.state and
            len(self.state['transcript'])
        )

    def is_playing(self, user):
        return user.id in self.state['players']

    async def on_input(self, user, channel, message):
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
                self.state['score'] = self.player.score
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    'Your score is %d' % self.player.score
                )
                if self.player.proc.returncode is not None:
                    await self.bot.send_message(
                        self.bot.fetch_channel('games'),
                        "The game has ended"
                    )
                    self.bot.dispatch('endgame')
            elif content == 'quit':
                # Don't call player.quit() here. That's handled in on_end
                self.bot.dispatch('endgame')
            else:
                unfiltered_len = len(content)
                content = ''.join(
                    char for char in content if char in printable_set
                )
                if not len(content):
                    await self.bot.send_message(
                        self.bot.fetch_channel('games'),
                        "Your message didn't contain any characters which could"
                        " be parsed by the game"
                    )
                elif len(content) != unfiltered_len:
                    await self.bot.send_message(
                        self.bot.fetch_channel('games'),
                        "I had to filter out part of your command. "
                        "Here's what I'm actually sending to the game: "
                        "`%s`" % content
                    )
                if content == '$':
                    content = '\n'
                self.state['transcript'].append(content)
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
                    self.bot.dispatch('endgame')
        except BackgroundGameExit:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "It looks like this game has ended!"
            )
            self.bot.dispatch('endgame')
        await self.save_state()

    async def save_state(self):
        await DBView.overwrite(story=self.state)

    async def on_start(self, user):
        self.state = {
            'transcript': [],
            'host': user.id,
            'players': [user.id],
            'game': self.game,
            'score': 0
        }
        await self.save_state()
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            self.player.readchunk(),
            quote='```'
        )


    async def on_join(self, user):
        self.state['players'].append(user.id)
        await self.save_state()

    async def on_leave(self, user):
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            user.mention + " has left the game"
        )
        self.state['players'].remove(user.id)
        await self.save_state()


    async def on_end(self):
        async with DBView('players', 'scores') as db:
            try:
                self.player.write('score')
                self.player.readchunk()
            except BackgroundGameExit:
                pass
            finally:
                self.player.quit()
            if self.game not in db['scores']:
                db['scores'][self.game] = []
            db['scores'][self.game].append([
                self.player.score,
                self.state['host']
            ])
            # Modifier = (avg of all games) / (avg of this game)
            modifier = avg(
                [score[0] for game in db['scores'] for score in db['scores'][game]]
            ) / max(1, avg(
                [score[0] for score in db['scores'][self.game]]
            ))
            # norm score = ((score * modifier) + (transcript/25) * {modifier if modifier < 1 else 1}) * (1.05/players)
            norm_score = ceil(self.player.score * modifier)
            print(self.player.score, modifier, norm_score)
            if len(self.state['players']) > 1:
                norm_score *= 1.05 / len(self.state['players'])
            if self.player.score > 0:
                norm_score = max(norm_score, 1)
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                'Your game has ended. Your score was %d\n'
                'Thanks for playing! All players will receive %d tokens' % (
                    self.player.score,
                    norm_score
                )
            )
            if self.player.score > max([score[0] for score in db['scores'][self.game]]):
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "%s %s just set the high score on %s at %d points" % (
                        (
                            self.bot.get_user(self.state['host']).mention
                            if len(self.state['players']) <= 1
                            else
                            (
                                ', '.join(
                                    self.bot.get_user(player).mention
                                    for player in self.state['players'][:-1]
                                ) + ' and ' + self.bot.get_user(self.state['players'][-1]).mention
                            )
                        ),
                        'has' if len(self.state['players']) <= 1 else 'have',
                        self.game,
                        self.player.score
                    )
                )
            if norm_score > 0:
                for player in self.state['players']:
                    db['players'][player]['balance'] += norm_score

    async def on_cleanup(self):
        await DBView.overwrite(story={})
