# Setting Up Beymax for Your Server

Welcome! We're glad you chose Beymax as the bot or bot framework for your server

**Note:** Beymax was written to work on all platforms, but is only tested on OSX
and Linux (Ubuntu 16.04). If you have any trouble setting up Beymax on any platform,
please don't hesitate to open an issue on our [Github](https://github.com/agraubert/Beymax)

#### Terminology:

This document is written towards individuals who have little (but some) programming
experience, as you'll need at least a little to set up Beymax. Here are some terms
that we'll use:

* Server: Your discord server
* Host: The computer (possibly a *server* in the standard sense) that will be running Beymax
* Shell: The command line interface for your **Host** platform. This will be
Terminal on OSX, Command Prompt (AKA cmd) on Windows, and if you're on Linux and
don't know what a shell is, you're going to have a bad time
* Underscore Command: Commands beginning with an underscore. Generally reserved for administrative commands

---

1. Download Beymax
  1. Beymax is set up to run single-server only, so you'll need to download and
  run your own version for your **Server**
  2. On the **Host** coputer, open a **Shell** and navigate to the directory where
  you would like to install Beymax
  3. Download the current version of Beymax's code: `git clone https://github.com/agraubert/Beymax.git`
    * If you don't have Git installed on your computer, you can get it [here](https://git-scm.com/)
  4. Move into the `Beymax` directory
2. Set up a Discord App for Beymax
  1. Go to the [Discord Developers page](https://discordapp.com/developers/) and
  log in, if necessary
  2. Click on `My Apps` on the left sidebar
  3. Click on the big `New App` button in the center of the page
  4. Give a name for your bot. This could be `Beymax`, if you so choose, but you
  can use whatever you like.
    * **Note:** This will be the username of your bot
    * You may optionally add a Description and Icon. I highly recommend uploading
    an icon for your bot (instead of using a default one)
  5. Click the `Create App` button, when ready
  6. Scroll down to the `Create a Bot User` button and click it.
    * Confirm the prompt that comes up. You'll need a bot user
  7. Click the `click to reveal` link next to `Token:`
    * The token will be a long string of letters and numbers. Copy that text for
    the next step
  8. In the folder where beymax is installed (the same folder as `main.py` and
    `example_permissions.yml`), create a file called `token.txt`
  9. Paste your client token (from step 7) into that file and save it.
    * Do not place any other text in the file
3. Configure your bot
  1. Right now, the Beymax framework requires modifications to the code to configure
  your bot. In the future, we may add a configuration file, but this is not currently
  planned.
  2. The following is a list of changes you may wish to make when configuring your bot:
    * In `main.py`, you may wish to comment out/delete lines of `Enable___` passed as
    arguments to `Beymax.EnableAll()`. Each argument to that function enables a
    different set of features, and you can comment out/delete the lines to remove features
    you do not want.
    * In `main.py` in the `on_ready()` function, you may wish to change the Channels
    that are assigned to `dev_channel` and `_bug_channel`, as your **Server** will probably
    use different names
    * In all files in the `bots` folder (except `utils.py`), you may wish to change
    the commands used. Each `@bot.add_command()` function takes commands as arguments,
    and you can freely change those to change which words will trigger the bot
    * In `bots/help.py` you may wish to overhaul the help system. Most of Beymax's
    code was written for our private server, so it's unlikely that the help system
    as it is will still be useful for you. In the future, we plan to overhaul the
    help system to be more configurable for other **Servers**, but this is not
    yet planned
    * In `bots/party.py` you may wish to change the category name that party channels
    are placed into (if any), if your **Server** uses different categories
  4. Adding features
    * The Beymax framework is designed to be highly adaptable and accepting of new
    features. If you wish to add your own commands, background tasks, or special
    actions, see the [Expanding Beymax] document on the github wiki
  3. You will also wish to set up permissions for your server. Here are some
  instructions on how to use the permissions file
    1. Copy `example_permissions.yml` to `permissions.yml`. Beymax will only look
    for a `permissions.yml` file
        * If you're unfamiliar with how to write yml/yaml files, check out [these docs](http://www.yaml.org/start.html).
        The format is generally very user friendly and easy to read, which is why
        it was chosen for the permissions file.
    2. General format:
        * The permissions file is essentially a list of 'rules' which define who
        can do what with your bot.
        * Each *rule* can have the following keys:
          * `deny`: A list of commands to deny to users who this  *rule* applies to
          * `allow`: A list of commands to grant to users who this *rule* applies to
          * `underscore`: set to `true` or `false` to allow or deny access to
          **Underscore Commands** for users who this *rule* applies to
          * **Note:** Do not include the command prefix in your lists. For example,
          all of the built-in commands are prefixed with `!`, which is left off of
          all the commands listed in the permissions file
    3. The `defaults` section
        * This section defines the default permissions for all users. This rule has
        the lowest priority, and establishes the baseline of what users can and cannot do.
        * If you choose not to explicitly list every single command as either `allow`
        or `deny`, the fallback behavior is to allow every command that isn't explicitly
        denied (and to automatically deny all **Underscore Commands**)
    4. The `permissions` section:
        * This is the main section of the file, and was left out of the example_permissions
        as it would need to be **Server** specific
        * This section defines a *list* of rules. For example:
      ```yml
      permissions:
        -
          users:
            - someUser#1234
            - someOtherUser#5678
          allow:
            - satisfied
          underscore: true
        -
          role: SomeRole
          allow:
            - output-dev
            - output-prod
            - owupdate
          underscore: true
      ```
        * Each *rule* in the permissions section can either set `users` or `role`.
        It **must** set one, and **cannot** set both.
          * `users`: a list of one or more users. You may enter user ids or full
          usernames (with the #discriminator), but cannot use nicknames or usernames
          without the #discriminator.
            * The permissions defined by a `users` rule will be applied to each user
            in the list
            * Permissions granted by `users` rules can be used in private messages with
            your bot
            * `user` rules have a higher priority than `role` rules
            * A `user` rule with less users has a higher priority than a `user` rule
            with more users
          * `role`: The name or id of a role in the server
            * The permissions defined by a `role` rule will be applied to each user
            in the server who has the specified role
            * Permissions granted by `role` rules **cannot** be used in private messages.
            Due to the structure of the Discord API, it is impossible to check the roles
            of a user from within a private message. In the future, since the Beymax
            framework is designed for single-servers, we may work around this by having
            Beymax check your role in the **Server**, but this is not planned
            * `role` rules have a lower priority than `user` rules
            * Priority between two `role` rules is determined by the order of roles
          in your **Server**. A higher role has higher priority
    5. Priority between rules comes into play when multiple rules apply to a user.
        * This is common if a user has multiple roles that have rules set, and if there
        are rules set for that user specifically.
        * When checking if a user has permissions to use a specific command, Beymax
        will check their highest priority rule first, followed by the next highest,
        etc. until reaching the `defaults` rule.
        * Beymax will keep checking rules in the above order until one of them explicitly
        allows or denies use of the command (via `allow`, `deny`, or `underscore`).
          * `allow` and `deny` have a higher priority than `underscore` and when
          evaluating any specific rule
        * If Beymax finishes checking all rules for a user (including the `defaults`
          rule), the fallback behavior is to allow the command if it is not an
          **Underscore Command**. This is the lowest priority behavior, so it can be
          overridden by any rule, including `defaults`.
4. Connect your bot to your **Server**
  1. At this point, your bot is configured and ready to work. Go back to the
  [Discord Developers page](https://discordapp.com/developers/) from step 2.1
  and navigate to your bot
  2. When you click on your bot, near the top of the page will be a field called
  `Client ID` and it will be a long number. Copy the number for the next step
    * **Do not** copy the `Client Secret`, `Username`, or `Token`. These will not
    work
  3. Go to `https://discordapp.com/oauth2/authorize?&client_id=[YOUR CLIENT ID]&scope=bot`
    * For example: `https://discordapp.com/oauth2/authorize?&client_id=388735679409946627&scope=bot`
  4. In the dropdown menu, select the **Server** you wish to add your bot to
  5. Click `Authorize` at the bottom
  6. Open up your **Shell** and navigate back to Beymax's folder (with `main.py`,
    `token.txt`, and `permissions.yml`)
  7. In your shell, type `pip install -r requirements.txt`
    * This may be `pip3` or another variant of the program name, depending on your
    platform and how you installed Python
    * If you do not have Python, you can get it [here](https://www.python.org/)
    * If you do not have Pip, you can get it [here](https://pip.pypa.io/en/stable/installing/)
    or through your platform's package manager (OSX and Linux only). It will usually
    be distributed under `python3-pip`
  8. Set up your Asphalt server (Optional)
    1. If you're using the Overwatch feature set for Beymax, you will need to provide
    access to the Overwatch API (OWAPI)
      * You can either set up and run your own instance by following the directions
      [here](https://github.com/SunDwarf/OWAPI) (recommended approach)
      * Or you can use the public OWAPI by changing the `get_mmr()` function in
      `bots/ow.py` to use `https://owapi.net/` instead of `https://localhost:4444`
        * You may also need to alter the method to send a `User-Agent` header to
        comply with OWAPI's rate limiting practices
  9. In your shell, type `python main.py`
    * This may be `python3` or another variant of the program name, depending on
    your platform and how you installed it.
    * Beymax was written on **3.5.2**, but should run on any version of Python 3
  10. Congratulations! You're now running Beymax!
    * If you do not see your bot as Online in your **Server** then something has
    gone wrong.
        * Check your **Shell** to see if Beymax has produced any error messages, which
        may help you find the problem
        * Run back over this document to make sure you didn't miss any steps like
        giving Beymax your App Token, or inviting Beymax to your server with your
        App's Client ID
        * If you're still having any trouble, feel free to reach out to us with an
        issue on our [Github](https://github.com/agraubert/Beymax)
