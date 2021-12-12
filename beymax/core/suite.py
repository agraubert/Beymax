
class CommandSuite(object):
    def __init__(self, name):
        self.name = name
        self.bot = None
        self.commands = []
        self.tasks = []
        self.special = []
        self.subscriptions = []
        self.migrations = []
        self.channels = []

    def attach(self, bot):
        """
        Attaches this command suite to the given bot
        """
        print(
            "Enabling command suite {}: {} commands, {} tasks, {} special message handlers, {} event handlers, {} db migrations, {} channel references".format(
                self.name,
                len(self.commands),
                len(self.tasks),
                len(self.special),
                len(self.subscriptions),
                len(self.migrations),
                len(self.channels)
            )
        )
        self.bot = bot
        for channel in self.channels:
            bot.reserve_channel(channel)

        for migration in self.migrations:
            bot.migration(migration['key'])(migration['function'])

        for subscription in self.subscriptions:
            bot.subscribe(
                subscription['event'],
                condition=subscription['condition'],
                once=subscription['once']
            )(subscription['function'])

        for special in self.special:
            bot.add_special(special['checker'])(special['function'])

        for task in self.tasks:
            bot.add_task(task['interval'])(task['function'])

        for command in self.commands:
            bot.add_command(command['command'], *command['args'], **command['kwargs'])(command['function'])

    def add_command(self, command, *args, **kwargs):
        def wrapper(func):
            self.commands.append(
                {
                    'command': command,
                    'args': args,
                    'kwargs': kwargs,
                    'function': func
                }
            )
            return func
        return wrapper

    def add_task(self, interval):
        def wrapper(func):
            self.tasks.append(
                {
                    'interval': interval,
                    'function': func
                }
            )
            return func
        return wrapper

    def add_special(self, checker):
        def wrapper(func):
            self.special.append(
                {
                    'checker': checker,
                    'function': func
                }
            )
            return func
        return wrapper

    def subscribe(self, event, *, condition=None, once=False):
        def wrapper(func):
            self.subscriptions.append(
                {
                    'event': event,
                    'function': func,
                    'condition': condition,
                    'once': once
                }
            )
            return func
        return wrapper

    def migration(self, key):
        """
        Migrations run after the bot has connected to discord and has readied.
        Discord interactions will be ready
        """
        def wrapper(func):
            self.migrations.append(
                {
                    'key': key,
                    'function': func
                }
            )
            return func
        return wrapper

    def reserve_channel(self, name):
        """
        Call to declare a channel reference. The bot configuration can then map
        this reference to an actual channel. By default all undefined references
        map to general
        Arguments:
        name : A string channel reference to reserve
        """
        self.channels.append(name)
