# Beymax

Not to be confused with _[Baymax](https://en.wikipedia.org/wiki/Baymax)_

---

A custom Discord bot to handle various utilities

main.py contains the reference implementation of Beymax. Files in the bots folder
contain code for creating your own bots with subsets of the same commands and for
easily adding your own commands to a bot

### Setup

Looking to set up Beymax on your server? Check the [Setup Guide](https://github.com/agraubert/Beymax/blob/master/INSTALL.md)

### Chat commands

* `!ow <battle-tag>`

  _battle-tag_ must be in the standard _username#discriminator_ format.
  Attaches the provided battle-tag to your discord username (on this server).
  Beymax will periodically check to see if your competitive rank has increased
  and will make announcements to the general chat if you go up a rank.
  **NOTE** You must be currently ranked to run this command.  Beymax will not
  be able to validate your battle-tag if you are unranked

* `!party [party name]`

  Beymax requires the **Manage Channels** permission to use this command.
  Creates a new temporary voice channel.  If _party name_ is provided, it will
  be the name of the channel.  Otherwise, the channel will simply be named 'Party'.
  Each user can only create one party at any given time, and Beymax will prompt
  users to delete old parties if they attempt to create a party while they already
  have one active. Use the `!disband` command to close your current party.
  Beymax will automatically clean up parties after 24 hours if nobody is in the channel.

* `!disband`

  Beymax requires the **Manage Channels** permission to use this command.
  Deletes your existing party, if you have one.  Use the `!party` command to
  create parties

* `!poll <title> | <option 1> [| <option 2> [| <option 3> ...]]`

  Beymax requires the **Manage Messages** permission to use this command.
  Creates a emoji-based poll. Separate each option using `|`. Supports up to 10
  options. Users can vote simply by clicking the reaction emoji corresponding to
  the option they choose. **NOTE** Beymax will vote for all options because he has
  no self control (but mostly because it's the only way to make the reactions
  appear initially)

* `!birthday <your birthday>`

  Tracks your birthday (provided in MM/DD/YYYY format). Beymax will post a congratulatory
  message

* `!bug <issue>`

  Reports a bug with Beymax. Currently bugs are tracked in discord via a dedicated
  text channel, but the goal would be to report the bug and open an issue on Beymax's
  github

* `!bug:comment <bug id> <your comments>` or `!comment <bug id> <your comments>`

  Adds a comment to an open issue

* `!bug:label <bug id> <new label>`

  Re-labels a bug. By default bugs are labeled using the original issue text

* `!bug:status <bug id> <status>`

  Change the status of a bug

* `!bug:thread <bug id>` or `!thread <bug id>`

  Display the full comment thread of a bug

* `!bug:unsubscribe <bug id>` or `!unsubscribe <bug id>`

  Disables getting \@mentioned every time changes are made to this bug. You cannot
  unsubscribe if you created the bug

* `!bug:user <bug id> <username or id>`

  Subscribes the user to the bug

* `!permissions`

  Beymax will PM you with a list of all commands you have are authorized to use.
  Note that permissions gained though roles cannot be verified in a PM, so if you
  use `!permissions` in a PM with Beymax, he will only report default permissions
  and those assigned to you directly. **This does not apply** iff you have a
  primary_server set in the configuration. Beymax will validate roles in PMs only
  with a primary_server configured

* `!kill-beymax` or `!satisfied`

  Shuts down Beymax

* `!ouch`

  Begins a private help session with Beymax.  Help sessions should be coded on a
  per-server basis. Help sessions run like state machines. You may use the Help
  Session in this code as an example, but it likely won't make much sense for your
  server.

* `!output-dev`

  Sets Beymax to send all messages normally directed to `General` into `Testing Grounds`

* `!output-prod`

  Sets Beymax to send all messages normally directed to `General` into `General`
  (standard mode)

* `!ignore <user ID or username#discriminator>`

  Sets Beymax to ignore all messages and commands from the provided user

* `!pardon <user ID or username#discriminator>`

  Sets Beymax to resume responding to commands from the provided user

* `!timeleft`

  Gets the time remaining on the current game

* `!games`

  Lists the games available

* `!toggle-comments`

  If there is a game currently being played *by the user issuing this command*,
  this toggles whether or not other users can speak in the game channel

* `!highscore <game>`

  Reports the highscore of the provided game

* `!idof <name>`

  Gets ids of all servers for any member, role, or channel with a name similar
  to *name*.

* `!balance`

  Get your current level, xp, and token balance

* `!reup`

  Extends the current game session if you are the player

### Administrative commands

* `!_announce <message>`

  Has Beymax send the _message_ verbatim into the general chat

* `!_greet`

  Manually trigger a greeting message (for yourself)

* `!_owinit`

  Enable stats tracking and trigger start-of-season message. Currently, there is
  no automated method for doing this

* `!_owupdate`

  Performs a manual update of overwatch statistics. This normally happens every
  hour or so

* `!_owreset`

  Performs an end-of-season analysis. I currently have no way to automate Beymax
  doing this task as the season end dates are rather unpredictable

* `!_payment <project> <username or ID> $<amount>`

  Records a payment to an ongoing fundraising project.  Currently this must be done
  manually. Report username as `0` to make anonymous

* `!_project <Full project name> | <One word short name> | <End date MM/DD/YYYY | $<goal amount> | <Venmo username>`

  Starts a new fundraising project. Beymax will notify users monthly until the project
  is manually ended, the time expires, or the goal is reached

* `!_project:end <project short name>`

  Manually ends a fundraising project

* `!_status [status message]`

  Changes Beymax's current status message to the provided status. If no status is provided,
  Beymax will pick one from the preset list

* `!_task [name of task]`

  Manually dispatches the named task. Task names are the name of the function used
  to handle the task

* `!_payout <username or id> {xp,tokens} <amount>`

  Pays the provided user the specified amount of tokens or xp

* `!_nt`

  Reports the number of events that have been dispatched by Beymax so far
