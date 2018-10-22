import discord
import asyncio

# System lifecycle (coroutines called by parent. Each event is dispatched to on_{event})
# init : dispatched after a game system object is initialized
# start : dispatched after initialization, when a new game is starting (restores do not run this event)
# restore : dispatched after initialization, if the game is being restored
# ready : dispatched after other initialization tasks, but before the system is expected to respond to any main events
# join : dispatched when a player joins the game
# leave : dispatched when a player leaves the game
# input : dispatched when a message is recieved from any user playing the game
# check : dispatched every 30 minutes. If the game chooses to implement this event, it should make sure that the game is still active, otherwise dispatch and end event
# end : dispatched when the game is ending, but only if the game was played
# cleanup : dispatched unconditionally after the game ends

# Note: this has no concept of turns. After starting, every message sent by a player is handled by the on_input event
# Use the TurnManager class to internally implement turns

# Exceptions

class GameError(Exception):
    pass

class GameEndException(GameError):
    """
    Special subclass of GameError.
    Indicates a non-recoverable error in the game state
    This will immediately end the game and dispatch the end, and cleanup events.
    Use only for internal errors, which indicate the game needs to be refunded
    """
    pass

class JoinLeaveProhibited(GameError):
    """
    Special sublcass of GameError.
    Indicates that the current game does not allow for players to join/leave mid-game.
    If on_join or on_leave raises this exception, the action will be denied.
    It is assumed that is_playing will return the same result before and after the event
    if this exception was raised
    """
    pass


# Endgame hardness:
# * 'soft' (default) : Assume the game exited cleanly. Refund based on the game's played property
#   dispatch game.on_end, then cleanup
# * 'hard' : Game indicated an internal fail state. Refund the game
#   dispatch game.on_end, then cleanup
# * 'critical' : A critical event raised an unhandled exception. Refund the game
#   Run cleanup without running 'end' event
# Exception handling
# During main state events, normal exceptions raised will print an error, but assume the game is still running
# GameEndExceptions are interpreted as non-recoverable errors, which will dispatch the 'end' event (hard)
# During 'Critical' events:
# * Any GameErrors will immediately dispatch the 'end' event (hard)
# * Any other exceptions will hard-end the game, skipping straight to 'cleanup'
# The following events are critical:
# * The System's constructor
# * The System's restore method
# * on_init
# * on_start
# * on_restore
# * on_ready

class GameSystem(object):
    name = "Abstract Game System"

    # Attributes expected to be present on any system after initiialization:
    # name : The display name of the system
    # game : The name of the current game

    def __init__(self, bot, game):
        self.bot = bot
        self.game = game

    @classmethod
    def games(cls):
        """
        Returns the list of games supported by this system
        """
        print("DEBUG FALLBACK games")
        return []

    @classmethod
    async def restore(cls, bot, game):
        """
        Coroutine to check for saved data and return a properly constructed system representing the game state

        Any exception raised by this routine will immediately end the game without
        running the 'end' event
        """
        print("DEBUG FALLBACK restore")
        raise NotImplementedError("Subclass must implement restore functionality")

    @property
    def played(self):
        """
        Readonly property. Returns True if the system considers the current game to have been played
        """
        print("DEBUG FALLBACK played")
        return False

    def is_playing(self, user):
        """
        Method returns True if the provided user object is one of the players for this game.
        Subclass is responsible for keeping track of which players are in the game
        """
        print("DEBUG FALLBACK is_playing")
        return False

    async def on_init(self):
        """
        Dispatched after GameSystem object is initialized, unconditionally.

        Any exception raised by this routine will immediately end the game without
        running the 'end' event
        """
        print("DEBUG FALLBACK on_init")
        return

    async def on_start(self, user):
        """
        Dispatched after the init event, but only if this is a new game, and not
        a game being restored

        Any exception raised by this routine will immediately end the game without
        running the 'end' event
        """
        print("DEBUG FALLBACK on_start")
        return

    async def on_restore(self, user):
        """
        Dispatched after the init event, but only if the game is being restored,
        and not a new game

        The system should take care of any setup specific to restore events.
        Note: The classmethod restore() function is responsible for restoring the game
        This is just a distinct on_start event to inform a game that it has been restored

        Any exception raised by this routine will immediately end the game without
        running the 'end' evnet
        """
        print("DEBUG FALLBACK on_restore")
        return

    async def on_ready(self):
        """
        Dispatched after all other initialization events, just before the game
        runs. After this event, the game is expected to be ready to respond to
        user input and other main events.

        This event should not return anything. As long as it runs without raising
        an exception, the bot assumes the game is ready.
        Any exception raised by this routine will immediately end the game without
        running the 'end' event.
        """
        print("DEBUG FALLBACK on_ready")
        return

    async def on_join(self, user):
        """
        Dispatched any time a player joins the game

        This is only dispatched for players joining mid-game. The bidding player
        is passed as a parameter to start and restore, but will not generate a join event.

        The subclass is responsible for keeping track of which players are in the game

        If you wish to prevent players from joining the game, raise JoinLeaveProhibited
        """
        print("DEBUG FALLBACK on_join")
        raise NotImplementedError("Subclass must implement join functionality")

    async def on_leave(self, user):
        """
        Dispatched any time a player leaves the game.

        Note: The leave command takes care of warning the user if the bidding player leaves

        The subclass is responsible for keeping track of which players are in the game

        If you wish to prevent players from leaving the game, raise JoinLeaveProhibited
        """
        print("DEBUG FALLBACK on_leave")
        raise NotImplementedError("Subclass must implement leave functionality")

    async def on_input(self, user, channel, message):
        """
        Dispatched any time a message is sent by a user playing this game (as determined
        by is_playing).
        This event will only be dispatched after the 'ready' event has dispatched
        up until the bot closes, or the 'end' event is dispatched

        Exceptions raised by this event will be handled by one of two routes:
        * Exceptions deriving from GameEndException will print an error message,
            refund the game, and dispatch the 'end' event
        * Any other exceptions will print an error message, but assume the game
            is still active
        """
        print("DEBUG FALLBACK on_input")
        raise NotImplementedError("Subclass must implement input functionality")

    async def on_check(self):
        """
        Dispatched once every 30 minutes to ensure the game is still in a valid state.
        Externally, this is used to issue warnings to players when their game time
        is about to expire, but the system may use this event as desired (no actions
        are expected to be performed in this event).
        This event will only be dispatched after the 'ready' event has dispatched
        up until the bot closes, or the 'end' event is dispatched.

        Exceptions raised by this event will be handled by one of two routes:
        * Exceptions deriving from GameEndException will print an error message,
            refund the game, and dispatch the 'end' event
        * Any other exceptions will print an error message, but assume the game
            is still active
        """
        print("DEBUG FALLBACK on_check")
        return

    async def on_end(self):
        """
        Dispatched when the game has ended. If the game was not played, this event
        will not be dispatched, so do not run any cleanup tasks here

        This routine is expected to accomplish the following tasks, iff the game has been played:
        * Pay XP and Tokens to players, with amounts being determined by the game
        * Determine the highest score of the players, and inform the highscore system
            by dispatching the 'score' event with the (player, score) arguments
        * Post any end-of-game messages
        """
        print("DEBUG FALLBACK on_end")
        raise NotImplementedError("Subclass must implement endgame functionality")

    async def on_cleanup(self):
        """
        Dispatched unconditionally, after a game has ended. The game should take
        care of any required cleanup tasks here, but it is not required to do so.

        No more events will be dispatched after running cleanup
        """
        print("DEBUG FALLBACK on_cleanup")
        return


class Phase(object):
    """
    Set of event handlers for different phases of the game
    Sublcass and override functions for desired functionality

    There are 4 events to be handled:
    * player joining
    * player leaving
    * turn player input (or any input for a free phase)
    * non-turn input (for turn-based phases)
    """

    def __init__(self, bot, game):
        """
        Initialize with the CoreBot and GameSystem classes
        """
        self.bot = bot
        self.game = game
        self.turn = None

    async def before_phase(self):
        """
        Function run once when entering the phase
        Take any setup actions required
        """
        return

    async def after_phase(self):
        """
        Run once when the phase exits.
        Take any cleanup actions required

        This does not get triggered if the game ends during the phase.
        This is only run by calling enter_phase on the parent game
        """
        return

    async def set_player(self, user):
        """
        Sets the turn-player. For phases which are not turn-based, set user to None
        Do not override.
        To respond to new turn events, override next_turn
        """
        if user is None:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "Turn order is no longer enforced. All players may now interact freely"
            )
        else:
            await self.bot.send_message(
                self.bot.fetch_channel('games'),
                "It is now %s's turn" % user.mention
            )
            await self.next_turn(user, self.turn)
        self.turn = user

    async def next_turn(self, new, old):
        """
        Override to handle changing of turns.
        Use to handle cleanup/setup actions going into the new player's turn.
        """
        return

    async def on_input(self, user, channel, message):
        """
        Do not override. This handles all input events and dispatches to the proper
        handler.
        * on_any_input is dispatched unconditionally, when any player sends a message
        * on_turn_input is dispatched if the current turn player sends a message
        """
        print("Phase captured input", message.content)
        await self.on_any_input(user, channel, message)
        if self.turn == user:
            await self.on_turn_input(user, channel, message)
        elif self.turn is not None and self.bot.config_get('games', self.game.game, 'scold_players'):
            await self.bot.send_message(
                user,
                "Please wait for your turn. It is currently %s's turn" % self.turn.mention
            )

    async def on_any_input(self, user, channel, message):
        """
        Override to handle arbitrary user messages. This event runs unconditionally
        """
        return

    async def on_turn_input(self, user, channel, message):
        """
        Override to hanlde message from the turn player.
        This is run iff self.turn is not None and self.turn == user
        """
        return

    async def on_join(self, user):
        """
        Override to handle players joining the game.
        Player will not be in the players list yet.

        If this phase should not allow new players to join, return False.
        If this method returns False, the join event is considered 'deferred'.
        The player will not be added to the players list, and their messages will not
        dispatch input events. When this phase exits, the join event will be passed
        to the next phase.

        The player will not be added to the list until a phase returns True from
        the on_join event.
        """
        return

    async def on_leave(self, user):
        """
        Override to handle players leaving the game.
        Player will still be in the player list at this point.

        If this phase should not allow players to leave, return False.
        If this method returns False, the leave event is considered 'deferred'.
        The player will remain in the player list, and their messages will still
        dispatch input events. When this phase exits, the leave event will be passed
        to the next phase.

        The player will not be removed from the list until a phase returns True from
        the on_leave event
        """
        return



class PhasedGame(GameSystem):
    """
    Subclass of the generic GameSystem

    Delegates handling events to distinct game phases
    """

    # PhasedGame lifecycle:
    # init
    # start
    # restore
    # ready
    # before_main : dispatched just before entering the first phase
    # join : dispatched when a player joins the game. Delegated to active phase
    # leave : dispatched when a player leaves the game. Delegated to active phase
    # any_input : dispatched when a message is recieved from any user playing the game. Delegated to active phase
    # turn_input : dispatched when a message is recieved from the current turn player. Delegated to active phase
    # check : dispatched every 30 minutes. If the game chooses to implement this event, it should make sure that the game is still active, otherwise dispatch and end event
    # after_main : dispatched just before the 'end' event. This event will not be dispatched if: no phase was currently active when the game ended, or if the game ended via a GameEndException
    # end : dispatched when the game is ending, but only if the game was played
    # cleanup : dispatched unconditionally after the game ends

    # Note: the join, leave, input events are only delegated to the active phase
    # If those events are recieved before a phase is activated, they will be handled as follows:
    # * To the 'default' phase, if one is registered
    # * By the event handlers on the PhasedGame (on_default_join, on_leave, on_input)

    # Note: The default phase will be implicitly activated when a input/join/leave event is handled without an active phase

    def __init__(self, bot, game, **phases):
        """
        Initialize with a CoreBot, a game name and optionally, keyword arguments for the phase map.
        The keyword phases are stored such that self.enter_phase(key) would activate
        the phase provided by key=phase to this function
        phases can be any of the following:
        * A class derived from Phase
        * An instance of a class derived from Phase
        * A string which exists as a key in the phase map
        """
        super().__init__(bot, game)
        print("PhasedGame initialized with phases", phases)
        self.active_phase = None
        self.phase_map = {**phases}
        self._defer_join = []
        self._defer_leave = []
        self.players = []

    def is_playing(self, user):
        return user in self.players

    async def _activate_default(self):
        if self.active_phase is None and 'default' in self.phase_map:
            await self.enter_phase('default')

    async def enter_phase(self, phase):
        if isinstance(phase, Phase):
            # User provided a Phase object. Assume it's been constructed properly
            next_phase = phase
        elif isinstance(phase, type) and issubclass(phase, Phase):
            # User provided a Phase class. Construct it here
            next_phase = phase(self.bot, self)
        elif isinstance(phase, str):
            # User provided a key.
            if phase in self.phase_map:
                return await self.enter_phase(self.phase_map[phase])
            raise KeyError("No such phase '%s'" % phase)
        if self.active_phase is not None:
            await self.active_phase.after_phase()
        else:
            await self.on_before_main()
        self.active_phase = next_phase
        await self.active_phase.before_phase()
        self._defer_join = [
            user for user in self._defer_join
            if not await self.active_phase.on_join(user)
        ]
        self._defer_leave = [
            user for user in self._defer_leave
            if not await self.active_phase.on_leave(user)
        ]

    async def on_before_main(self):
        """
        Dispatched just before activating the first phase.
        If a 'default' phase is registered, this will be dispatched just before
        the default phase responds to any events
        """
        return

    async def on_after_main(self):
        """
        Dispatched just before the 'end' event.
        This is only dispatched if both of the following conditions are met:
        * There was a phase active when the game ended
        * The game was ended by dispatching the global 'endgame' event, and not by raising a GameEndException

        Use this if there is any specific action that needs to be taken care of
        if the game ends mid-phase.

        Use on_end for anything that needs to be run no matter how the game ends
        """
        return

    async def on_input(self, user, channel, message):
        """
        Do not override this method. This routes the input event to the active phase

        If you wish to override the fallback event handler (to process input when no phase is active)
        use on_default_input
        """
        await self._activate_default()
        if self.active_phase is not None:
            return await self.active_phase.on_input(user, channel, message)
        else:
            return await self.on_default_input(user, channel, message)

    async def on_default_input(self, user, channel, message):
        """
        Dispatched when input is recieved without an active phase
        """
        return

    async def on_join(self, user):
        """
        Do not override this method. This routes the join event to the active phase,
        and handles deferring join events as well.

        If you wish to override the fallback event handler (to process joins when no phase is active)
        use on_default_join.
        """
        print("HANDLE JOIN", user)
        await self._activate_default()
        if self.active_phase is not None:
            if not await self.active_phase.on_join(user):
                print("DEFER")
                self._defer_join.append(user)
                await self.bot.send_message(
                    user,
                    "You cannot join the game at this time. "
                    "You will automatically join the game at the next opportunity"
                )
        else:
            if not await self.on_default_join(user):
                print("DEFER")
                self._defer_join.append(user)
                await self.bot.send_message(
                    user,
                    "You cannot join the game at this time. "
                    "You will automatically join the game at the next opportunity"
                )

    async def on_default_join(self, user):
        """
        Dispatched when a player joins without an active phase

        Return False to defer the join event to the next phase

        Default implementation returns False
        """
        return False

    async def on_leave(self, user):
        """
        Do not override this method. This routes the leave event to the active phase,
        and handles deferring leave events as well.

        If you wish to override the fallback event handler (to process leaves when no phase is active)
        use on_default_leave.
        """
        print("HANDLE LEAVE", user)
        await self._activate_default()
        if self.active_phase is not None:
            if not await self.active_phase.on_leave(user):
                print("DEFER")
                self._defer_leave.append(user)
                await self.bot.send_message(
                    user,
                    "You cannot leave the game at this time. "
                    "You will automatically leave the game at the next opportunity"
                )
        else:
            if not await self.on_default_leave(user):
                print("DEFER")
                self._defer_leave.append(user)
                await self.bot.send_message(
                    user,
                    "You cannot leave the game at this time. "
                    "You will automatically leave the game at the next opportunity"
                )


    async def on_default_leave(self, user):
        """
        Dispatched when a player leaves without an active phase

        Return False to defer the leave event to the next phase

        Default implementation returns False
        """
        return False
