import asyncio
from ...utils import Database, load_db, getname
from .utils import FreePhase, LockedPhase, Hand, strike_if

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
        return True

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
        self.game.bets = {}
        self.game.square = set()
        self.game.bet = -1

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
            return await self.next_turn(user, None)
        elif content[0] == 'bet' and self.game.bet == -1:
            if len(content) != 2:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to bet"
                )
                return await self.next_turn(user, None)
            try:
                cost = int(content[1])
            except ValueError:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to bet"
                )
                return await self.next_turn(user, None)
            if cost < 1:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to bet"
                )
                return await self.next_turn(user, None)
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
                if user.id in self.game.refund:
                    self.game.refund[user.id] += cost
                else:
                    self.game.refund[user.id] = cost
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
                return await self.next_turn(user, None)
            try:
                raise_amt = int(content[1])
                cost = raise_amt + call
            except ValueError:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to raise by"
                )
                return await self.next_turn(user, None)
            if cost < 1:
                await self.bot.send_message(
                    self.bot.fetch_channel('games'),
                    "You must provide a quantity of tokens to raise by"
                )
                return await self.next_turn(user, None)
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
                if user.id in self.game.refund:
                    self.game.refund[user.id] += cost
                else:
                    self.game.refund[user.id] = cost
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
                if user.id in self.game.refund:
                    self.game.refund[user.id] += cost
                else:
                    self.game.refund[user.id] = cost
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
        return await self.next_turn(user, None)


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
        # First make sure the table has 5 cards. We may have skipped to this state
        remaining_cards = 5 - len(self.game.table)
        if remaining_cards:
            if len(self.game.deck) < remaining_cards:
                self.game.deck.fill(self.game.trash)
                self.game.trash.cards = []
            self.game.table += self.game.deck.deal(remaining_cards)
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
        payout = self.game.pot // len(winners)
        leftover = self.game.pot % len(winners)
        await self.bot.send_message(
            self.bot.fetch_channel("games"),
            "Everyone, flip your cards!\n"
            "`%s` on the table,\n"
            "%s\n----------\n"
            "And the winner%s:\n"
            "%s\n"
            "Congratulations! Each winner will recieve %d tokens" % (
                self.game.table.display,
                player_hands,
                ' is' if len(winners) <= 1 else 's are',
                ', '.join(
                    self.bot.get_user(player_id).mention
                    for player_id in winners
                ),
                payout
            )
        )
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
    * Reset the player index to 1
    * Reset inactive players to set()
    * Reset ante to 0
    * Empty hands and table into trash deck
    * save the player list, dealer index, bidder, deck, and trash to poker.json
    """

    async def before_phase(self):
        self.game.dealer = (self.game.dealer + 1) % len(self.game.players)
        self.game.index = 1
        self.game.inactive_players = set()
        self.game.ante = 0
        self.game.square = set()
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


__GAME_DEF = {
    'Texas-Hold-em':
    {
        'reset': ResetPhase,
        'deal': Deal,
        'flop': Flop,
        'turn': Turn,
        'river': River,
        'win': WinPhase,
        'refund': RefundPhase,
        'pregame': PreGame,
        'beforeRound': BeforeRound,
        'default': PreGame
    }
}

async def __RESTORE(game, bidder):
    tlen = len(game.table)
    if tlen == 5:
        await game.enter_phase('win')
    elif tlen == 4:
        await game.enter_phase('river')
    elif tlen == 3:
        await game.enter_phase('turn')
    elif tlen == 0 and len(game.hands) > 1:
        await self.enter_phase('flop')
    elif tlen == 0 and len(game.hands) == 0:
        await game.enter_phase('deal')
    else:
        await game.bot.send_message(
            game.bot.fetch_channel("games"),
            "Could not determine game state."
            " I'm sorry for the inconvenience"
        )
        await game.enter_phase('refund')
