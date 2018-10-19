import discord
import asyncio
import random
import json
from itertools import permutations, groupby
from ..utils import Database, load_db, getname
from .base import GameSystem, GameError, JoinLeaveProhibited, GameEndException, Phase, PhasedGame

# FIXME /Users/agraubert/Documents/beymax/bots/game_systems/base.py:448: RuntimeWarning: coroutine 'NoJoinPhase.on_join' was never awaited
# FIXME Rotation of turn order is odd
# FIXME Two pair just shows one card from each pair
# FIXME Invite/Args broken, not accepting fullnames
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
        return '<%s: %s (%s high)>' % (
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
                rank_groups[pair_keys[-1][0]][0],
                rank_groups[pair_keys[-2][0]][0]
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

class PreGame(FreePhase):
    """
    This phase represents the standby period before a game starts
    Players may freely leave and join while the host sets the ante
    As soon as the host sets the ante, it advances to beforeRound
    This should be registered as the default phase
    """

    async def on_join(self, user):
        await super().on_join(user)
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "%s, please specify the ante: " % getname(self.game.bidder)
        )

    async def before_phase(self):
        await self.set_player(self.game.bidder)
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "The game is about to start."
            " You may invite other players (and players may now leave)."
            " When the host specifies the ante, the game will begin."
            " Please specify the ante:"
        )

    async def on_turn_input(self, user, channel, message):
        try:
            self.game.ante = int(message.content.lower().replace('tokens', '').strip())
            if self.game.ante < 0:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "That is not a valid amount. "
                    "Please specify the ante as a non-negative integer:"
                )
            else:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "Okay. The ante is now %d tokens per hand" % self.game.ante
                )
                await self.game.enter_phase('beforeRound')
        except ValueError:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "I couldn't interpret that amount. "
                "Please specify the ante as a non-negative integer:"
            )

class BeforeRound(LockedPhase):
    """
    This is a computational phase to deduct antes and get the final player list.
    It iterates through players, charging them for the ante.
    If there are not at least two players by the end of this phase, it feeds into refund
    Otherwise, it feeds into deal
    """
    # Phase locked as it's entirely a computational phase.
    # No input is handled, so it's unreasonable to expect users to leave
    async def before_phase(self):
        async with Database('players.json') as players:
            for user in self.game.players:
                if user.id not in players:
                    players[user.id] = {
                        'level':1,
                        'xp':0,
                        'balance':10
                    }
                if players[user.id]['balance'] < self.game.ante:
                    self.game.inactive_players.add(user.id)
                else:
                    players[user.id]['balance'] -= self.game.ante
                    self.game.pot += self.game.ante
                    self.game.refund[user.id] = self.game.ante
            players.save()
        if len(self.game.inactive_players):
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "The following players could not afford the ante, and will sit"
                " this round out: %s" % (', '.join(
                    getname(self.bot.get_user(user))
                    for user in self.game.inactive_players
                ))
            )
        if len([player for player in self.game.players if player.id not in self.game.inactive_players]) <= 1:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "There are not enough players in the game to continue."
                " Refunding the ante, and restarting..."
            )
            await self.game.enter_phase('refund')
        else:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "Ante has been collected. There are %d players in the game and %d tokens in the pot" % (
                    len([player for player in self.game.players if player.id not in self.game.inactive_players]),
                    self.game.pot
                )
            )
            await self.game.save_state()
            await self.game.enter_phase('deal')


# FIXME: Somehow specify next phase
class BettingPhase(LockedPhase):
    """
    This is a generic phase in which bets are taken from each player during their turn
    """
    async def after_phase(self):
        await self.game.save_state()
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "The pot is now %d tokens" % self.game.pot
        )
        self.game.index = 0
        self.game.bets = {}
        self.game.square = set()
        self.game.bet = -1
        print(self.game.hands)

    async def advance_if(self, bet, cost):
        """
        This function inspects the current bet and the cost paid by the current player
        If it determines that betting must continue, it advances to the next turn
        Otherwise, it calls determine_route to change phase
        """
        # Actually, just check square
        remaining_players = ({player.id for player in self.game.players} - self.game.inactive_players) - self.game.square
        if len(remaining_players):
            await self.set_player(self.game.advance_index())
        else:
            await self.determine_route()

    async def determine_route(self):
        """
        This function determines the next state to enter
        """
        async with Database('players.json') as players:
            balances = {
                player.id: players[player.id]['balance']
                for player in self.game.players
                if (player.id in players and player.id not in self.game.inactive_players)
            }
        print(balances)
        if len([pid for pid, bal in balances.items() if bal]) <= 1:
            await self.game.enter_phase('win')
        else:
            await self.game.enter_phase(self.next_phase)

    async def next_turn(self, new, old):
        call = self.game.bet if new.id not in self.game.bets else self.game.bet - self.game.bets[new.id]
        if self.game.bet != -1:
            msg = (
                "The current bet is %d tokens\n"
                "You'll pay %d tokens to call the bet" % (
                    self.game.bet,
                    call
                )
            )
        else:
            msg = "Currently, there is not bet"
        async with Database('players.json') as players:
            if new.id not in players:
                players[new.id] = {
                    'level':1,
                    'xp':0,
                    'balance':10
                }
                players.save()
            balance = players[new.id]['balance']

        msg += '\nYou have %d tokens' % balance
        msg += '\nActions:'
        if self.game.bet == -1:
            msg += strike_if(
                '`bet <amount>` (At least one token)',
                balance >= 1
            )
            msg += '\n`check` (Free)'
        else:
            msg += strike_if(
                '`raise <amount to raise by>` (Raise by at least one token, '
                'costs you at least %d tokens)' % (call + 1),
                balance > call
            )
            msg += strike_if(
                '`call` (Costs %d tokens)%s' % (
                    call,
                    ' (ALL IN)' if balance < call else ''
                ),
                True, #balance >= 1,

            )
        msg += '\n`fold` (Free)'
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            msg
        )

    async def on_turn_input(self, user, channel, message):
        content = message.content.lower().strip().split()
        call = self.game.bet if user.id not in self.game.bets else self.game.bet - self.game.bets[user.id]
        async with Database('players.json') as players:
            balance = players[user.id]['balance']
        if len(content) < 1 or content[0] not in {'bet', 'check', 'raise', 'call', 'fold'}:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "Please provide a valid action"
            )
            await self.next_turn(user, None)
        elif content[0] == 'bet' and self.game.bet == -1:
            if len(content) != 2:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to bet"
                )
                await self.next_turn(user, None)
            try:
                cost = int(content[1])
            except ValueError:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to bet"
                )
                await self.next_turn(user, None)
            if cost < 1:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to bet"
                )
                await self.next_turn(user, None)
            elif cost > balance:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You do not have enough tokens to make that bet"
                )
            else:
                async with Database('players.json') as players:
                    players[user.id]['balance'] -= cost
                    players.save()
                if user.id in self.game.bets:
                    self.game.bets[user.id] += cost
                else:
                    self.game.bets[user.id] = cost
                self.game.pot += cost
                self.game.refund[user.id] += cost
                self.game.bet = cost
                self.game.square = {user.id} # new bet, so only the current user is square
                return await self.advance_if(self.game.bet, cost)

        elif content[0] == 'check' and self.game.bet <= 0:
            self.game.bets[user.id] = 0
            self.game.square.add(user.id) # User was allowed to check, so they're square
            return await self.advance_if(self.game.bet, 0)
        elif content[0] == 'raise' and self.game.bet > 0:
            if len(content) != 2:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to raise by"
                )
                await self.next_turn(user, None)
            try:
                raise_amt = int(content[1])
                cost = raise_amt + call
            except ValueError:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to raise by"
                )
                await self.next_turn(user, None)
            if cost < 1:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to raise by"
                )
                await self.next_turn(user, None)
            elif cost > balance:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You do not have enough tokens to raise by that much"
                )
            else:
                async with Database('players.json') as players:
                    players[user.id]['balance'] -= cost
                    players.save()
                if user.id in self.game.bets:
                    self.game.bets[user.id] += cost
                else:
                    self.game.bets[user.id] = cost
                self.game.pot += cost
                self.game.refund[user.id] += cost
                self.game.bet += raise_amt
                self.game.square = {user.id} # Raised, so only this user is square
                return await self.advance_if(self.game.bet, cost)
        elif content[0] == 'call' and self.game.bet > 0:
            cost = min(call, balance)
            async with Database('players.json') as players:
                players[user.id]['balance'] -= cost
                players.save()
                if user.id in self.game.bets:
                    self.game.bets[user.id] += cost
                else:
                    self.game.bets[user.id] = cost
                self.game.pot += cost
                self.game.refund[user.id] += cost
            if cost == balance and balance != 0:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    '%s is now all-in' % user.mention
                )
            self.game.square.add(user.id) # user called, so they're square
            return await self.advance_if(self.game.bet, cost)
        elif content[0] == 'fold':
            self.game.inactive_players.add(user.id)
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                '%s has folded' % user.mention
            )
            return await self.advance_if(self.game.bet, 0)
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "That action is invalid"
        )
        await self.next_turn(user, None)


class Deal(BettingPhase):
    """
    This is the initial game phase.
    Players are each dealt 2 cards
    After the dealing (before_phase) it conducts betting inheritted from BettingPhase
    At the end of this phase, if there are at least two players who have not folded or gone all-in, this feeds to Flop
    Otherwise, this feeds to Win
    """
    next_phase = 'flop'
    async def before_phase(self):
        self.game.was_played = True
        self.game.bets = {}
        self.game.square = set()
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "Players can no longer join or leave until the end of the round."
            " Each player is being dealt cards. Check your DMs for your hand"
        )
        for i in range(len(self.game.players)):
            player = self.game.players[(self.game.dealer + i) % len(self.game.players)]
            if player.id not in self.game.inactive_players:
                if len(self.game.deck) < 2:
                    self.game.deck.fill(self.game.trash)
                    self.game.trash.cards = []
                self.game.hands[player.id] = Hand(self.game.deck.deal(2))
                await self.bot.send_message(
                    player,
                    "Your hand is: " + self.game.hands[player.id].display
                )
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "All hands have been dealt. Place your bets!"
        )
        await self.set_player(self.game.advance_index())

class Flop(BettingPhase):
    """
    This is the second game phase.
    3 Cards are dealt to the table
    After the dealing (before_phase) it conducts betting inheritted from BettingPhase
    At the end of this phase, if there are at least two players who have not folded or gone all-in, this feeds to Turn
    Otherwise, this feeds to Win
    """
    next_phase = 'turn'
    async def before_phase(self):
        if len(self.game.deck) < 3:
            self.game.deck.fill(self.game.trash)
            self.game.trash.cards = []
        self.game.table += self.game.deck.deal(3)
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "Here comes the flop: **%s**. Place your bets!" % self.game.table.display
        )
        await self.set_player(self.game.advance_index())

class Turn(BettingPhase):
    """
    This is the third game phase.
    1 card is dealt to the table
    After the dealing (before_phase) it conducts betting inheritted from BettingPhase
    At the end of this phase, if there are at least two players who have not folded or gone all-in, this feeds to River
    Otherwise, this feeds to Win
    """
    next_phase = 'river'
    async def before_phase(self):
        if len(self.game.deck) < 1:
            self.game.deck.fill(self.game.trash)
            self.game.trash.cards = []
        self.game.table += self.game.deck.deal(1)
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "Here's the turn: **%s**. Place your bets!" % self.game.table.display
        )
        await self.set_player(self.game.advance_index())

class River(BettingPhase):
    """
    This is the final game phase.
    1 card is dealt to the table
    After the dealing (before_phase) it conducts betting inheritted from BettingPhase
    At the end of this phase, this feeds to Win
    """
    # FIXME: I *thinK* that by setting the advancement phase to WIN, this should
    # integrate seamlessly with BettingPhase.determine_route
    next_phase = 'win'
    async def before_phase(self):
        if len(self.game.deck) < 1:
            self.game.deck.fill(self.game.trash)
            self.game.trash.cards = []
        self.game.table += self.game.deck.deal(1)
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "And here's the river: **%s**. Last chance for betting" % self.game.table.display
        )
        await self.set_player(self.game.advance_index())

class WinPhase(LockedPhase):
    """
    This phase represents the natural end of the game
    The hands of all active players are compared,
    and the pot is split evenly between the hands tied for best
    This writes the results back into the player database and feeds into the reset state
    * Reset refund to {} (refunds no longer necessary after pot is paid back)
    * Reset the pot to 0
    """
    async def before_phase(self):
        effective_hands = {
            player.id:Hand(self.game.hands[player.id].cards + self.game.table.cards)
            for player in self.game.players
            if player.id in self.game.hands
        }
        winning_ranks = {
            player_id:hand.poker_rank
            for player_id, hand in effective_hands.items()
        }
        best_rank = sorted(
            [
                player_id for player_id in winning_ranks
                if player_id not in self.game.inactive_players
            ],
            key=lambda player_id:winning_ranks[player_id],
            reverse=True
        )[0]
        winners = {
            player_id for player_id, hand in winning_ranks.items()
            if hand == winning_ranks[best_rank] and player_id not in self.game.inactive_players
        }
        player_hands = '\n'.join(
            "%s : `%s` -> %s" % (
                getname(self.bot.get_user(player_id)),
                hand.display,
                winning_ranks[player_id].display
            )
            for player_id, hand in self.game.hands.items()
        )
        await self.bot.send_message(
            self.bot.fetch_channel("games"),
            "Everyone, flip your cards!\n"
            "`%s` on the table,\n"
            "%s\n----------\n"
            "And the winner%s:\n"
            "%s\n"
            "Congratulations!" % (
                self.game.table.display,
                player_hands,
                ' is' if len(winners) <= 1 else 's are',
                ', '.join(
                    self.bot.get_user(player_id).mention
                    for player_id in winners
                )
            )
        )
        payout = self.game.pot // len(winners)
        leftover = self.game.pot % len(winners)
        self.game.pot = leftover
        self.game.refund = {}
        if leftover:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "There was a leftover balance of %d tokens"
                " which could not be evenly paid to the winners."
                " This balance will stay in the pot for the next round, "
                "or will be refunded to the host (if they end the game)" % leftover
            )
            self.game.refund[self.game.bidder.id] = leftover
        async with Database('players.json') as players:
            for winner in winners:
                if winner not in players:
                    players[winner] = {
                        'level':1,
                        'xp':0,
                        'balance':10
                    }
                players[winner]['balance'] += payout
            players.save()
        # XP payout?
        # base - penalty + bonus
        # 25 - {15 if inactive} + {2.5*payout if winner}
        for player in self.game.players:
            xp = 25
            if player.id in self.game.inactive_players:
                xp -= 15
            if player.id in winners:
                xp += int(2.5 * payout) + leftover
            self.bot.dispatch(
                'grant_xp',
                player,
                xp
            )
        await self.game.enter_phase('reset')

    async def after_phase(self):
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "Thank you all for playing. Please wait while I set up another round"
        )

class ResetPhase(LockedPhase):
    """
    This phase resets the game for another round:
    * Advance the dealer index by 1
    * Reset the player index to 0
    * Reset inactive players to set()
    * Reset ante to 0
    * Empty hands and table into trash deck
    * save the player list, dealer index, bidder, deck, and trash to poker.json
    """

    async def before_phase(self):
        self.game.dealer = (self.game.dealer + 1) % len(self.game.players)
        self.game.index = 0
        self.game.inactive_players = set()
        self.game.ante = 0
        self.game.trash += self.game.table.cards
        self.game.table = Hand()
        for hand in self.game.hands.values():
            self.game.trash += hand.cards
        self.game.hands = {}
        await self.game.enter_phase('pregame')

    async def after_phase(self):
        await self.game.save_state()

class RefundPhase(LockedPhase):
    """
    This phase is a fallback state if there aren't enough players after the host
    sets the ante.
    It refunds players their ante (and updates the player database) then feeds into reset
    """
    async def before_phase(self):
        await self.game.do_refund()
        await self.game.save_state()
        await self.game.enter_phase('reset')

class PokerSystem(PhasedGame):
    """
    This is a lightweight class
    Most of it's function is conducted by the various phases
    It handles restoring the game state and setting up the initial phase
    It also handles small things like greetings or fallback messages
    """
    name = "Poker"
    def __init__(self, bot, game):
        print("Initializing Super PhasedGame")
        super().__init__(
            bot,
            game,
            reset=ResetPhase,
            deal=Deal,
            flop=Flop,
            turn=Turn,
            river=River,
            win=WinPhase,
            refund=RefundPhase,
            pregame=PreGame,
            beforeRound=BeforeRound,
            default=PreGame
        )
        print("Initializing PokerSystem")
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
        return [
            'Texas-Hold-em'
        ]

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
        tlen = len(self.table)
        if tlen == 5:
            await self.enter_phase('win')
        elif tlen == 4:
            await self.enter_phase('river')
        elif tlen == 3:
            await self.enter_phase('turn')
        elif tlen == 0 and len(self.hands) > 1:
            await self.enter_phase('flop')
        elif tlen == 0 and len(self.hands) == 0:
            await self.enter_phase('deal')
        else:
            await self.bot.send_message(
                self.bot.fetch_channel("games"),
                "Could not determine game state."
                " I'm sorry for the inconvenience"
            )
            await self.enter_phase('refund')

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

    async def on_ready(self):
        if self.active_phase is None:
            await self.enter_phase('pregame')
