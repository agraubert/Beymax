import asyncio
import json
import random
from itertools import permutations, groupby
from ..base import GameSystem, GameError, Phase

class PokerError(GameError):
    """
    For poker-specific errors
    """
    pass

class NotEnoughCards(PokerError):
    """
    The deck did not have enough cards to deal
    """
    pass

def strike_if(text, condition):
    return '\n'+ (text if condition else '~~'+text+'~~')

class Card(object):
    """
    Object representing generic playing card
    """
    RANKS = [
        'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
        'nine', 'ten', 'jack', 'queen', 'king', 'ace'
    ]
    SUITS = ['clubs', 'diamonds', 'hearts', 'spades']
    R_REPR = [
        '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'
    ]
    S_REPR = ['C', 'D', 'H', 'S']

    def __init__(self, rank, suit=None):
        if suit is None:
            suit = self.SUITS[
                self.S_REPR.index(rank[-1])
            ]
            rank = self.RANKS[
                self.R_REPR.index(rank[:-1])
            ]
        self.rank = rank
        self.suit = suit
        self.rank_value = self.RANKS.index(self.rank)
        self.suit_value = self.SUITS.index(self.suit)

    def __lt__(self, other):
        if self.rank_value != other.rank_value:
            return self.rank_value < other.rank_value
        if self.suit_value != other.suit_value:
            return self.suit_value < other.suit_value
        return False

    def __eq__(self, other):
        return self.rank_value == other.rank_value and self.suit_value == other.suit_value

    def __repr__(self):
        return '%s%s' % (
            self.R_REPR[self.rank_value],
            self.S_REPR[self.suit_value]
        )

    def demoted_ace(self):
        copy = Card(self.rank, self.suit)
        if copy.rank == 'ace':
            copy.rank_value = -1
        return copy


class PokerRank(object):
    POKER_RANKS = [
        'high',
        'pair',
        'two-pair',
        'three',
        'straight',
        'flush',
        'full-house',
        'four',
        'straight-flush',
        'royal-flush'
    ]
    def __init__(self, rank, high, *cards):
        self.rank = rank
        self.high = high
        self.cards = sorted(cards)

    def __eq__(self, other):
        if self.rank != other.rank:
            return False
        if self.high != other.high:
            return False
        if len(self.cards) != len(other.cards):
            return False
        for cardA, cardB in zip(self.cards, other.cards):
            if cardA != cardB:
                return False

        return True

    @property
    def display(self):
        return '%s: %s (%s high)' % (
            self.rank,
            Hand(self.cards).display,
            repr(self.high)
        )

    def __lt__(self, other):
        s = self.POKER_RANKS.index(self.rank)
        o = self.POKER_RANKS.index(other.rank)
        if s != o:
            return s < o
        for cardA, cardB in zip(self.cards, other.cards):
            if cardA != cardB:
                return cardA < cardB
        if self.high != other.high:
            return self.high < other.high
        return len(self.cards) < len(other.cards)



class Hand(object):
    def __init__(self, cards=None):
        self.cards = cards if cards is not None else []

    def __repr__(self):
        return '<HAND: %s>' % self.display

    @property
    def display(self):
        return ', '.join(repr(card) for card in self.cards)

    def __len__(self):
        return len(self.cards)

    def __getitem__(self, i):
        return self.cards[i]

    def discard(self):
        self.cards = []

    def __iadd__(self, other):
        if isinstance(other, Hand):
            self.cards += other.cards
        elif isinstance(other, Card):
            self.cards.append(other)
        elif isinstance(other, list):
            self.cards += other
        else:
            return NotImplemented
        return self

    @property
    def ordered_cards(self):
        return sorted(self.cards)

    def __lt__(self, other):
        for cardA, cardB in zip(self.ordered_cards, other.ordered_cards):
            if cardA != cardB:
                return cardA < cardB
        return len(self.cards) < len(other.cards)

    def __eq__(self, other):
        if len(self.cards) != len(other.cards):
            return False
        for cardA, cardB in zip(self.ordered_cards, other.ordered_cards):
            if cardA != cardB:
                return False
        return True

    @property
    def is_straight(self):
        last_card = None
        for card in self.ordered_cards:
            if last_card is None:
                last_card = card
            elif last_card.rank_value + 1 != card.rank_value and not (card.rank == 'ace' or last_card.rank == 'ace'):
                return False
        last_card = None
        for card in sorted(card.demoted_ace() for card in self.cards):
            if last_card is None:
                last_card = card
            elif last_card.rank_value + 1 != card.rank_value:
                return False
        return True

    @property
    def poker_rank(self):
        if len(self.cards) > 5:
            return sorted(
                Hand(permutation).poker_rank
                for permutation in permutations(self.cards, 5)
            )[-1]
        cards = self.ordered_cards
        rank_groups = {
            value:[*group]
            for value, group in groupby(self.cards, key=lambda card:card.rank_value)
        }
        suit_groups = {
            value:[*group]
            for value, group in groupby(self.cards, key=lambda card:card.suit_value)
        }
        if len(suit_groups) == 1:
            # Definitely a flush, may be a royal flush or straight flush
            if cards[-1].rank == 'ace' and cards[0].rank == 'ten':
                return PokerRank(
                    'royal-flush',
                    cards[-1],
                    *cards
                )
            if self.is_straight:
                return PokerRank(
                    'straight-flush',
                    cards[-1],
                    *cards
                )
        threes = []
        pairs = []
        for v, g in sorted(rank_groups.items(), key=lambda x:x[0], reverse=True):
            if len(g) == 4:
                return PokerRank(
                    'four',
                    cards[-1],
                    *g
                )
            elif len(g) == 3:
                threes.append((v,g))
            elif len(g) == 2:
                pairs.append((v,g))
        if len(threes) and len(pairs):
            # full house
            return PokerRank(
                'full-house',
                cards[-1],
                *cards
            )
        if len(suit_groups) == 1:
            return PokerRank(
                'flush',
                cards[-1],
                *cards
            )
        if self.is_straight:
            return PokerRank(
                'straight',
                cards[-1],
                *cards
            )
        if len(threes):
            return PokerRank(
                'three',
                cards[-1],
                *threes[0][1]
            )
        if len(pairs) > 1:
            pair_keys = sorted(pairs, key=lambda x:x[0])
            return PokerRank(
                'two-pair',
                cards[-1],
                *rank_groups[pair_keys[-1][0]],
                *rank_groups[pair_keys[-2][0]]
            )
        if len(pairs):
            return PokerRank(
                'pair',
                cards[-1],
                *pairs[0][1]
            )
        return PokerRank(
            'high',
            cards[-1],
            cards[-1],
        )




class Deck(Hand):

    def __repr__(self):
        return '<DECK: %s>' % ', '.join(repr(card) for card in self.cards)

    def shuffle(self):
        self.cards.sort(key=lambda card:random.random())

    def deal(self, n=1):
        if len(self.cards) >= n:
            output = [card for card in self.cards[:n]]
            self.cards = self.cards[n:]
            return output
        raise NotEnoughCards("The deck only has %d of the requested %d cards" % (len(self.cards), n))

    def fill(self, other, shuffle=True):
        self += other
        if shuffle:
            self.shuffle()

    def dump(self, filename):
        with open(filename, 'w') as w:
            json.dump(
                [repr(card) for card in self.cards],
                w
            )

    def load(self, filename):
        with open(filename) as r:
            self.cards = [
                Card(card)
                for card in json.load(r)
            ]

    def all_cards(self, shuffle=True):
        self.cards = [
            Card(rank, suit) for suit in Card.SUITS
            for rank in Card.RANKS
        ]
        if shuffle:
            self.shuffle()

class FreePhase(Phase):
    async def on_join(self, user):
        self.game.players.append(user)
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            '%s has joined the game' % user.mention
        )
        return True

    async def on_leave(self, user):
        self.game.players.remove(user)
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            '%s has left the game' % user.mention
        )
        return True

class NoJoinPhase(FreePhase):
    async def on_join(self, user):
        return False

class LockedPhase(NoJoinPhase):
    async def on_leave(self, user):
        return False
