import asyncio
from ...utils import Database, load_db, getname
from ..base import GameEndException
from .utils import FreePhase, LockedPhase, Card, Hand, strike_if

# Blackjack house rules:
# * Reset phase and pregame phase both set dealer to -1 so that the Host always goes fist
# During pregame phase, players may join and leave freely (refunding their bet)
# Keep advancing until all players have placed a bet, folded, or left the game
# Deal all cards, keeping 1 face down for beymax
# * If Beymax has a natural, the game immediately ends
#       Collect money from every player without a natural, and refund those with (i'ts a draw)
# * If any player has a natural, and beymax does not, immediately payout 2.5x (Total 1.5x return)
# Otherwise, commence the main phase
# On each turn, a player may
# * Stay/Stand : Keep current hand and pass
# * Hit : Take another card
# * Double-down (Iff the initial hand totals 9, 10, or 11) : Double your bet and take one hit, then stay
# The dealer must hit until his hand totals 17 or higher
# On a soft finish, beymax will only hit if he has not beaten any hands

# blackjack xp
# (base: 15) + (2.5 * payout) - (10 on loss) - (5 on tie)

def evaluate_hand(hand, total=0, soft=False):
    # value + 2
    # if value > 8, value == 10
    # if rank == ace, recurse soft and hard
    for i in range(len(hand.cards)):
        card = hand.cards[i]
        if card.rank == 'ace':
            soft_ace = Card('two', card.suit)
            soft_ace.rank_vaue = 0 # +2 = 1
            hard_ace = Card('two', card.suit)
            hard_ace.rank_value = 99
            return (
                *evaluate_hand(Hand([soft_ace] + hand.cards[i+1:]), total - 1, soft),
                *evaluate_hand(Hand([hard_ace] + hand.cards[i+1:]), total, True)
            )
        elif card.rank_value > 8 and card.rank_value != 99:
            assert card.rank in {'ten', 'jack', 'queen', 'king'}, card
            total += 10
        elif card.rank_value == 99:
            assert card.rank == 'two', card
            total += 11
        else:
            assert card.rank in {'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'}, card
            total += card.rank_value + 2
    return [(total, soft)]

class BeforeRound(FreePhase):
    """
    This phase represents the betting period between when the game has started
    and when all players have placed bets. Players may join or leave freely
    The phase automatically ends when all players have placed a bet
    """
    async def on_leave(self, user):
        await super().on_leave(user)
        if user.id in self.game.refund:
            async with Database('players.json') as players:
                if user.id not in players:
                    players[user.id] = {
                        'level':1,
                        'xp':0,
                        'balance':10
                    }
                players[user.id]['balance'] += self.game.refund[user.id]
                players.save()
            del self.game.refund[user.id]
        await self.try_advance()
        return True

    async def before_phase(self):
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "A new round of Blackjack is about to start."
            " Players may join or leave freely until all players have placed a "
            "bet. If you leave after placing a bet, your bet **will** be refunded."
            " All players, please specify your bets, in tokens. If you would"
            " like to sit this round out, say `fold`"
        )

    async def on_join(self, user):
        await super().on_join(user)
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            " Please specify your bets, in tokens. If you would"
            " like to sit this round out, say `fold`"
        )
        return True

    async def try_advance(self):
        if len({*self.game.bets} | self.game.inactive_players) == len(self.game.players):
            if len({player.id for player in self.game.players} - self.game.inactive_players) ==  0:
                await self.bot.send_message(
                    self.bot.fetch_channel("games"),
                    "There are no players this round. The round will now"
                    " restart."
                )
                return await self.game.enter_phase('reset')
            else:
                return await self.game.enter_phase('deal')
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "Still waiting on bets from: %s" % (
                ', '.join(player.mention for player in self.game.players if player.id not in self.game.inactive_players and (player.id not in self.game.bets or self.game.bets[player.id] == 0))
            )
        )

    async def on_any_input(self, user, channel, message):
        if message.content.lower().strip() == 'fold':
            self.game.inactive_players.add(user.id)
            await self.try_advance()
            return
        async with Database('players.json') as players:
            if user.id not in players:
                players[user.id] = {
                    'level':1,
                    'xp':0,
                    'balance':10
                }
                players.save()
            balance = players[user.id]['balance']
        try:
            bet = int(message.content.lower().replace('tokens', '').strip())
            if bet < 1:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "That is not a valid amount. "
                    "Please specify your bet as a positive integer"
                )
            elif bet > balance:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You do not have enough tokens to make that bet. "
                    "Your balance is currently %d tokens" % balance
                )
            else:
                self.game.refund[user.id] = bet
                self.game.bets[user.id] = bet
                async with Database('players.json') as players:
                    if user.id not in players:
                        players[user.id] = {
                            'level':1,
                            'xp':0,
                            'balance':10
                        }
                    players[user.id]['balance'] -= bet
                    players.save()
                await self.try_advance()
        except ValueError:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "That is not a valid amount. "
                "Please specify your bet as a positive integer:"
            )

class Deal(LockedPhase):
    """
    This is the initial game phase.
    Players are each dealt two cards face up
    Beymax is dealt 1 up and 1 down
    """
    async def before_phase(self):
        self.game.was_played = True
        self.game.square = set()
        for player in self.game.players:
            if player.id not in self.game.inactive_players:
                if len(self.game.deck) < 2:
                    self.game.deck.fill(self.game.trash)
                    self.game.trash.cards = []
                self.game.hands[player.id] = Hand(self.game.deck.deal(2))
        if len(self.game.deck) < 2:
            self.game.deck.fill(self.game.trash)
            self.game.trash.cards = []
        self.game.table = Hand(self.game.deck.deal(2))
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            "Players can no longer join or leave until the end of the round.\n"+
            "All hands have been dealt. Here are your cards:\n" + (
                "\n".join(
                    '%s : %s' % (
                        getname(self.bot.get_user(uid)),
                        hand.display
                    )
                    for uid, hand in self.game.hands.items()
                )
            ) + (
                "\n------------------\n$NICK's hand: *, %s" % repr(self.game.table.cards[1])
            )
        )
        # * If Beymax has a natural, the game immediately ends
        #       Collect money from every player without a natural, and refund those with (i'ts a draw)
        # * If any player has a natural, and beymax does not, immediately payout 2.5x (Total 1.5x return)
        table_score = [score for score, soft in evaluate_hand(self.game.table) if score == 21]
        player_scores = {
            uid: [score for score, soft in evaluate_hand(hand) if score == 21]
            for uid, hand in self.game.hands.items()
        }
        if len(table_score):
            # Beymax has a natural
            # Collect from each player withou
            # Refund for each player with
            # Reset
            ties = []
            async with Database('players.json') as players:
                for player in self.game.players:
                    if player.id not in self.game.inactive_players:
                        if player.id not in players:
                            players[player.id] = {
                                'level':1,
                                'xp':0,
                                'balance':10
                            }
                        if len(player_scores[player.id]):
                            # Player had a natural
                            players[player.id]['balance'] += self.game.bets[player.id]
                            ties.append(player.id)
                            self.bot.dispatch(
                                'grant_xp',
                                player,
                                int(0.75 * self.game.bets[player.id])
                            )
                        # else:
                        #     self.bot.dispatch(
                        #         'grant_xp',
                        #         player,
                        #         5
                        #     )
                players.save()
            msg = "$NICK had a natural 21 (%s), so the game is over. " % self.game.table.display
            if len(ties):
                msg += "%s%s%s also had a natural 21, so their bet(s) are refunded. " % (
                    ', '.join(self.bot.get_user(tie).mention for tie in ties[:-1]),
                    ' and ' if len(ties) > 1 else '',
                    self.bot.get_user(ties[-1]).mention
                )
            msg += "Everyone else loses. Better luck next time!"
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                msg
            )
            await self.game.enter_phase('reset')
        elif len([uid for uid, wins in player_scores.items() if len(wins)]):
            async with Database('players.json') as players:
                for player in self.game.players:
                    if player.id not in self.game.inactive_players:
                        if player.id not in players:
                            players[player.id] = {
                                'level':1,
                                'xp':0,
                                'balance':10
                            }
                        if len(player_scores[player.id]):
                            # Player had a natural
                            players[player.id]['balance'] += int(1.5 * self.game.bets[player.id])
                            self.bot.dispatch(
                                'grant_xp',
                                player,
                                int(1.75 * self.game.bets[player.id])
                            )
                        # else:
                        #     self.bot.dispatch(
                        #         'grant_xp',
                        #         player,
                        #         5
                        #     )
                players.save()
            winners = [uid for uid, hand in self.game.hands if len(player_scores[uid])]
            msg = "%s%s%s had a natural 21, so their bet(s) are refunded. " % (
                ', '.join(self.bot.get_user(uid).mention for uid in winners[:-1]),
                ' and ' if len(winners) > 1 else '',
                self.bot.get_user(winners[-1]).mention
            )
            await self.game.enter_phase('reset')
        else:
            await self.game.enter_phase('main')

    async def after_phase(self):
        await self.game.save_state()

class MainPhase(LockedPhase):
    """
    This is the main game phase.
    During each player's turn, they can stay, hit, or double down.
    After all players have finished, advance to the dealer's phase
    """
    async def before_phase(self):
        await self.set_player(self.game.advance_index())

    async def after_phase(self):
        await self.game.save_state()

    async def advance_if(self):
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
            await self.game.enter_phase('dealer')

    async def next_turn(self, player, old):
        hand = self.game.hands[player.id]
        scores = [
            (score, soft)
            for score, soft in evaluate_hand(hand)
            if score <= 21
        ]
        best_score = sorted(scores, key=lambda x:x[0])[-1]
        msg = (
            "Your hand is %s, which comes to %d (%s)\n"
            "$NICK has *, %s.\nActions:\n" % (
                hand.display,
                best_score[0],
                'soft' if best_score[1] else 'hard',
                repr(self.game.table.cards[1])
            )
        )
        if len(hand) == 2 and len({9,10,11} & {score for score, soft in scores}):
            async with Database('players.json') as players:
                if player.id not in players:
                    players[player.id] = {
                        'level':1,
                        'xp':0,
                        'balance':10
                    }
                    players.save()
                balance = players[player.id]['balance']
            msg += strike_if(
                '`double down` (Double your bet of %d, hit, then stay)\n' % self.game.bets[player.id],
                balance >= self.game.bets[player.id]
            )
        msg += "`hit` (Take another card)\n`stay` (End your turn)"
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            msg
        )

    async def on_turn_input(self, user, channel, message):
        content = message.content.lower().strip().split()
        if len(content) < 1:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "That action is invalid"
            )
        elif content[0] == 'hit':
            if len(self.game.deck) < 1:
                self.game.deck.fill(self.game.trash)
                self.game.trash.cards = []
            self.game.hands[user.id] += self.game.deck.deal(1)
            scores = evaluate_hand(self.game.hands[user.id])
            if min(score[0] for score in scores) > 21:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "Bust! You were dealt %s which brought you to a total of %d"
                    ". Better luck next time!" % (
                        repr(self.game.hands[user.id][-1]),
                        min(score[0] for score in scores)
                    )
                )
                del self.game.refund[user.id]
                self.game.inactive_players.add(user.id)
                self.bot.dispatch(
                    'grant_xp',
                    user,
                    5
                )
                # del self.game.hands[user.id]
                return await self.advance_if()
            else:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "Safe! You were dealt %s" % repr(self.game.hands[user.id][-1])
                )
                self.game.square.add(self.turn.id)
        elif content[0] == 'stay':
            self.game.square.add(self.turn.id)
            return await self.advance_if()
        elif content[0] == 'double' and (len(content) == 1 or content[1] == 'down'):
            scores = evaluate_hand(self.game.hands[user.id])
            if len(self.game.hands[user.id]) == 2 and len({9,10,11} & {score for score, soft in scores}):
                async with Database('players.json') as players:
                    if user.id not in players:
                        players[user.id] = {
                            'level':1,
                            'xp':0,
                            'balance':10
                        }
                        players.save()
                    balance = players[user.id]['balance']
                if balance >= self.game.bets[user.id]:
                    async with Database('players.json') as players:
                        players[user.id]['balance'] -= self.game.bets[user.id]
                        players.save()
                    self.game.refund[user.id] += self.game.bets[user.id]
                    self.game.bets[user.id] *= 2
                    if len(self.game.deck) < 1:
                        self.game.deck.fill(self.game.trash)
                        self.game.trash.cards = []
                    self.game.hands[user.id] += self.game.deck.deal(1)
                    scores = evaluate_hand(self.game.hands[user.id])
                    if min(score[0] for score in scores) > 21:
                        await self.bot.send_message(
                            self.bot.fetch_channel('games'),
                            "Bust! You were dealt %s which brought you to a total of %d"
                            ". Better luck next time!" % (
                                repr(self.game.hands[user.id][-1]),
                                min(score[0] for score in scores)
                            )
                        )
                        del self.game.refund[user.id]
                        self.game.inactive_players.add(user.id)
                        self.bot.dispatch(
                            'grant_xp',
                            user,
                            5
                        )
                        # del self.game.hands[user.id]
                    else:
                        await self.bot.send_message(
                            self.bot.fetch_channel('games'),
                            "Safe! You were dealt %s" % repr(self.game.hands[user.id][-1])
                        )
                        self.game.square.add(self.turn.id)
                    return await self.advance_if()
                else:
                    await self.bot.send_message(
                        self.bot.fetch_channel('games'),
                        "You do not have enough tokens to double your bet"
                    )
            else:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You can only double down as your first action, and only if "
                    "your hand totals 9, 10, or 11"
                )
        else:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "That action is invalid"
            )
        await self.next_turn(user, None)

class DealerPhase(LockedPhase):
    """
    This is a purely computational phase.
    Beymax plays the game until reaching a score of 17.
    On a soft 17, hit only if he isn't beating any players
    """

    async def before_phase(self):
        scores = [score for score in evaluate_hand(self.game.table) if score[0] <= 21]
        scores = sorted(scores, key=lambda x:x[0])
        msg = "It's now $MENTION's turn...\n"
        msg += "$NICK has %s, which comes to %d (%s)\n" % (
            self.game.table.display,
            scores[-1][0],
            'soft' if scores[-1][1] else 'hard'
        )
        worst_player_score = min([0] +
            [score
            for uid, hand in self.game.hands.items()
            for score, soft in evaluate_hand(hand)
            if uid not in self.game.inactive_players]
        )
        while scores[0][0] < 21 and (scores[-1][0] < 17 or (scores[-1][1] and scores[-1][0] < worst_player_score)):
            # Beymax must take a hit because:
            # He has not busted AND
            #   His best hand is under 17 OR
            #       His best hand is soft AND
            #           He is not beating any player
            if len(self.game.deck) < 1:
                self.game.deck.fill(self.game.trash)
                self.game.trash.cards = []
            self.game.table += self.game.deck.deal(1)
            scores = sorted(evaluate_hand(self.game.table), key=lambda x:x[0])
            msg += "$NICK hits, drawing %s (total of %d)\n" % (
                repr(self.game.table[-1]),
                scores[-1][0]
            )
            # scores= [(score, soft) for score, soft in scores if score <= 21]
        if not len([score for score, soft in scores if score <= 21]):
            msg += 'Bust!'
        else:
            msg += '$NICK stays with a hand of %s' % self.game.table.display
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            msg
        )
        await self.game.enter_phase('win')

    async def after_phase(self):
        await self.game.save_state()


class WinPhase(LockedPhase):
    """
    This phase represents the end of the game.
    It checks to see if there are no active players (at least one square player not inactive)
    If there are no active players (everyone busted then just reset)
    For any player who beat beymax, pay them 1.5x (add 2.5 to their balance) and grant 2.5x
    For any player who tied beymax, pay them 0x (add 1 to their balance) and grant them 1.5x
    For any player who lost to beymax, grant them 5xp
    """
    async def before_phase(self):
        table_score = max([0] + [score for score, soft in evaluate_hand(self.game.table) if score <= 21])
        best_bust_score = min([99] + [score for score, soft in evaluate_hand(self.game.table) if score > 21])
        losers = set()
        ties = set()
        winners = set()
        msg = "Here are the results:\n"
        async with Database('players.json') as players:
            for player in self.game.players:
                if player.id not in players:
                    players[player.id] = {
                        'level':1,
                        'xp':0,
                        'balance':10
                    }
                # assert player.id in self.game.square != player.id in self.game.inactive_players, (self.game.inactive_players, self.game.square)
                if player.id in self.game.hands:
                    hand = self.game.hands[player.id]
                    scores = sorted(evaluate_hand(hand), key=lambda x:x[0])
                    best_score = max([0] + [score for score, soft in scores if score <= 21])
                    msg += "%s with %s, which comes to %d%s\n" % (
                        getname(player),
                        hand.display,
                        best_score if best_score > 0 else min(score for score, soft in scores if score > 21),
                        ' (Bust!)' if best_score == 0 else ''
                    )
                    if player.id not in self.game.inactive_players:
                        if scores[0][0] > 21 or best_score < table_score:
                            losers.add(player.id)
                            if player.id in self.game.refund:
                                del self.game.refund[player.id]
                            del self.game.bets[player.id]
                            # self.bot.dispatch(
                            #     'grant_xp',
                            #     player,
                            #     5
                            # )
                        elif scores[0][0] <= 21:
                            if best_score == table_score:
                                ties.add(player.id)
                                if player.id in self.game.refund:
                                    del self.game.refund[player.id]
                                players[player.id]['balance'] += self.game.bets[player.id]
                                self.bot.dispatch(
                                    'grant_xp',
                                    player,
                                    int(0.75 * self.game.bets[player.id])
                                )
                                del self.game.bets[player.id]
                            elif best_score > table_score:
                                winners.add(player.id)
                                if player.id in self.game.refund:
                                    del self.game.refund[player.id]
                                players[player.id]['balance'] += int(1.5 * self.game.bets[player.id])
                                self.bot.dispatch(
                                    'grant_xp',
                                    player,
                                    int(1.75 * self.game.bets[player.id])
                                )
                                del self.game.bets[player.id]
            players.save()
        msg += "And $NICK with %s, which comes to %d%s\n" % (
            self.game.table.display,
            table_score if table_score != 0 else best_bust_score,
            ' (Bust!)' if table_score == 0 else ''
        )
        if len(ties):
            msg += "The following players tied with $NICK and will have their bets refunded: %s\n" % (
                ', '.join(
                    self.bot.get_user(uid).mention
                    for uid in ties
                )
            )
        if len(winners):
            msg += "The following players beat $NICK and earn 1.5x their bets: %s\n" % (
                ', '.join(
                    self.bot.get_user(uid).mention
                    for uid in winners
                )
            )
            msg += 'Congratulations!'
        else:
            msg += "Better luck next time!"
        await self.bot.send_message(
            self.bot.fetch_channel('games'),
            msg
        )
        await self.game.enter_phase('reset')

class ResetPhase(LockedPhase):
    """
    This phase resets the game for another round:
    * Advance the dealer index by 1
    * Reset the player index to 1
    * Reset inactive players to set()
    * Reset ante to 0
    * Empty hands and table into trash deck
    * save the player list, dealer index, bidder, deck, and trash to poker.json
    """

    async def before_phase(self):
        self.game.dealer = -1
        self.game.index = 0
        self.game.inactive_players = set()
        self.game.ante = 0
        self.game.square = set()
        self.game.trash += self.game.table.cards
        self.game.table = Hand()
        for hand in self.game.hands.values():
            self.game.trash += hand.cards
        self.game.hands = {}
        self.game.bets = {}
        self.game.refund = {}
        await self.game.enter_phase('beforeRound')

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


__GAME_DEF = {
    'Blackjack':
    {
        'reset': ResetPhase,
        'pregame': BeforeRound,
        'beforeRound': BeforeRound,
        'deal': Deal,
        'main': MainPhase,
        'dealer': DealerPhase,
        'win': WinPhase,
        'refund': RefundPhase,
        'default': BeforeRound
    }
}

async def __RESTORE(game, bidder):
    tlen = len(game.table)
    plen = max([0] + [len(hand) for hand in game.hands.values()])
    if tlen == 0 and plen == 0:
        await game.enter_phase('beforeRound')
    elif tlen == 2 and plen == 2:
        await game.enter_phase('main')
    elif tlen > 2:
        await game.enter_phase('win')
    elif plen > 2:
        await game.enter_phase('dealer')
    else:
        await game.bot.send_message(
            game.bot.fetch_channel("games"),
            "Could not determine game state."
            " I'm sorry for the inconvenience"
        )
        await game.enter_phase('refund')
