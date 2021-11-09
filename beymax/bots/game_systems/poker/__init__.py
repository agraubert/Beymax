import discord
import asyncio
import random
import json
import os
from ....utils import DBView, getname
from ..base import GameEndException, PhasedGame
from .utils import Card, Hand, Deck, PokerError
from .texas_hold_em import __GAME_DEF as texas, __RESTORE as texas_restore
from .blackjack import __GAME_DEF as blackjack, __RESTORE as blackjack_restore

class PokerSystem(PhasedGame):
    """
    This is a lightweight class
    Most of it's function is conducted by the various phases
    It handles restoring the game state and setting up the initial phase
    It also handles small things like greetings or fallback messages
    """
    name = "Poker"
    GAMES = {
        **texas,
        **blackjack
    }
    def __init__(self, bot, game):
        super().__init__(
            bot,
            game,
            **self.GAMES[game]
        )
        self.host = None
        self.ante = 0
        self.inactive_players = set()
        self.pot = 0
        self.index = 1
        self.bet = -1
        self.refund = {}
        self.bets = {} # bets paid current round
        self.square = set() # Players square with current bet
        self.dealer = 0
        self.was_played = False
        self.hands = {}
        self.table = Hand()
        self.deck = Deck()
        self.trash = Deck()
        self.deck.all_cards(True)

    @classmethod
    def games(cls):
        return [*cls.GAMES]

    @property
    def played(self):
        return self.was_played

    def player_at(self, i):
        """
        Returns the player i positions after the dealer, skipping inactive players
        """
        idx = (self.dealer + i) % len(self.players)
        for x in range(len(self.players)):
            if self.players[(x + idx) % len(self.players)].id not in self.inactive_players:
                return self.players[(x + idx) % len(self.players)]
        raise PokerError("All players inactive")

    async def save_state(self):
        async with DBView('poker') as db:
            db['poker'].update({
                'players': [player.id for player in self.players],
                'inactive_players': [player_id for player_id in self.inactive_players],
                'dealer': self.dealer,
                'host': self.host.id,
                'deck': [repr(card) for card in self.deck.cards],
                'trash': [repr(card) for card in self.trash.cards],
                'pot': self.pot,
                'refunds': self.refund,
                'hands': {
                    player_id:[repr(card) for card in hand]
                    for player_id, hand in self.hands.items()
                },
                'table': [repr(card) for card in self.table]
            })

    async def do_refund(self):
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "Issuing refunds..."
        )
        async with DBView('players') as db:
            for player, amount in self.refund.items():
                if player not in db['players']:
                    db['players'][player] = {
                        'balance':10
                    }
                db['players'][player]['balance'] += amount
                self.pot = max(self.pot - amount, 0)

    @classmethod
    async def restore(cls, bot, game):
        async with DBView(poker = {}) as db:
            if 'players' not in db['poker']:
                raise GameEndException("No data to restore")
            poker_game = PokerSystem(bot, game)
            poker_game.players = [
                bot.get_user(player_id) for player_id in db['poker']['players']
            ]
            poker_game.inactive_players = set(db['poker']['inactive_players'])
            poker_game.dealer = db['poker']['dealer']
            poker_game.host = bot.get_user(db['poker']['host'])
            poker_game.deck = Deck([
                Card(card) for card in db['poker']['deck']
            ])
            poker_game.trash = Deck([
                Card(card) for card in db['poker']['trash']
            ])
            poker_game.pot = db['poker']['pot']
            poker_game.refund = db['poker']['refunds']
            poker_game.hands = {
                player_id: Hand([
                    Card(card) for card in hand
                ])
                for player_id, hand in db['poker']['hands'].items()
            }
            poker_game.table = Hand([
                Card(card) for card in db['poker']['table']
            ])
            poker_game.was_played = True
            return poker_game

    async def on_restore(self, host):
        self.host = host
        if not self.is_playing(host):
            self.players.append(host)
        if self.game == 'Texas-Hold-em':
            return await texas_restore(self, host)
        elif self.game == 'Blackjack':
            return await blackjack_restore(self, host)
        else:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "The current game is invalid. Unable to restore state"
            )
            self.bot.dispatch('endgame', 'critical')

    def advance_index(self):
        """
        Advances the player index around the table
        """
        # for i in range(len(self.layers)):
        #     player = self.game.players[(self.index + i) % len(self.game.players)]
        #     if player.id not in self.game.inactive_players:
        #         self.index = (self.index + i) % len(self.game.players)
        #         return player
        # raise PokerError("All players inactive")
        self.index = (self.index + 1) % len(self.players)
        return self.player_at(self.index)

    async def on_start(self, host):
        self.host = host
        if not self.is_playing(host):
            self.players.append(host)

    async def on_end(self, *args, **kwargs):
        if sum(v for v in self.refund.values()) > 0:
            await self.do_refund()
        # clean game end

    async def on_ready(self):
        if self.active_phase is None:
            await self.enter_phase('pregame')

    async def on_cleanup(sefl):
        await DBView.overwrite(poker={})

class SidePot(object):
    """
    Used to represent a specific side pot in a poker game
    """
    def __init__(self, parent, num):
        self.parent = parent # The parent gamepots object
        self.num = num
        self.players = set() # player ids
        self.value = 0
        self.bets = {} # id: value mappings for unfinalized bets this round

    def exclude(self, value):
        db = DBView.readonly_view('players')
        balances = {
            player: db['players'][player]['balance'] if player in db['players'] else 10
            for player in self.players
        }
        pot = self.parent.new_pot()
        pot.players |= {
            player for player, balance in balances.items()
            if balance > value
        }
        return pot

    def consume(self):
        """
        Consumes the active bets
        """
        self.bets = {}

    def __getitem__(self, player):
        return self.bets[player]

    def update_bet(self, player, value):
        """
        Update a player's bet.
        If bet his higher than capacity, issue a new side pot.
        """
        assert value>0, "Bets must be positive"
        if value > cap:
            side_value = value - cap
            value = cap
            side_pot = self.exclude(value)
            side_pot.update_bet(player, side_value)
        self.bets[player] += value
        self.value += value

    @property
    def maxbet(self):
        return max(self.bets.values())

    def remainder(self, player):
        """
        Get amount left for the current player to square with the current
        bet in this pot
        """
        return self.bets[player] - self.maxbet

    def get_capacity(self):
        """
        Gets the maximum bet this pot can take before splitting a side pot
        """
        db = DBView.readonly_view('players')
        return min(
            db['players'][player]['balance'] if player in db['players'] else 10
            for player in self.players
        )


class GamePots(object):
    """
    Fancy List object for Side Pots
    """

    def __init__(self):
        self.pots = []

    @property
    def sum(self):
        return sum(pot.value for pot in self.pots)

    def new_pot(self):
        self.pots.append(SidePot(self, len(self.pots)))
        return self.pots[-1]

    def get_participating(self, player):
        return [
            pot
            for pot in self.pots
            if player in pot.players
        ]

    def get_latest(self, player):
        return self.get_participating(player)[-1]

    def get_call(self, player):
        return sum(
            pot.remainder(player)
            for pot in self.pots
        )

    def distribute_bet(self, player, value):
        pots = self.get_participating(player)
        for pot in pots[:-1]:
            r = pot.remainder(player)
            value -= r
            if value < 0:
                raise PokerError("huh?")
            pot.update_bet(player, r)
        if value > 0:
            new = pots[-1].update_bet(player, value)
