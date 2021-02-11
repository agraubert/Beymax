from .core import CoreBot
from .utils import getname, DBView, get_attr
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

from .game_systems.base import GameSystem, GameError, GameEndException, JoinLeaveProhibited
from .game_systems.story import StorySystem
from .game_systems.poker import PokerSystem

from functools import lru_cache

# def avg(n):
#     return sum(n)/len(n)

# Games overhaul / notes:

SYSTEMS = [StorySystem, PokerSystem]


# New commands:
# !invite @user : bidder invites user to game
# !join : Invitee accepts invitation to join game (dispatch on_join)
# !leave : Player leaves game (dispatch on_leave). If bidder leaves, dispatch on_end instead

# Enable games adds the following commands, events, and tasks
# !games :

def EnableGames(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.reserve_channel('games')
    bot._pending_activity = set()
    bot._game_system = None

    def listgames():
        for system in SYSTEMS:
            for game in system.games():
                yield game, system.name, system

    # FIXME: Why is this not subscribed to restore or something?
    async def restore_game(self):
        async with DBView(game={'user': None}) as db:
            if db['game']['user'] is not None and self._game_system is None:
                await self.send_message(
                    self.fetch_channel('games'),
                    "The game has been interrupted. "
                    "Please wait while I resume the previous game"
                )
                try:
                    self._game_system = await {
                        game:system
                        for game, sysname, system in listgames()
                    }[db['game']['game']].restore(self, db['game']['game'])
                    await self._game_system.on_init()
                    await self._game_system.on_restore(
                        self.get_user(db['game']['user'])
                    )
                    await self._game_system.on_ready()
                except GameError:
                    await self.send_message(
                        self.fetch_channel('games'),
                        "I was unable to restore the previous state. "
                        "The current game will be refunded"
                    )
                    await self.trace()
                    self.dispatch('endgame', 'hard')
                    raise
                except:
                    await self.send_message(
                        self.fetch_channel('games'),
                        "I was unable to restore the previous state. "
                        "The current game will be refunded"
                    )
                    await self.trace()
                    self.dispatch('endgame', 'critical')
                    raise

    @bot.add_command('invite', Arg('user', type=UserType(bot), help="Username, nickname, or ID of user"))
    async def cmd_invite(self, message, user):
        """
        `$!invite <user>` : Invites the given user to join your game.
        Can only be used if you are the host of the current game
        Example: `$!invite $NAME` : Invites me to join your game
        """
        async with DBView('game', game={'user': None}) as db:
            if db['game']['user'] is None:
                await self.send_message(
                    message.channel,
                    "There are no games in progress. You can start one with `$!bid`"
                )
            elif db['game']['user'] != message.author.id:
                await self.send_message(
                    message.channel,
                    "You are not the host of the current game. Only the host "
                    "(who had the winning `$!bid` can invite players)"
                )
            else:
                if self._game_system is None:
                    await restore_game(self)
                if self._game_system.is_playing(user):
                    return await self.send_message(
                        message.channel,
                        "%d is already playing this game" % getname(args.user)
                    )
                if 'invites' not in db['game']:
                    db['game']['invites'] = [user.id]
                elif user.id not in db['game']['invites']:
                    db['game']['invites'].append(user.id)
                await self.send_message(
                    user,
                    '%s has invited you to play %s. Use `$!join` to accept the '
                    'invite and join the game.' % (
                        message.author.mention,
                        db['game']['game']
                    )
                )
                await self.send_message(
                    message.channel,
                    "Invite sent to %s" % user.mention
                )

    @bot.add_command('join')
    async def cmd_join(self, message):
        """
        `$!join` : Joins the current game, if you've been invited
        """
        print("joining")
        async with DBView('game', game={'user': None}) as db:
            print("Acquired state")
            if db['game']['user'] is None:
                await self.send_message(
                    message.channel,
                    "There are no games in progress. You can start one with `$!bid`"
                )
            elif 'invites' not in db['game'] or message.author.id not in db['game']['invites']:
                await self.send_message(
                    message.channel,
                    "You have not been invited to play this game"
                )
            else:
                print("State is joinable")
                db['game']['invites'].remove(message.author.id)
                await self.send_message(
                    message.channel,
                    "Attempting to join the game..."
                )
                if self._game_system is None:
                    await restore_game(self)
                try:
                    print("Joining")
                    await self._game_system.on_join(message.author)
                except JoinLeaveProhibited:
                    await self.send_message(
                        message.channel,
                        "The current game prohibits new players from joining the game"
                    )
                except GameEndException:
                    await self.trace()
                    await self.send_message(
                        self.fetch_channel('games'),
                        "Encountered a critical error while adding a new player."
                        " The current game will be refunded"
                    )
                    self.dispatch('endgame', 'hard')
                except:
                    await self.trace()
                    await self.send_message(
                        self.fetch_channel('games'),
                        "Encountered an error while adding a new player"
                    )
                else:
                    await self.send_message(
                        message.channel,
                        "The game has processed your request to join. "
                        "Use `$!leave` to leave the game"
                    )


    @bot.add_command('leave')
    async def cmd_leave(self, message):
        """
        `$!leave` : Leaves the current game, if you're playing.
        If you are the host of the game, leaving will end the game
        """
        async with DBView('game', game={'user': None}) as db:
            print("LEAVING GAME")
            if db['game']['user'] is None:
                await self.send_message(
                    message.channel,
                    "There are no games in progress. You can start one with `$!bid`"
                )
            else:
                if self._game_system is None:
                    await restore_game(self)
                if not self._game_system.is_playing(message.author):
                    await self.send_message(
                        message.channel,
                        "You are not playing this game"
                    )
                else:
                    if message.author.id == db['game']['user']:
                        await self.send_message(
                            message.channel,
                            "You are the host of the current game. If you leave,"
                            " the game will end. Do you still want to leave the"
                            " game? (Yes/No)"
                        )
                        while True:
                            try:
                                response = await self.wait_for(
                                    'message',
                                    check=lambda m: m.author==message.author and m.channel == message.channel,
                                    timeout=60,
                                )
                            except asyncio.TimeoutError:
                                await self.send_message(
                                    message.channel,
                                    "%s, if you still want to leave the game, "
                                    "you'll have to use `$!leave` again" % getname(message.author)
                                )
                                return
                            if response.content.lower().strip() == 'no':
                                await self.send_message(
                                    message.channel,
                                    "Okay, %s. You will still remain in the game" % getname(message.author)
                                )
                                return
                            elif response.content.lower().strip() == 'yes':
                                await self.send_message(
                                    self.fetch_channel('games'),
                                    "Ending the game. The host, %s, has left" % message.author.mention
                                )
                                return self.dispatch('endgame')
                            await self.send_message(
                                message.channel,
                                "I didn't understand your response. %s, would you"
                                " like to quit your game? (Yes/No)" % message.author.mention
                            )
                    else:
                        try:
                            await self._game_system.on_leave(message.author)
                        except JoinLeaveProhibited:
                            await self.send_message(
                                message.channel,
                                "The current game prohibits players from leaving the game"
                            )
                        except GameEndException:
                            await self.trace()
                            await self.send_message(
                                self.fetch_channel('games'),
                                "Encountered a critical error while removing a player."
                                " The current game will be refunded"
                            )
                            self.dispatch('endgame', 'hard')
                        except:
                            await self.trace()
                            await self.send_message(
                                self.fetch_channel('games'),
                                "Encountered an error while removing a player"
                            )


    @bot.add_command('games')
    async def cmd_games(self, message):
        """
        `$!games` : Lists the available games
        """
        await self.send_message(
            message.channel,
            "\n\n===========\n\n".join(
                "**%s**\n%s" % (
                    system.name,
                    ',   '.join(sorted(
                        '`%s`' % game for game in system.games()
                    ))
                )
                for system in SYSTEMS
            )
        )

    def checker(self, message):
        view = DBView.readonly_view('game', read_persistent=False, game={'user': None})
        return (
            message.channel == self.fetch_channel('games') and
            (not message.content.startswith(self.command_prefix)) and
            view['game']['user'] is not None
        )

    @bot.add_special(checker)
    async def state_router(self, message, content):
        # Routes messages depending on the game state
        # if not allowed:
        async with DBView(game={'user': None}) as db:
            if db['game']['user'] is not None and self._game_system is None:
                await restore_game(self)
            if self._game_system.is_playing(message.author):
                try:
                    await self._game_system.on_input(
                        message.author,
                        message.channel,
                        message
                    )
                except GameEndException:
                    await self.send_message(
                        self.fetch_channel('games'),
                        "The game encountered an irrecoverable error."
                        " I will refund you for the current game"
                    )
                    await self.trace()
                    self.dispatch('endgame', 'hard')
                except:
                    await self.trace(False)
            elif 'restrict' in db['game'] and db['game']['restrict']:
                await self.send_message(
                    message.author,
                    "The current player has disabled comments in the games channel"
                )
                await asyncio.sleep(0.5)
                await message.delete()


    @bot.add_command('toggle-comments')
    async def cmd_toggle_comments(self, message):
        """
        `$!toggle-comments` : Toggles allowing spectator comments in the story_channel
        """
        async with DBView('game', game={'user': None}) as db:
            if db['game']['user'] != message.author.id:
                await self.send_message(
                    message.channel,
                    "You can't toggle comments if you aren't the game host"
                )
            else:
                if 'restrict' not in db['game']:
                    db['game']['restrict'] = True
                else:
                    db['game']['restrict'] = not db['game']['restrict']
                await self.send_message(
                    self.fetch_channel('games'),
                    "Comments from spectators are now %s" % (
                        'forbidden' if db['game']['restrict'] else 'allowed'
                    )
                )

    @bot.add_command('_start', Arg('game', help="The game to play"))
    async def cmd_start(self, message, game):
        """
        `$!_start <game name>` : Starts one of the allowed games
        Example: `$!_start zork1`
        """
        async with DBView('game', game={'user': None}) as db:
            if db['game']['user'] is None:
                games = {
                    game:system
                    for game, sysname, system in listgames()
                }
                if game in games:
                    db['game']['bids'] = [{
                        'user':message.author.id,
                        'game':game,
                        'amount':0
                    }]
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

    @lru_cache(4096)
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
        async with DBView('players') as db:
            if user.id not in db['players']:
                db['players'][user.id] = {
                    'level':1,
                    'xp':0,
                    'balance':10
                }
            player = db['players'][user.id]
            player['xp'] += xp
            current_level = player['level']
            while player['xp'] >= xp_for(player['level']+1):
                player['xp'] -= xp_for(player['level']+1)
                player['level'] += 1
            if player['level'] > current_level and ('active' in db['weekly'][uid] or uid in self._pending_activity):
                await self.send_message(
                    user,
                    "Congratulations on reaching level %d! Your weekly token payout"
                    " and maximum token balance have both been increased. To check"
                    " your balance, type `$!balance`" % player['level']
                )
            db['players'][user.id] = player

    @bot.add_command('balance')
    async def cmd_balance(self, message):
        """
        `$!balance` : Displays your current token balance
        """
        async with DBView('players') as db:
            if message.author.id not in db['players']:
                db['players'][message.author.id] = {
                    'level':1,
                    'xp':0,
                    'balance':10
                }
            player = db['players'][message.author.id]
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
    async def cmd_bid(self, message, amount, game):
        """
        `$!bid <amount> <game>` : Place a bid to play the next game
        Example: `$!bid 1 zork1`
        """
        async with DBView('game', 'players', game={'user': None}) as db:
            if message.author.id == db['game']['user']:
                await self.send_message(
                    message.channel,
                    "You can't bid on a game while you're currently hosting one."
                    " Why not give someone else a turn?"
                )
                return
            games = {
                game:system
                for game, sysname, system in listgames()
            }
            if 'bids' not in db['game']:
                db['game']['bids'] = [{'user': None, 'amount':0, 'game':''}]
            # print(state)
            # print(players)
            # print(bid)
            # print(game)
            if amount <= db['game']['bids'][-1]['amount']:
                if db['game']['bids'][-1]['user'] is not None:
                    await self.send_message(
                        message.channel,
                        "The current highest bid is %d tokens. Your bid must"
                        " be at least %d tokens." % (
                            db['game']['bids'][-1]['amount'],
                            db['game']['bids'][-1]['amount'] + 1
                        )
                    )
                    return
                else:
                    await self.send_message(
                        message.channel,
                        "The minimum bid is 1 token"
                    )
                    return
            if message.author.id not in db['players']:
                db['players'][message.author.id] = {
                    'level':1,
                    'xp':0,
                    'balance':10
                }
            if amount > db['players'][message.author.id]['balance']:
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
            user = self.get_user(db['game']['bids'][-1]['user'])
            if user:
                await self.send_message(
                    user,
                    "You have been outbid by %s with a bid of %d tokens."
                    " If you would like to place another bid, use "
                    "`$!bid %d %s`" % (
                        getname(message.author),
                        bid,
                        bid+1,
                        db['game']['bids'][-1]['game']
                    )
                )
            db['game']['bids'].append({
                'user':message.author.id,
                'amount':amount,
                'game':game
            })
            if db['game']['user'] is None:
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
        Arg('amount', type=int, help="Amount to pay"),
        Arg('pay_type', choices=['xp', 'tokens'], help="Type of payout (xp or tokens)")
    )
    async def cmd_payout(self, message, user, amount, pay_type):
        """
        `$!_payout <user> <amount> <xp/tokens>` : Pays xp/tokens to the provided user
        Example: `$!_payout some_user_id 12 xp`
        """
        async with DBView('players') as db:
            if user.id not in db['players']:
                db['players'][user.id] = {
                    'level':1,
                    'xp':0,
                    'balance':10
                }
            if pay_type == 'tokens':
                db['players'][user.id]['balance'] += amount
            else:
                self.dispatch(
                    'grant_xp',
                    user,
                    amount
                )

    @bot.add_command('reup')
    async def cmd_reup(self, message):
        """
        `$!reup` : Extends your current game session by 1 day
        """
        async with DBView('game', 'players', game={'user':None, 'bids':[]}) as db:
            if 'reup' not in db['game']:
                db['game']['reup'] = 1
            if db['game']['user'] != message.author.id:
                await self.send_message(
                    message.channel,
                    "You are not currently hosting a game"
                )
            elif not (self._game_system is None or self._game_system.played):
                await self.send_message(
                    message.channel,
                    "You should play your game first"
                )
            elif db['players'][db['game']['user']]['balance'] < db['game']['reup']:
                await self.send_message(
                    message.channel,
                    "You do not have enough tokens to extend this session "
                    "(%d tokens)." % db['game']['reup']
                )
            else:
                db['game']['time'] += 86400
                # 1 day + the remaining time
                db['players'][db['game']['user']]['balance'] -= db['game']['reup']
                db['game']['reup'] += 1
                if 'notified' in db['game']:
                    del db['game']['notified']
                await self.send_message(
                    self.fetch_channel('games'),
                    "The current game session has been extended"
                )

    @bot.subscribe('endgame')
    async def end_game(self, evt, hardness='soft'):
        async with DBView('game', 'players', game={'user': None}) as db:
            user = self.get_user(db['game']['user'])
            if user is not None and self._game_system is None or not self._game_system.played:
                await self.send_message(
                    self.fetch_channel('games'),
                    "You quit your game without playing. "
                    "You are being refunded %d tokens" % (
                        db['game']['refund']
                    )
                )
                if user.id not in db['players']:
                    db['players'][user.id] = {
                        'level':1,
                        'xp':0,
                        'balance':10
                    }
                db['players'][user.id]['balance'] += db['game']['refund']
            elif hardness != 'soft':
                await self.send_message(
                    self.fetch_channel('games'),
                    "You are being refunded %d tokens."
                    " I apologize for the inconvenience" % (
                        db['game']['refund']
                    )
                )
                db['players'][user.id]['balance'] += db['game']['refund']
        if hardness != 'critical' and self._game_system is not None:
            try:
                await self._game_system.on_end(user)
            except:
                await self.trace()
                await self.send_message(
                    self.fetch_channel('games'),
                    "I encountered an error while ending the game. "
                    "Scores and payouts may not have been processed. "
                    "If you belive this to be the case, please make a `!bug` report"
                )
        async with DBView('game', game={'user': None}) as db:
            db['game'] = {
                'user': None,
                'bids': db['game']['bids'] if 'bids' in db['game'] else []
            }
            if self._game_system is not None:
                try:
                    await self._game_system.on_cleanup()
                except:
                    await self.trace()
                self._game_system = None
            if 'bids' not in db['game'] or len(db['game']['bids']) <= 1:
                await self.send_message(
                    self.fetch_channel('games'),
                    "The game is now idle and will be awarded to the first bidder"
                )
            else:
                self.dispatch('startgame')

    @bot.subscribe('startgame')
    async def start_game(self, evt):
        print("Starting game")
        async with DBView('game', 'players', game={'user': None}) as db:
            if db['game']['user'] is None:
                for bid in reversed(db['game']['bids']):
                    if bid['user'] is not None:
                        if bid['user'] not in db['players']:
                            db['players'][bid['user']] = {
                                'level':1,
                                'xp':0,
                                'balance':10
                            }
                        user = self.get_user(bid['user'])
                        if bid['amount'] > db['players'][bid['user']]['balance']:
                            await self.send_message(
                                user,
                                "You do not have enough tokens to cover your"
                                " bid of %d. Your bid is forfeit and the game"
                                " shall pass to the next highest bidder" % (
                                    bid['amount']
                                )
                            )
                            continue
                        db['players'][bid['user']]['balance'] -= bid['amount']
                        db['game']['user'] = bid['user']
                        db['game']['restrict'] = False
                        db['game']['game'] = bid['game']
                        db['game']['refund'] = max(0, bid['amount'] - 1)
                        db['game']['time'] = time.time()
                        db['game']['bids'] = [{'user':'', 'amount':0, 'game':''}]
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
                            '`$!invite <user>` : Use this command to invite users to the game.'
                            ' Note that not all games will allow players to join'
                            ' or may only allow players to join at specific times\n'
                            '`$!leave` : Use this command to leave the game.'
                            ' As the host, this will force the game to end\n'
                            '`$!toggle-comments` : Use this command to toggle permissions in the games channel\n'
                            'Right now, anyone can send messages in the channel'
                            ' while you\'re playing. If you use `$!toggle-comments`,'
                            ' nobody but you will be allowed to send messages.'
                            ' Note: even when other users are allowed to send'
                            ' messages, the game will only process messages'
                            ' from users who are actually playing'
                        )
                        await self.send_message(
                            self.fetch_channel('games'),
                            '%s is now playing %s\n'
                            'The game will begin shortly' % (
                                user.mention,
                                bid['game']
                            )
                        )
                        break
            if db['game']['user'] is not None:
                try:
                    print(db['game'])
                    self._game_system = {
                        game:system
                        for game, sysname, system in listgames()
                    }[db['game']['game']](self, db['game']['game'])
                    await self._game_system.on_init()
                    await self._game_system.on_start(user)
                    await self._game_system.on_ready()
                except GameError:
                    await self.send_message(
                        self.fetch_channel('games'),
                        "I was unable to initialize the game. "
                        "The current game will be refunded"
                    )
                    await self.trace()
                    self.dispatch('endgame', 'hard')
                except:
                    await self.send_message(
                        self.fetch_channel('games'),
                        "I was unable to initialize the game. "
                        "The current game will be refunded"
                    )
                    await self.trace()
                    self.dispatch('endgame', 'critical')
                return

            # No bids were honored
            db['game'] = {
                'user': None,
                # 'transcript': [],
                'game': '',
                'reup': 1,
                'bids': [{'user': None, 'amount': 0, 'game': ''}]
            }
            await self.send_message(
                self.fetch_channel('games'),
                "None of the bidders for the current game session could"
                " honor their bids. The game is now idle and will be"
                " awarded to the first bidder"
            )


    @bot.subscribe('command')
    async def record_command(self, evt, command, user):
        async with DBView('weekly') as db:
            if user.id not in db['weekly']:
                db['weekly'][user.id] = {'commands': [], 'active': False}
            # print(week)
            if command not in db['weekly'][user.id]['commands']:
                db['weekly'][user.id]['commands'].append(command)
                # print("granting xp for new command", command)
                self.dispatch(
                    'grant_xp',
                    user,
                    5
                )
            db['weekly'][user.id]['active'] = True

    @bot.subscribe('after:message')
    async def record_activity(self, evt, message):
        if message.author.id != self.user.id:
            self._pending_activity.add(message.author.id)

    @bot.subscribe('cleanup')
    async def save_activity(self, evt):
        async with DBView('weekly') as db:
            # print(week, self._pending_activity)
            for uid in self._pending_activity:
                if uid not in db['weekly']:
                    db['weekly'][uid]={'commands': [], 'active': True}
                else:
                    db['weekly'][uid]['active'] = True
            self._pending_activity = set()

    @bot.add_command('timeleft')
    async def cmd_timeleft(self, message):
        """
        `$!timeleft` : Gets the remaining time for the current game
        """
        async with DBView('game', {'user': None, 'bids': []}) as db:
            if db['game']['user'] is None:
                await self.send_message(
                    message.channel,
                    "Currently, nobody is playing a game"
                )
            else:
                delta = (db['game']['time'] + 172800) - time.time()
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
                        getname(self.get_user(db['game']['user'])),
                        db['game']['game'],
                        d_days,
                        d_hours,
                        d_minutes,
                        d_seconds
                    )
                )

    @bot.add_command('highscore', Arg('game', help="The game to get the highscore of"))
    async def cmd_highscore(self, message, game):
        """
        `$!highscore <game>` : Gets the current highscore for that game
        Example: `$!highscore zork1`
        """
        async with DBView(scores={}) as db:
            if game in db['scores']:
                score, uid = sorted(
                    db['scores'][game],
                    key=lambda x:x[0],
                    reverse=True
                )[0]
                await self.send_message(
                    message.channel,
                    "High score for %s: %d set by %s" % (
                        game,
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
        async with DBView('weekly', 'players') as db:
            print("Resetting the week")
            xp = []
            for uid in db['weekly']:
                user = self.get_user(uid)
                if user is not None:
                    if user.id not in db['players']:
                        db['players'][user.id] = {
                            'level':1,
                            'xp':0,
                            'balance':10
                        }
                    payout = db['players'][user.id]['level']
                    if db['players'][user.id]['balance'] < 20*db['players'][user.id]['level']:
                        payout *= 2
                    elif db['players'][user.id]['balance'] > 100*db['players'][user.id]['level']:
                        payout //= 10
                    db['players'][uid]['balance'] += payout
                    if 'active' in db['weekly'][uid] or uid in self._pending_activity:
                        xp.append([user, 5])
                        #only notify if they were active. Otherwise don't bother them
                        if self.config_get("notify_allowance"):
                            await self.send_message(
                                self.get_user(uid),
                                "Your allowance was %d tokens this week. Your balance is now %d "
                                "tokens" % (
                                    payout,
                                    db['players'][uid]['balance']
                                )
                            )
            self._pending_activity = set()
            db['weekly'] = {}
            for user, payout in xp:
                # print("granting xp for activity payout")
                self.dispatch(
                    'grant_xp',
                    user,
                    payout
                )

    @bot.add_task(1800) # 30 minutes
    async def check_game(self):
        async with DBView('game', game={'user': None, 'bids': []}) as db:
            now = time.time()
            if db['game']['user'] is not None and now - db['game']['time'] >= 172800: # 2 days
                user = self.get_user(db['game']['user'])
                self.dispatch('endgame', user)
                return
            elif db['game']['user'] is not None and now - db['game']['time'] >= 151200: # 6 hours left
                if 'notified' not in db['game'] or db['game']['notified'] == 'first':
                    await self.send_message(
                        self.get_user(db['game']['user']),
                        "Your current game of %s is about to expire. If you wish to extend"
                        " your game session, you can `$!reup` at a cost of %d tokens,"
                        " which will grant you an additional day" % (
                            db['game']['game'],
                            db['game']['reup'] if 'reup' in db['game'] else 1
                        )
                    )
                    db['game']['notified'] = 'second'
            elif (self._game_system is not None and self._game_system.played) and db['game']['user'] is not None and now - db['game']['time'] >= 86400: # 1 day left
                if 'notified' not in db['game']:
                    await self.send_message(
                        self.get_user(db['game']['user']),
                        "Your current game of %s will expire in less than 1 day. If you"
                        " wish to extend your game session, you can `$!reup` at a cost of"
                        " %d tokens, which will grant you an additional day" % (
                            db['game']['game'],
                            db['game']['reup'] if 'reup' in db['game'] else 1
                        )
                    )
                    db['game']['notified'] = 'first'
        if self._game_system is not None:
            try:
                await self._game_system.on_check()
            except:
                await self.trace()
    return bot
