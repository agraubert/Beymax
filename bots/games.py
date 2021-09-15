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

    @bot.add_command('start', Arg('game', help="The game to play"))
    async def cmd_start(self, message, game):
        """
        `$!start <game name>` : Starts one of the allowed games
        Example: `$!start zork1`
        """
        async with DBView('game', game={'user': None}) as db:
            if db['game']['user'] is None:
                games = {
                    game:system
                    for game, sysname, system in listgames()
                }
                if game in games:
                    db['game']['next'] = {
                        'user':message.author.id,
                        'game':game,
                    }
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

    @bot.add_command('balance')
    async def cmd_balance(self, message):
        """
        `$!balance` : Displays your current token balance
        """
        async with DBView('players') as db:
            if message.author.id not in db['players']:
                db['players'][message.author.id] = {
                    'balance':10
                }
            player = db['players'][message.author.id]
            await self.send_message(
                message.author,
                "You have a balance of {} tokens".format(
                    player['balance']
                )
            )

    @bot.add_command(
        '_payout',
        Arg('user', type=UserType(bot), help="Username or ID"),
        Arg('amount', type=int, help="Amount to pay"),
    )
    async def cmd_payout(self, message, user, amount):
        """
        `$!_payout <user> <amount>` : Pays tokens to the provided user
        Example: `$!_payout some_user_id 12`
        """
        async with DBView('players') as db:
            if user.id not in db['players']:
                db['players'][user.id] = {
                    'balance':10
                }
            db['players'][user.id]['balance'] += amount

    @bot.subscribe('endgame')
    async def end_game(self, evt, hardness='soft'):
        if hardness != 'critical' and self._game_system is not None:
            try:
                await self._game_system.on_end(user)
            except:
                await self.trace()
                await self.send_message(
                    self.fetch_channel('games'),
                    "I encountered an error while ending the game. "
                )
        async with DBView('game', game={'user': None}) as db:
            db['game'] = {
                'user': None,
            }
            if self._game_system is not None:
                try:
                    await self._game_system.on_cleanup()
                except:
                    await self.trace()
                self._game_system = None
        await self.send_message(
            self.fetch_channel('games'),
            "This game has ended. Thanks for playing! Anyone may now start a new game"
        )

    @bot.subscribe('startgame')
    async def start_game(self, evt):
        print("Starting game")
        async with DBView('game', 'players', game={'user': None}) as db:
            if db['game']['user'] is None:
                if 'next' in db['game']:
                    bid = db['game']['next'] # legacy naming
                    if bid['user'] is not None:
                        if bid['user'] not in db['players']:
                            db['players'][bid['user']] = {
                                'balance':10
                            }
                        user = self.get_user(bid['user'])
                        db['game']['user'] = bid['user']
                        db['game']['restrict'] = False
                        db['game']['game'] = bid['game']
                        db['game']['time'] = time.time()
                        del db['game']['next']
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
                        "I was unable to initialize the game. Please try again later"
                    )
                    await self.trace()
                    self.dispatch('endgame', 'hard')
                except:
                    await self.send_message(
                        self.fetch_channel('games'),
                        "I was unable to initialize the game. Please try again later"
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
            }
            # We shouldn't really get here these days

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


    @bot.add_task(86400) # 1 day
    async def reset_week(self):
        #{uid: {}}
        async with DBView('players') as db:
            for pid in db['players']:
                if db['players'][pid]['balance'] < 0:
                    db['players'][pid]['balance'] = 1
                else:
                    db['players'][pid]['balance'] += 1

    @bot.add_task(1800) # 30 minutes
    async def check_game(self):
        async with DBView('game', game={'user': None, 'bids': []}) as db:
            now = time.time()
            if db['game']['user'] is not None and now - db['game']['time'] >= 172800: # 2 days
                user = self.get_user(db['game']['user'])
                self.dispatch('endgame', user)
                return
        if self._game_system is not None:
            try:
                await self._game_system.on_check()
            except:
                await self.trace()
    return bot
