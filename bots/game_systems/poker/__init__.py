import discord
import asyncio
import random
import json
import traceback
import os
from ...utils import Database, load_db, getname
from ..base import GameEndException, PhasedGame
from .utils import Card, Hand, Deck, PokerError
from .texas_hold_em import __GAME_DEF as texas, __RESTORE as texas_restore
from .blackjack import __GAME_DEF as blackjack, __RESTORE as blackjack_restore

# /Users/agraubert/Documents/beymax/bots/game_systems/base.py:448: RuntimeWarning: coroutine 'NoJoinPhase.on_join' was never awaited
# Rotation of turn order is odd
# Two pair just shows one card from each pair
# Turn prompts show up twice on error

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
        self.bidder = None
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
            if self.players[x + idx].id not in self.inactive_players:
                return self.players[x + idx]
        raise PokerError("All players inactive")

    async def save_state(self):
        async with Database('poker.json') as poker:
            poker.update({
                'players': [player.id for player in self.players],
                'inactive_players': [player_id for player_id in self.inactive_players],
                'dealer': self.dealer,
                'bidder': self.bidder.id,
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
            poker.save()

    async def do_refund(self):
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "Issuing refunds..."
        )
        async with Database('players.json') as players:
            for player, amount in self.refund.items():
                if player not in players:
                    players[player] = {
                        'level':1,
                        'xp':0,
                        'balance':10
                    }
                players[player]['balance'] += amount
            players.save()

    @classmethod
    async def restore(cls, bot, game):
        async with Database('poker.json') as poker:
            if 'players' not in poker:
                raise GameEndException("No data to restore")
            poker_game = PokerSystem(bot, game)
            poker_game.players = [
                bot.get_user(player_id) for player_id in poker['players']
            ]
            poker_game.inactive_players = set(poker['inactive_players'])
            poker_game.dealer = poker['dealer']
            poker_game.bidder = bot.get_user(poker['bidder'])
            poker_game.deck = Deck([
                Card(card) for card in poker['deck']
            ])
            poker_game.trash = Deck([
                Card(card) for card in poker['deck']
            ])
            poker_game.pot = poker['pot']
            poker_game.refund = poker['refunds']
            poker_game.hands = {
                player_id: Hand([
                    Card(card) for card in hand
                ])
                for player_id, hand in poker['hands'].items()
            }
            poker_game.table = Hand([
                Card(card) for card in poker['table']
            ])
            poker_game.was_played = True
            return poker_game

    async def on_restore(self, bidder):
        self.bidder = bidder
        if not self.is_playing(bidder):
            self.players.append(bidder)
        if self.game == 'Texas-Hold-em':
            return await texas_restore(self, bidder)
        elif self.game == 'Blackjack':
            return await blackjack_restore(self, bidder)
        else:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "The current game is invalid. Unable to restore state"
            )
            self.bot.dispatch('endgame', 'critical')

    def advance_index(self):
        # for i in range(len(self.layers)):
        #     player = self.game.players[(self.index + i) % len(self.game.players)]
        #     if player.id not in self.game.inactive_players:
        #         self.index = (self.index + i) % len(self.game.players)
        #         return player
        # raise PokerError("All players inactive")
        self.index = (self.index + 1) % len(self.players)
        return self.player_at(self.index)

    async def on_start(self, bidder):
        self.bidder = bidder
        if not self.is_playing(bidder):
            self.players.append(bidder)

    async def on_end(self, *args, **kwargs):
        if sum(v for v in self.refund.values()) > 0:
            await self.do_refund()
        # clean game end

    async def on_ready(self):
        if self.active_phase is None:
            await self.enter_phase('pregame')

    async def on_cleanup(sefl):
        if os.path.exists('poker.json'):
            os.remove('poker.json')
