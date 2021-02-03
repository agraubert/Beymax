from .core import CoreBot
from .utils import DBView, getname, get_attr
from .args import Arg, UserType
import asyncio
import json

def EnableBugs(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.reserve_channel('bugs')

    @bot.subscribe('before:ready')
    async def cleanup(self, _):
        if not os.path.exists('bugs.json'):
            return
        with open('bugs.json') as r:
            bugs = json.load(r)
        async with DBView('bugs') as db:
            db['bugs'] = bugs


    @bot.add_command(
        'bug',
        Arg(
            'content',
            remainder=True,
            help='Your feedback or bug report'
        ),
    )
    async def cmd_bug(self, message, content):
        """
        `$!bug [feedback or bug report]` : Opens a new ticket with your
        feedback. Example: `$!bug $NAME didn't understand me in a help session`
        """
        async with DBView('bugs', bugs=[]) as db:
            db['bugs'].append({
                'users': [message.author.id],
                'status': 'Pending', #pending->investigating->solution in progress->testing solution->closed
                'content': content,
                'comments':[],
                'label': content
            })
            role_mention = ''
            role_target = self.config_get('bug_role')
            if role_target is not None:
                for role in self.fetch_channel('bugs').guild.roles:
                    # Not that this will make literally 0 sense in a multi-server environment
                    # primaryServerMasterRace
                    if role.id == role_target or role.name == role_target:
                        role_mention = role.mention
                if role_mention == '':
                    raise NameError("No role '%s'" % role_target)
            await self.send_message(
                self.fetch_channel('bugs'),
                'New issue reported: %s\n' #@Developer
                '[%d] [Pending] %s : %s' % (
                    role_mention,
                    len(db['bugs'])-1,
                    message.author.mention,
                    db['bugs'][-1]['content']
                )
            )

    @bot.add_command('thread', Arg('bug', type=int, help="Bug ID"), aliases=['bug:thread'])
    async def cmd_thread(self, message, bug):
        """
        `$!thread <bug ID>` : Displays the full comment thread for a bug.
        Example: `$!thread 2`
        """
        async with DBView(bugs=[]) as db:
            if bug >= len(db['bugs']):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                data = db['bugs'][bug]
                body = '[%d] [%s] %s : %s\n' % (
                    bug,
                    data['status'],
                    ' '.join(
                        getname(self.get_user(user)) for user in
                        data['users']
                    ),
                    data['label'],
                )
                body += 'Issue: %s\n' % data['content']
                for comment in data['comments']:
                    body += 'Comment by %s\n' % comment
                await self.send_message(
                    message.channel,
                    body
                )

    @bot.add_command(
        'comment',
        Arg('bug', type=int, help="Bug ID"),
        Arg('comment', remainder=True, help="Your comments"),
        aliases=['bug:comment']
    )
    async def cmd_comment(self, message, bug, comment):
        """
        `$!comment <bug ID> [Your comments]` : Adds your comments to the bug's
        thread. Example: `$!comment 2 The help system is working great!`
        """
        async with DBView('bugs', bugs=[]) as db:
            if bug >= len(db['bugs']):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                comment = ' '.join(comment)
                db['bugs'][bug]['comments'].append(
                    '%s : %s' % (
                        getname(message.author),
                        comment
                    )
                )
                await self.send_message(
                    self.fetch_channel('bugs'),
                    'New comment on issue:\n'
                    '[%d] [%s] %s : %s\n'
                    'Comment: [%s] : %s' % (
                        bug,
                        db['bugs'][bug]['status'],
                        ' '.join(
                            get_attr(self.get_user(user), 'mention', '') for user in
                            db['bugs'][bug]['users']
                        ),
                        db['bugs'][bug]['label'],
                        message.author.mention,
                        comment
                    )
                )

    @bot.add_command(
        'bug:status',
        Arg('bug', type=int, help="Bug ID"),
        Arg('status', remainder=True, help='New Status')
    )
    async def cmd_bug_status(self, message, bug, status):
        """
        `$!bug:status <bug ID> <New status>` : Sets the status for the bug.
        Example: `$!bug:status 2 In Progress`
        """
        async with DBView('bugs', bugs=[]) as db:
            if bug >= len(db['bugs']):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                db['bugs'][bug]['status'] = ' '.join(status)
                await self.send_message(
                    self.fetch_channel('bugs'),
                    'Issue status changed:\n'
                    '[%d] [%s] %s : %s' % (
                        bug,
                        db['bugs'][bug]['status'],
                        ' '.join(
                            get_attr(self.get_user(user), 'mention', '') for user in
                            db['bugs'][bug]['users']
                        ),
                        db['bugs'][bug]['label'],
                    )
                )

    @bot.add_command(
        'bug:label',
        Arg('bug', type=int, help='Bug ID'),
        Arg('label', remainder=True, help="New Label")
    )
    async def cmd_bug_label(self, message, bug, label):
        """
        `$!bug:label <bug ID> <New label>` : Sets the label for a bug report.
        Example: `$!bug:label 2 $NAME's help system`
        """
        async with DBView('bugs', bugs=[]) as db:
            if bug >= len(db['bugs']):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                label = ' '.join(label)
                await self.send_message(
                    self.fetch_channel('bugs'),
                    'Issue label changed:\n'
                    '[%d] [%s] %s : %s\n'
                    'New label: %s' % (
                        bug,
                        db['bugs'][bug]['status'],
                        ' '.join(
                            get_attr(self.get_user(user), 'mention', '') for user in
                            db['bugs'][bug]['users']
                        ),
                        db['bugs'][bug]['label'],
                        label
                    )
                )
                db['bugs'][bug]['label'] = label

    @bot.add_command(
        'bug:user',
        Arg('bug', type=int, help="Bug ID"),
        Arg('user', type=UserType(bot), help="Username or ID")
    )
    async def cmd_bug_user(self, message, bug, user):
        """
        `$!bug:user <bug ID> <Username or ID>` : Subscribes a user to a bug report.
        Example: `$!bug:user 2 $ID` (that's my user ID)
        """
        async with DBView('bugs', bugs=[]) as db:
            if bug >= len(db['bugs']):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                db['bugs'][bug]['users'].append(user.id)
                await self.send_message(
                    user,
                    "You have been added to the following issue by %s:\n"
                    '[%d] [%s] : %s\n'
                    'If you would like to unsubscribe from this issue, '
                    'type `$!bug:unsubscribe %d`'% (
                        str(message.author),
                        bug,
                        db['bugs'][bug]['status'],
                        db['bugs'][bug]['label'],
                        bug
                    )
                )
                await self.send_message(
                    message.channel,
                    "Added user to issue"
                )

    @bot.add_command(
        'bug:unsubscribe',
        Arg('bug', type=int, help="Bug ID")
    )
    async def cmd_bug_unsubscribe(self, message, bug):
        """
        `$!bug:unsubscribe <bug ID>` : Unsubscribes yourself from a bug report.
        Example: `$!bug:unsubscribe 2`
        """
        async with DBView('bugs', bugs=[]) as db:
            if bug >= len(db['bugs']):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                if db['bugs'][bug]['users'][0] == message.author.id:
                    await self.send_message(
                        message.channel,
                        "As the creator of this issue, you cannot unsubscribe"
                    )
                elif message.author.id not in db['bugs'][bug]['users']:
                    await self.send_message(
                        message.channel,
                        "You are not subscribed to this issue"
                    )
                else:
                    db['bugs'][bug]['users'].remove(message.author.id)
                    await self.send_message(
                        message.channel,
                        "You have been unsubscribed from this issue:\n"
                        '[%d] [%s] : %s' % (
                            bug,
                            db['bugs'][bug]['status'],
                            db['bugs'][bug]['label']
                        )
                    )

    return bot
