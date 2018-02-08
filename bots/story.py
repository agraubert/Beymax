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

    bot.reserve_channel('story')

    @bot.add_command('!_stories')
    async def cmd_story(self, message, content):
        """
        `!_stories` : Lists the available stories
        """
        games = [
            f[:-3] for f in os.listdir('games') if f.endswith('.z5')
        ]
        await self.send_message(
            message.channel,
            '\n'.join(
                ["Here are the stories thar are available:"]+
                games
            )
        )

    def checker(self, message):
        state = load_db('game.json', {'user':'~<IDLE>'})
        return message.channel.id == self.fetch_channel('story').id and state['user'] != '~<IDLE>' and not message.content.startswith('!')

    @bot.add_special(checker)
    async def state_router(self, message, content):
        # Routes messages depending on the game state
        state = load_db('game.json', {'user':'~<IDLE>'})
        if state['user'] == message.author.id:
            if not hasattr(self, 'player'):
                # The game has been interrupted
                await self.send_message(
                    message.channel,
                    "Resuming game in progress...\n"
                    "Please wait"
                )
                self.player = Player(state['game'])
                for msg in state['transcript']:
                    self.player.write(msg)
                    await asyncio.sleep(0.5)
                    self.player.readchunk()
            content = message.content.strip().lower()
            if content == '$':
                content = '\n'
                state['transcript'].append(content)
                save_db(state, 'game.json')
                self.player.write('\n')
                await self.send_message(
                    message.channel,
                    '```'+self.player.readchunk()+'```'
                )
            elif content == 'score':
                self.player.write('score')
                self.player.readchunk()
                await self.send_message(
                    message.channel,
                    'Your score is %d' % self.player.score
                )
            elif content == 'quit':
                self.player.write('score')
                self.player.readchunk()
                self.player.quit()
                await self.send_message(
                    message.channel,
                    'You have quit your game. Your score was %d' % self.player.score
                )
                state['user'] = '~<IDLE>'
                self.dispatch(
                    'grant_xp',
                    message.author,
                    self.player.score * 10 #maybe normalize this since each game scores differently
                )
                del state['transcript']
                del self.player
                save_db(state, 'game.json')
            else:
                state['transcript'].append(content)
                save_db(state, 'game.json')
                self.player.write(content)
                await self.send_message(
                    message.channel,
                    '```'+self.player.readchunk()+'```'
                )
        else:
            await self.send_message(
                message.author,
                "Please refrain from posting messages in the story channel"
                " while someone else is playing"
            )
            await asyncio.sleep(0.5)
            await self.delete_message(message)

    @bot.add_command('!_start')
    async def cmd_start(self, message, content):
        """
        `!_start <game name>` : Starts an interactive text adventure
        Example: `!_start zork1`
        """
        state = load_db('game.json', {'user':'~<IDLE>'})
        if state['user'] == '~<IDLE>':
            games = {
                f[:-3] for f in os.listdir('games') if f.endswith('.z5')
            }
            if content[1] in games:
                state['user'] = message.author.id
                state['transcript'] = []
                state['game'] = content[1]
                save_db(state, 'game.json')
                self.player = Player(content[1])
                # in future:
                # See if there's a way to change permissions of an existing channel
                # For now, just delete other player's messages
                await self.send_message(
                    message.author,
                    'Here are the controls for the story-mode system:\n'
                    'Any message you type in the story channel will be interpreted'
                    ' as input to the game **unless** your message starts with `!`'
                    ' (my commands)\n'
                    '`$` : Simply type `$` to enter a blank line to the game\n'
                    '`quit` : Quits the game in progress\n'
                    '`score` : View your score\n'
                    'Some games may have their own commands in addition to these'
                    ' ones that I handle personally'
                )
                await self.send_message(
                    self.fetch_channel('story'),
                    '%s is now playing %s\n'
                    'The game will begin shortly' % (
                        message.author.mention,
                        content[1]
                    )
                )
                # Post to general
                await asyncio.sleep(2)
                await self.send_message(
                    self.fetch_channel('story'),
                    '```'+self.player.readchunk()+'```'
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


    return bot

    def xp_for(level):
        if level <= 2:
            return 10
        else:
            return (2*xp_for(level-1)-xp_for(level-2))+5

    @bot.subscribe('grant_xp')
    async def grant_xp(self, evt, user, xp):
        players = load_db('players.json')
        if user.id not in players:
            players[user.id] = {
                'level':1,
                'xp':0,
                'balance':10
            }
        player = players[user.id]
        current_level = player['level']
        while player['xp'] >= xp_for(player['level']+1):
            player['xp'] -= xp_for(player['level']+1)
            player['level'] += 1
        if player['level'] > current_level:
            await self.send_message(
                user,
                "Congratulations on reaching level %d! Your weekly token payout"
                " and maximum token balance have both been increased. To check"
                " your balance, type `!balance`" % player['level']
            )
        players[user.id] = player
        self.save_db(players, 'players.json')

    @bot.add_command('!_balance')
    async def cmd_balance(self, message, content):
        """
        `!_balance` : Displays your current token balance
        """
        players = load_db('players.json')
        if message.author.id not in players:
            players[message.author.id] = {
                'level':1,
                'xp':0,
                'balance':10
            }
        player = players[message.author.id]
        await self.send_message(
            message.channel,
            "You are currently level %d and have a balance of %d tokens\n"
            "You have %d xp to go to reach the next level" % (
                player['level'],
                player['balance'],
                xp_for(player['level']+1)-player['xp']
            )
        )

    @bot.add_command('!_bid')
    async def cmd_bid(self, message, content):
        """
        `!_bid <amount> <game>` : Place a bid to play the next game
        """
        pass

    @bot.subscribe('command')
    async def record_command(self, evt, command, user):
        week = load_db('weekly.json')
        if user.id not in week:
            week[user.id] = {}
        if 'commands' not in week[user.id]:
            week[user.id]['commands'] = [command]
            self.dispatch(
                'grant_xp',
                user,
                5
            )
        elif command not in week[user.id]['commands']:
            week[user.id]['commands'].append(command)
            self.dispatch(
                'grant_xp',
                user,
                5
            )
        save_db(week, 'weekly.json')

    @bot.add_task(604800) # 1 week
    async def reset_week(self):
        #{uid: {}}
        week = load_db('weekly.json')
        players = load_db('players.json')
        xp = []
        for uid in weekly:
            if 'active' in weekly[uid]:
                xp.append([user, 5])
            user = self.fetch_channel('story').server.get_member(uid) #icky!
            payout = players[user.id]['level']
            if players[user.id]['balance'] < 20*players[user.id]['level']:
                payout *= 2
            players[uid]['balance'] += payout
            await self.send_message(
                self.fetch_channel('story').server.get_member(uid), #icky!
                "Your allowance was %d tokens this week. Your balance is now %d "
                "tokens" % (
                    payout,
                    players[uid]['balance']
                )
            )
        save_db(players, 'players.json')
        save_db({}, 'weekly.json')
        for user, payout in xp:
            self.dispatch(
                'grant_xp',
                user,
                payout
            )
