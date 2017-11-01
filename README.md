# Beymax

Not to be confused with _[Baymax](https://en.wikipedia.org/wiki/Baymax)_

--

A custom Discord bot to handle various utilities

main.py contains the reference implementation of Beymax. Files in the bots folder
contain code for creating your own bots with subsets of the same commands and for
easily adding your own commands to a bot

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

### Administrative commands

* `!_announce <message>`

  Has Beymax send the _message_ verbatim into the general chat

* `!_owupdate`

  Performs a manual update of overwatch statistics. This normally happens every
  hour or so

* `!_owreset`

  Performs an end-of-season analysis. I currently have no way to automate Beymax
  doing this task as the season end dates are rather unpredictable
