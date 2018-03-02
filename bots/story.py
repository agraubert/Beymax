from .core import CoreBot
from .utils import getname, Database, load_db, save_db
import discord
import asyncio
import os
import subprocess
import queue
import threading
import time
import re
from math import ceil, floor

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

def avg(n):
    return sum(n)/len(n)

def EnableStory(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.reserve_channel('story')
    bot._pending_activity = set()

    @bot.add_command('!games')
    async def cmd_story(self, message, content):
        """
        `!games` : Lists the available games
        """
        games = [
            f[:-3] for f in os.listdir('games') if f.endswith('.z5')
        ]
        await self.send_message(
            message.channel,
            '\n'.join(
                ["Here are the games that are available:"]+
                games
            )
        )

    def checker(self, message):
        state = load_db('game.json', {'user':'~<IDLE>'})
        return message.channel.id == self.fetch_channel('story').id and state['user'] != '~<IDLE>' and not message.content.startswith('!')

    @bot.add_special(checker)
    async def state_router(self, message, content):
        # Routes messages depending on the game state
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            if state['user'] == message.author.id:
                try:
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
                            if self.player.proc.returncode is not None:
                                await self.send_message(
                                    message.channel,
                                    "The game has ended"
                                )
                                self.dispatch('endgame', message.author, message.channel)
                    content = message.content.strip().lower()
                    if content == '$':
                        state['transcript'].append('\n')
                        state.save()
                        self.player.write('\n')
                        await self.send_message(
                            message.channel,
                            self.player.readchunk(),
                            quote='```'
                        )
                        if self.player.proc.returncode is not None:
                            await self.send_message(
                                message.channel,
                                "The game has ended"
                            )
                            self.dispatch('endgame', message.author, message.channel)
                    elif content == 'save':
                        await self.send_message(
                            message.channel,
                            "Unfortunately, saved games are not supported at "
                            "this time."
                        )
                    elif content == 'score':
                        self.player.write('score')
                        self.player.readchunk()
                        await self.send_message(
                            message.channel,
                            'Your score is %d' % self.player.score
                        )
                        if self.player.proc.returncode is not None:
                            await self.send_message(
                                message.channel,
                                "The game has ended"
                            )
                            self.dispatch('endgame', message.author, message.channel)
                    elif content == 'quit':
                        self.dispatch('endgame', message.author, message.channel)
                    else:
                        state['played'] = True
                        state['transcript'].append(content)
                        state.save()
                        self.player.write(content)
                        await self.send_message(
                            message.channel,
                            self.player.readchunk(),
                            quote='```'
                        )
                        if self.player.proc.returncode is not None:
                            await self.send_message(
                                message.channel,
                                "The game has ended"
                                )
                            self.dispatch('endgame', message.author, message.channel)
                except GameEnded:
                    await self.send_message(
                        message.channel,
                        "It looks like this game has ended!"
                    )
                    self.dispatch('endgame', message.author, message.channel)
            elif 'restrict' in state and state['restrict']:
                await self.send_message(
                    message.author,
                    "The current player has disabled comments in the story channel"
                )
                await asyncio.sleep(0.5)
                await self.delete_message(message)

    @bot.add_command('!toggle-comments')
    async def cmd_toggle_comments(self, message, content):
        """
        `!toggle-comments` : Toggles allowing spectator comments in the story_channel
        """
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            if state['user'] != message.author.id:
                await self.send_message(
                    message.channel,
                    "You can't toggle comments if you're not playing"
                )
            else:
                if 'restrict' not in state:
                    state['restrict'] = True
                else:
                    state['restrict'] = not state['restrict']
                await self.send_message(
                    self.fetch_channel('story'),
                    "Comments from spectators are now %s" % (
                        'forbidden' if state['restrict'] else 'allowed'
                    )
                )
                state.save()

    @bot.add_command('!_start')
    async def cmd_start(self, message, content):
        """
        `!_start <game name>` : Starts an interactive text adventure
        Example: `!_start zork1`
        """
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            if state['user'] == '~<IDLE>':
                games = {
                    f[:-3] for f in os.listdir('games') if f.endswith('.z5')
                }
                if content[1] in games:
                    state['bids'] = [{
                        'user':message.author.id,
                        'game':content[1],
                        'amount':0
                    }]
                    state.save()
                    self.dispatch('startgame')
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


    def xp_for(level):
        if level <= 2:
            return 10
        else:
            return (2*xp_for(level-1)-xp_for(level-2))+5

    @bot.subscribe('grant_xp')
    async def grant_some_xp(self, evt, user, xp):
        # print(
        #     "<dev>: %d xp has been granted to %s" % (
        #         xp, str(user)
        #     )
        # )
        async with Database('players.json') as players:
            if user.id not in players:
                players[user.id] = {
                    'level':1,
                    'xp':0,
                    'balance':10
                }
            player = players[user.id]
            player['xp'] += xp
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
            players.save()

    @bot.add_command('!balance')
    async def cmd_balance(self, message, content):
        """
        `!balance` : Displays your current token balance
        """
        async with Database('players.json') as players:
            if message.author.id not in players:
                players[message.author.id] = {
                    'level':1,
                    'xp':0,
                    'balance':10
                }
            player = players[message.author.id]
            await self.send_message(
                message.author,
                "You are currently level %d and have a balance of %d tokens\n"
                "You have %d xp to go to reach the next level" % (
                    player['level'],
                    player['balance'],
                    xp_for(player['level']+1)-player['xp']
                )
            )

    @bot.add_command('!bid')
    async def cmd_bid(self, message, content):
        """
        `!bid <amount> <game>` : Place a bid to play the next game
        Example: `!bid 1 zork1`
        """
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            if message.author.id == state['user']:
                await self.send_message(
                    message.channel,
                    "You can't place a bid while you're already playing a game."
                    " Why not give someone else a turn?"
                )
                return
            async with Database('players.json') as players:
                bid = content[1]
                try:
                    bid = int(bid)
                except ValueError:
                    await self.send_message(
                        message.channel,
                        "'%s' is not a valid amount of tokens" % bid
                    )
                    return
                game = content[2]
                games = {
                    f[:-3] for f in os.listdir('games') if f.endswith('.z5')
                }
                if 'bids' not in state:
                    state['bids'] = [{'user':'', 'amount':0, 'game':''}]
                # print(state)
                # print(players)
                # print(bid)
                # print(game)
                if bid <= state['bids'][-1]['amount']:
                    if len(state['bids'][-1]['user']):
                        await self.send_message(
                            message.channel,
                            "The current highest bid is %d tokens. Your bid must"
                            " be at least %d tokens." % (
                                state['bids'][-1]['amount'],
                                state['bids'][-1]['amount'] + 1
                            )
                        )
                        return
                    else:
                        await self.send_message(
                            message.channel,
                            "The minimum bid is 1 token"
                        )
                        return
                if message.author.id not in players:
                    players[message.author.id] = {
                        'level':1,
                        'xp':0,
                        'balance':10
                    }
                if bid > players[message.author.id]['balance']:
                    await self.send_message(
                        message.channel,
                        "You do not have enough tokens to make that bid."
                        "To check your token balance, use `!balance`"
                    )
                    return
                if game not in games:
                    await self.send_message(
                        message.channel,
                        "That is not a valid game. To see the list of games that"
                        " are available, use `!games`"
                    )
                    return
                user = self.fetch_channel('story').server.get_member(state['bids'][-1]['user'])
                if user:
                    await self.send_message(
                        user,
                        "You have been outbid by %s with a bid of %d tokens."
                        " If you would like to place another bid, use "
                        "`!bid %d %s`" % (
                            getname(message.author),
                            bid,
                            bid+1,
                            state['bids'][-1]['game']
                        )
                    )
                state['bids'].append({
                    'user':message.author.id,
                    'amount':bid,
                    'game':game
                })
                state.save()
                if state['user'] == '~<IDLE>':
                    self.dispatch('startgame')
                else:
                    await self.send_message(
                        message.channel,
                        "Your bid has been placed. If you are not outbid, your"
                        " game will begin after the current game has ended"
                    )

    @bot.add_command('!reup')
    async def cmd_reup(self, message, content):
        """
        `!reup` : Extends your current game session by 1 day
        """
        async with Database('game.json', {'user':'~<IDLE>', 'bids':[]}) as state:
            async with Database('players.json') as players:
                if 'reup' not in state:
                    state['reup'] = 1
                if state['user'] != message.author.id:
                    await self.send_message(
                        message.channel,
                        "You are not currently playing a game"
                    )
                elif 'played' in state and not state['played']:
                    await self.send_message(
                        message.channel,
                        "You should play your game first"
                    )
                elif players[state['user']]['balance'] < state['reup']:
                    await self.send_message(
                        message.channel,
                        "You do not have enough tokens to extend this session"
                    )
                else:
                    state['time'] += 86400
                    # 1 day + the remaining time
                    players[state['user']]['balance'] -= state['reup']
                    state['reup'] += 1
                    if 'notified' in state:
                        del state['notified']
                    await self.send_message(
                        self.fetch_channel('story'),
                        "The current game session has been extended"
                    )
                    state.save()

    @bot.subscribe('endgame')
    async def end_game(self, evt, user, dest):
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            async with Database('players.json') as players:
                if 'played' in state and not state['played']:
                    await self.send_message(
                        dest,
                        "You quit your game without playing. "
                        "You are being refunded %d tokens" % (
                            state['refund']
                        )
                    )
                    players[user.id]['balance'] += state['refund']
                else:
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
                    await self.send_message(
                        dest,
                        'Your game has ended. Your score was %d\n'
                        'Thanks for playing! You will receive %d tokens' % (
                            self.player.score,
                            norm_score
                        )
                    )
                    if self.player.score > max([score[0] for score in scores[state['game']]]):
                        await self.send_message(
                            self.fetch_channel('story'),
                            "%s has just set the high score on %s at %d points" % (
                                user.mention,
                                state['game'],
                                self.player.score
                            )
                        )
                    if norm_score > 0:
                        players[state['user']]['balance'] += norm_score
                        # print("Granting xp for score payout")
                        self.dispatch(
                            'grant_xp',
                            user,
                            norm_score * 10 #maybe normalize this since each game scores differently
                        )
            del state['transcript']
            if 'notified' in state:
                del state['notified']
            state['user'] = '~<IDLE>'
            del self.player
            state.save()
            players.save()
            if 'bids' not in state or len(state['bids']) == 1:
                await self.send_message(
                    self.fetch_channel('story'),
                    "The game is now idle and will be awarded to the first bidder"
                )
            else:
                self.dispatch('startgame')

    @bot.subscribe('startgame')
    async def start_game(self, evt):
        async with Database('game.json', {'user':'~<IDLE>', 'bids':[]}) as state:
            async with Database('players.json') as players:
                if state['user'] == '~<IDLE>':
                    for bid in reversed(state['bids']):
                        if bid['user'] != '':
                            if bid['user'] not in players:
                                players[bid['user']] = {
                                    'level':1,
                                    'xp':0,
                                    'balance':10
                                }
                            user = self.fetch_channel('story').server.get_member(bid['user'])
                            if bid['amount'] > players[bid['user']]['balance']:
                                await self.send_message(
                                    user,
                                    "You do not have enough tokens to cover your"
                                    " bid of %d. Your bid is forfeit and the game"
                                    " shall pass to the next highest bidder" % (
                                        bid['amount']
                                    )
                                )
                                continue
                            players[bid['user']]['balance'] -= bid['amount']
                            players.save()
                            state['user'] = bid['user']
                            state['transcript'] = []
                            state['restrict'] = False
                            state['game'] = bid['game']
                            state['played'] = False
                            state['refund'] = max(0, bid['amount'] - 1)
                            state['time'] = time.time()
                            state['bids'] = [{'user':'', 'amount':0, 'game':''}]
                            state.save()
                            self.player = Player(bid['game'])
                            # in future:
                            # See if there's a way to change permissions of an existing channel
                            # For now, just delete other player's messages
                            await self.send_message(
                                user,
                                'You have up to 2 days to finish your game, after'
                                ' which, your game will automatically end\n'
                                'Here are the controls for the story-mode system:\n'
                                'Any message you type in the story channel will be interpreted'
                                ' as input to the game **unless** your message starts with `!`'
                                ' (my commands)\n'
                                '`!reup` : Use this command to add a day to your game session\n'
                                'This costs 1 token, and the cost will increase each time\n'
                                '`!toggle-comments` : Use this command to toggle permissions in the story channel\n'
                                'Right now, anyone can send messages in the story channel'
                                ' while you\'re playing. If you use `!toggle-comments`,'
                                ' nobody but you will be allowed to send messages.\n'
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
                                'simply start the message with `! `, for example:'
                                ' `! Any ideas on how to unlock this door?`'
                            )
                            await self.send_message(
                                self.fetch_channel('story'),
                                '%s is now playing %s\n'
                                'The game will begin shortly' % (
                                    user.mention,
                                    bid['game']
                                )
                            )
                            # Post to general
                            await asyncio.sleep(2)
                            await self.send_message(
                                self.fetch_channel('story'),
                                self.player.readchunk(),
                                quote='```'
                            )
                            return
                    state['user'] = '~<IDLE>'
                    state['transcript'] = []
                    state['game'] = ''
                    state['reup'] = 1
                    state['bids'] = [{'user':'', 'amount':0, 'game':''}]
                    state.save()
                    await self.send_message(
                        self.fetch_channel('story'),
                        "None of the bidders for the current game session could"
                        " honor their bids. The game is now idle and will be"
                        " awarded to the first bidder"
                    )


    @bot.subscribe('command')
    async def record_command(self, evt, command, user):
        async with Database('weekly.json') as week:
            if user.id not in week:
                week[user.id] = {}
            # print(week)
            if 'commands' not in week[user.id]:
                week[user.id]['commands'] = [command]
                # print("granting xp for first command", command)
                self.dispatch(
                    'grant_xp',
                    user,
                    5
                )
            elif command not in week[user.id]['commands']:
                week[user.id]['commands'].append(command)
                # print("granting xp for new command", command)
                self.dispatch(
                    'grant_xp',
                    user,
                    5
                )
            week[user.id]['active'] = True
            week.save()

    @bot.subscribe('after:message')
    async def record_activity(self, evt, message):
        if message.author.id != self.user.id:
            self._pending_activity.add(message.author.id)

    @bot.subscribe('cleanup')
    async def save_activity(self, evt):
        async with Database('weekly.json') as week:
            # print(week, self._pending_activity)
            for uid in self._pending_activity:
                if uid not in week:
                    week[uid]={'active':True}
                else:
                    week[uid]['active']=True
            self._pending_activity = set()
            # print(week)
            week.save()

    @bot.add_command('!timeleft')
    async def cmd_timeleft(self, message, content):
        """
        `!timeleft` : Gets the remaining time for the current game
        """
        async with Database('game.json', {'user':'~<IDLE>', 'bids':[]}) as state:
            if state['user'] == '~<IDLE>':
                await self.send_message(
                    message.channel,
                    "Currently, nobody is playing a game"
                )
            else:
                delta = (state['time'] + 172800) - time.time()
                d_days = delta // 86400
                delta = delta % 86400
                d_hours = delta // 3600
                delta = delta % 3600
                d_minutes = delta // 60
                d_seconds = delta % 60
                await self.send_message(
                    message.channel,
                    "%s's game of %s will end in %d days, %d hours, %d minutes, "
                    "and %d seconds" % (
                        self.users[state['user']]['fullname'],
                        state['game'],
                        d_days,
                        d_hours,
                        d_minutes,
                        d_seconds
                    )
                )

    @bot.add_command('!highscore')
    async def cmd_highscore(self, message, content):
        """
        `!highscore <game>` : Gets the current highscore for that game
        Example: `!highscore zork1`
        """
        if len(content) < 2:
            await self.send_message(
                message.channel,
                "Please provide a game name with this command"
            )
            return
        async with Database('scores.json') as scores:
            if content[1] in scores:
                score, uid = sorted(
                    scores[content[1]],
                    key=lambda x:x[0],
                    reverse=True
                )[0]
                await self.send_message(
                    message.channel,
                    "High score for %s: %d set by %s" % (
                        content[1],
                        score,
                        self.users[uid]['mention']
                    )
                )
            else:
                await self.send_message(
                    message.channel,
                    "No scores for this game yet"
                )


    @bot.add_task(604800) # 1 week
    async def reset_week(self):
        #{uid: {}}
        async with Database('players.json') as players:
            async with Database('weekly.json') as week:
                print("Resetting the week")
                xp = []
                for uid in week:
                    user = self.fetch_channel('story').server.get_member(uid) #icky!
                    if uid not in players:
                        players[uid] = {
                            'level':1,
                            'xp':0,
                            'balance':10
                        }
                    payout = players[user.id]['level']
                    if players[user.id]['balance'] < 20*players[user.id]['level']:
                        payout *= 2
                    players[uid]['balance'] += payout
                    if 'active' in week[uid] or uid in self._pending_activity:
                        xp.append([user, 5])
                        #only notify if they were active. Otherwise don't bother them
                        await self.send_message(
                            self.fetch_channel('story').server.get_member(uid), #icky!
                            "Your allowance was %d tokens this week. Your balance is now %d "
                            "tokens" % (
                                payout,
                                players[uid]['balance']
                            )
                        )
                self._pending_activity = set()
                players.save()
                os.remove('weekly.json')
                for user, payout in xp:
                    # print("granting xp for activity payout")
                    self.dispatch(
                        'grant_xp',
                        user,
                        payout
                    )

    @bot.add_task(1800) # 30 minutes
    async def check_game(self):
        async with Database('game.json', {'user':'~<IDLE>', 'bids':[]}) as state:
            now = time.time()
            if state['user'] != '~<IDLE>' and now - state['time'] >= 172800: # 2 days
                user = self.fetch_channel('story').server.get_member(state['user'])
                self.dispatch('endgame', user, user)
            elif state['user'] != '~<IDLE>' and now - state['time'] >= 151200: # 6 hours left
                if 'notified' not in state or state['notified'] == 'first':
                    await self.send_message(
                        self.fetch_channel('story').server.get_member(state['user']),
                        "Your current game of %s is about to expire. If you wish to extend"
                        " your game session, you can `!reup` at a cost of %d tokens,"
                        " which will grant you an additional day" % (
                            state['game'],
                            state['reup'] if 'reup' in state else 1
                        )
                    )
                    state['notified'] = 'second'
                    state.save()
            elif ('played' not in state or state['played']) and state['user'] != '~<IDLE>' and now - state['time'] >= 86400: # 1 day left
                if 'notified' not in state:
                    await self.send_message(
                        self.fetch_channel('story').server.get_member(state['user']),
                        "Your current game of %s will expire in less than 1 day. If you"
                        " wish to extend your game session, you can `!reup` at a cost of"
                        " %d tokens, which will grant you an additional day" % (
                            state['game'],
                            state['reup'] if 'reup' in state else 1
                        )
                    )
                    state['notified'] = 'first'
                    state.save()
    return bot
