from .core import CoreBot
from .utils import getname, Database, load_db, save_db, get_attr
from .args import Arg, UserType
import discord
import asyncio
import os
# import subprocess
# import queue
# import threading
# from string import printable
import time
# import re
from math import ceil, floor

from .game_systems.story import StorySystem



# def avg(n):
#     return sum(n)/len(n)

def EnableGames(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.reserve_channel('games')
    bot._pending_activity = set()

    def listgames():
        for system in [StorySystem]:
            sysname, games = system.query()
            for game in games:
                yield game, sysname, system

    @bot.add_command('games', empty=True)
    async def cmd_story(self, message, content):
        """
        `$!games` : Lists the available games
        """
        await self.send_message(
            message.channel,
            '\n'.join(
                ["Here are the games that are available:"]+
                sorted([
                    '`%s` (%s)' % (game, sysname)
                    for game, sysname, system in listgames()
                ])
            )
        )

    def checker(self, message):
        state = load_db('game.json', {'user':'~<IDLE>'})
        return message.channel.id == self.fetch_channel('games').id and state['user'] != '~<IDLE>' and not message.content.startswith(self.command_prefix)

    @bot.add_special(checker)
    async def state_router(self, message, content):
        # Routes messages depending on the game state
        # if not allowed:
        state = load_db('game.json', {'user':'~<IDLE>'})
        if state['user'] != '~<IDLE>' and not hasattr(self, 'game_system') and self.game_system is not None:
            await self.send_message(
                self.fetch_channel('games'),
                "The game has been interrupted. "
                "Please wait while I resume the previous game"
            )
            self.game_system = await {
                game:system
                for game, sysname, system in listgames()
            }[state['game']].restore(self)
            if self.game_system is None:
                await self.send_message(
                    self.fetch_channel('games'),
                    "I was unable to restore the previous state. "
                    "The current game will be refunded"
                )
                self.dispatch('endgame', self.get_user(state['user']))
        if self.game_system.is_playing(message.author):
            await self.game_system.on_message(message, content)
        elif 'restrict' in state and state['restrict']:
            await self.send_message(
                message.author,
                "The current player has disabled comments in the story channel"
            )
            await asyncio.sleep(0.5)
            await self.delete_message(message)


    @bot.add_command('toggle-comments', empty=True)
    async def cmd_toggle_comments(self, message, content):
        """
        `$!toggle-comments` : Toggles allowing spectator comments in the story_channel
        """
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            if state['user'] != message.author.id:
                await self.send_message(
                    message.channel,
                    "You can't toggle comments if you aren't the game host"
                )
            else:
                if 'restrict' not in state:
                    state['restrict'] = True
                else:
                    state['restrict'] = not state['restrict']
                await self.send_message(
                    self.fetch_channel('games'),
                    "Comments from spectators are now %s" % (
                        'forbidden' if state['restrict'] else 'allowed'
                    )
                )
                state.save()

    @bot.add_command('_start', Arg('game', help="The game to play"))
    async def cmd_start(self, message, args):
        """
        `$!_start <game name>` : Starts one of the allowed games
        Example: `$!_start zork1`
        """
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            if state['user'] == '~<IDLE>':
                games = {
                    game:system
                    for game, sysname, system in listgames()
                }
                if args.game in games:
                    state['bids'] = [{
                        'user':message.author.id,
                        'game':args.game,
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
                    " your balance, type `$!balance`" % player['level']
                )
            players[user.id] = player
            players.save()

    @bot.add_command('balance', empty=True)
    async def cmd_balance(self, message, content):
        """
        `$!balance` : Displays your current token balance
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

    @bot.add_command(
        'bid',
        Arg('amount', type=int, help='Amount of tokens to bid'),
        Arg('game', help="The game to play")
    )
    async def cmd_bid(self, message, args):
        """
        `$!bid <amount> <game>` : Place a bid to play the next game
        Example: `$!bid 1 zork1`
        """
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            if message.author.id == state['user']:
                await self.send_message(
                    message.channel,
                    "You can't bid on a game while you're currently hosting one."
                    " Why not give someone else a turn?"
                )
                return
            async with Database('players.json') as players:
                bid = args.amount
                game = args.game
                games = {
                    game:system
                    for game, sysname, system in listgames()
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
                        " are available, use `$!games`"
                    )
                    return
                user = self.get_user(state['bids'][-1]['user'])
                if user:
                    await self.send_message(
                        user,
                        "You have been outbid by %s with a bid of %d tokens."
                        " If you would like to place another bid, use "
                        "`$!bid %d %s`" % (
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

    @bot.add_command(
        '_payout',
        Arg('user', type=UserType(bot), help="Username or ID"),
        Arg('type', choices=['xp', 'tokens'], help="Type of payout (xp or tokens)"),
        Arg('amount', type=int, help="Amount to pay")
    )
    async def cmd_payout(self, message, args):
        """
        `$!_payout <user> <xp/tokens> <amount>` : Pays xp/tokens to the provided user
        Example: `$!_payout some_user_id xp 12`
        """
        async with Database('players.json') as players:
            if args.user.id not in players:
                players[args.user.id] = {
                    'level':1,
                    'xp':0,
                    'balance':10
                }
            if args.type == 'tokens':
                players[user.id]['balance'] += args.amount
            else:
                self.dispatch(
                    'grant_xp',
                    args.user,
                    args.amount
                )
            players.save()

    @bot.add_command('reup', empty=True)
    async def cmd_reup(self, message, content):
        """
        `$!reup` : Extends your current game session by 1 day
        """
        async with Database('game.json', {'user':'~<IDLE>', 'bids':[]}) as state:
            async with Database('players.json') as players:
                if 'reup' not in state:
                    state['reup'] = 1
                if state['user'] != message.author.id:
                    await self.send_message(
                        message.channel,
                        "You are not currently hosting a game"
                    )
                elif 'played' in state and not state['played']:
                    await self.send_message(
                        message.channel,
                        "You should play your game first"
                    )
                elif players[state['user']]['balance'] < state['reup']:
                    await self.send_message(
                        message.channel,
                        "You do not have enough tokens to extend this session "
                        "(%d tokens)." % state['reup']
                    )
                else:
                    state['time'] += 86400
                    # 1 day + the remaining time
                    players[state['user']]['balance'] -= state['reup']
                    state['reup'] += 1
                    if 'notified' in state:
                        del state['notified']
                    await self.send_message(
                        self.fetch_channel('games'),
                        "The current game session has been extended"
                    )
                    state.save()

    @bot.subscribe('endgame')
    async def end_game(self, evt, user):
        endgame = False
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            async with Database('players.json') as players:
                if self.game_system is None or ('played' in state and not state['played']):
                    await self.send_message(
                        self.fetch_channel('games'),
                        "You quit your game without playing. "
                        "You are being refunded %d tokens" % (
                            state['refund']
                        )
                    )
                    players[user.id]['balance'] += state['refund']
                elif hasattr(self.game_system, 'startgame'):
                    endgame = True
                state.save()
                players.save()
        if endgame:
            await self.game_system.endgame(user)
        async with Database('game.json', {'user':'~<IDLE>'}) as state:
            state['bids'] = state['bids'] if 'bids' in state else []
            state['user'] = '~<IDLE>'
            for k in set(state) - {'user', 'bids'}:
                del state[k]
            del self.game_system
            state.save()
            if 'bids' not in state or len(state['bids']) == 1:
                await self.send_message(
                    self.fetch_channel('games'),
                    "The game is now idle and will be awarded to the first bidder"
                )
            else:
                self.dispatch('startgame')

    @bot.subscribe('startgame')
    async def start_game(self, evt):
        startgame = False
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
                            user = self.get_user(bid['user'])
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
                            state['restrict'] = False
                            state['game'] = bid['game']
                            state['played'] = False
                            state['refund'] = max(0, bid['amount'] - 1)
                            state['time'] = time.time()
                            state['bids'] = [{'user':'', 'amount':0, 'game':''}]
                            state.save()
                            self.game_system = {
                                game:system
                                for game, sysname, system in listgames()
                            }[bid['game']](self, bid['game'])
                            await self.send_message(
                                user,
                                'You have up to 2 days to finish your game, after'
                                ' which, your game will automatically end\n'
                                'Here are the global game-system controls:\n'
                                'Any message you type in the games channel will be interpreted'
                                ' as input to the game **unless** your message starts with `$!`'
                                ' (my commands)\n'
                                '`$!reup` : Use this command to add a day to your game session\n'
                                'This costs 1 token, and the cost will increase each time\n'
                                '`$!toggle-comments` : Use this command to toggle permissions in the games channel\n'
                                'Right now, anyone can send messages in the channel'
                                ' while you\'re playing. If you use `$!toggle-comments`,'
                                ' nobody but you will be allowed to send messages.'
                            )
                            await self.send_message(
                                self.fetch_channel('games'),
                                '%s is now playing %s\n'
                                'The game will begin shortly' % (
                                    user.mention,
                                    bid['game']
                                )
                            )
                            startgame = True
        if startgame:
            await asyncio.sleep(2)
            if hasattr(self.game_system, 'startgame'):
                await self.game_system.startgame(user)
            return
        else:
            async with Database('game.json', {'user':'~<IDLE>', 'bids':[]}) as state:
                state['user'] = '~<IDLE>'
                state['transcript'] = []
                state['game'] = ''
                state['reup'] = 1
                state['bids'] = [{'user':'', 'amount':0, 'game':''}]
                state.save()
                await self.send_message(
                    self.fetch_channel('games'),
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

    @bot.add_command('timeleft', empty=True)
    async def cmd_timeleft(self, message, content):
        """
        `$!timeleft` : Gets the remaining time for the current game
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
                        str(self.get_user(state['user'])),
                        state['game'],
                        d_days,
                        d_hours,
                        d_minutes,
                        d_seconds
                    )
                )

    @bot.add_command('highscore', Arg('game', help="The game to get the highscore of"))
    async def cmd_highscore(self, message, args):
        """
        `$!highscore <game>` : Gets the current highscore for that game
        Example: `$!highscore zork1`
        """
        async with Database('scores.json') as scores:
            if args.game in scores:
                score, uid = sorted(
                    scores[args.game],
                    key=lambda x:x[0],
                    reverse=True
                )[0]
                await self.send_message(
                    message.channel,
                    "High score for %s: %d set by %s" % (
                        args.game,
                        score,
                        get_attr(self.get_user(uid), 'mention', '')
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
                    user = self.get_user(uid)
                    if uid not in players:
                        players[uid] = {
                            'level':1,
                            'xp':0,
                            'balance':10
                        }
                    payout = players[user.id]['level']
                    if players[user.id]['balance'] < 20*players[user.id]['level']:
                        payout *= 2
                    elif players[user.id]['balance'] > 100*players[user.id]['level']:
                        payout //= 10
                    players[uid]['balance'] += payout
                    if 'active' in week[uid] or uid in self._pending_activity:
                        xp.append([user, 5])
                        #only notify if they were active. Otherwise don't bother them
                        await self.send_message(
                            self.get_user(uid),
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
                user = self.get_user(state['user'])
                self.dispatch('endgame', user)
                return
            elif state['user'] != '~<IDLE>' and now - state['time'] >= 151200: # 6 hours left
                if 'notified' not in state or state['notified'] == 'first':
                    await self.send_message(
                        self.get_user(state['user']),
                        "Your current game of %s is about to expire. If you wish to extend"
                        " your game session, you can `$!reup` at a cost of %d tokens,"
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
                        self.get_user(state['user']),
                        "Your current game of %s will expire in less than 1 day. If you"
                        " wish to extend your game session, you can `$!reup` at a cost of"
                        " %d tokens, which will grant you an additional day" % (
                            state['game'],
                            state['reup'] if 'reup' in state else 1
                        )
                    )
                    state['notified'] = 'first'
                    state.save()
        if hasattr(self, 'game_system') and hasattr(self.game_system, 'check_game'):
            await self.game_system.check_game()
    return bot
