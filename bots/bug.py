from .core import CoreBot
from .utils import DBView, getname, get_attr
from .args import Arg, UserType
import asyncio

def EnableBugs(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    bot.reserve_channel('bugs')

    @bot.add_command(
        'bug',
        Arg(
            'message',
            type='extra',
            help='Your feedback or bug report'
        ),
    )
    async def cmd_bug(self, message, args):
        """
        `$!bug [feedback or bug report]` : Opens a new ticket with your
        feedback. Example: `$!bug $NAME didn't understand me in a help session`
        """
        content = ' '.join([args.message] + args.extra)
        async with ListDatabase('bugs.json') as bugs:
            bugs.append({
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
                    len(bugs)-1,
                    message.author.mention,
                    bugs[-1]['content']
                )
            )
            bugs.save()

    @bot.add_command('thread', Arg('bug', type=int, help="Bug ID"), aliases=['bug:thread'])
    async def cmd_thread(self, message, args):
        """
        `$!thread <bug ID>` : Displays the full comment thread for a bug.
        Example: `$!thread 2`
        """
        async with ListDatabase('bugs.json') as bugs:
            if args.bug >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                body = '[%d] [%s] %s : %s\n' % (
                    args.bug,
                    bugs[args.bug]['status'],
                    ' '.join(
                        getname(self.get_user(user)) for user in
                        bugs[args.bug]['users']
                    ),
                    bugs[args.bug]['label'],
                )
                body += 'Issue: %s\n' % bugs[args.bug]['content']
                for comment in bugs[args.bug]['comments']:
                    body += 'Comment by %s\n' % comment
                await self.send_message(
                    message.channel,
                    body
                )

    @bot.add_command(
        'comment',
        Arg('bug', type=int, help="Bug ID"),
        Arg('comment', type='extra', help="Your comments"),
        aliases=['bug:comment']
    )
    async def cmd_comment(self, message, args):
        """
        `$!comment <bug ID> [Your comments]` : Adds your comments to the bug's
        thread. Example: `$!comment 2 The help system is working great!`
        """
        async with ListDatabase('bugs.json') as bugs:
            bugid = args.bug
            if bugid >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                comment = ' '.join([args.comment] + args.extra)
                bugs[bugid]['comments'].append(
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
                        bugid,
                        bugs[bugid]['status'],
                        ' '.join(
                            get_attr(self.get_user(user), 'mention', '') for user in
                            bugs[bugid]['users']
                        ),
                        bugs[bugid]['label'],
                        message.author.mention,
                        comment
                    )
                )
                bugs.save()

    @bot.add_command(
        'bug:status',
        Arg('bug', type=int, help="Bug ID"),
        Arg('status', type='extra', help='New Status')
    )
    async def cmd_bug_status(self, message, args):
        """
        `$!bug:status <bug ID> <New status>` : Sets the status for the bug.
        Example: `$!bug:status 2 In Progress`
        """
        async with ListDatabase('bugs.json') as bugs:
            bugid = args.bug
            if bugid >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                bugs[bugid]['status'] = ' '.join([args.status] + args.extra)
                await self.send_message(
                    self.fetch_channel('bugs'),
                    'Issue status changed:\n'
                    '[%d] [%s] %s : %s' % (
                        bugid,
                        bugs[bugid]['status'],
                        ' '.join(
                            get_attr(self.get_user(user), 'mention', '') for user in
                            bugs[bugid]['users']
                        ),
                        bugs[bugid]['label'],
                    )
                )
                bugs.save()

    @bot.add_command(
        'bug:label',
        Arg('bug', type=int, help='Bug ID'),
        Arg('label', type='extra', help="New Label")
    )
    async def cmd_bug_label(self, message, args):
        """
        `$!bug:label <bug ID> <New label>` : Sets the label for a bug report.
        Example: `$!bug:label 2 $NAME's help system`
        """
        async with ListDatabase('bugs.json') as bugs:
            bugid = args.bug
            if bugid >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                label = ' '.join([args.label] + args.extra)
                await self.send_message(
                    self.fetch_channel('bugs'),
                    'Issue label changed:\n'
                    '[%d] [%s] %s : %s\n'
                    'New label: %s' % (
                        bugid,
                        bugs[bugid]['status'],
                        ' '.join(
                            get_attr(self.get_user(user), 'mention', '') for user in
                            bugs[bugid]['users']
                        ),
                        bugs[bugid]['label'],
                        label
                    )
                )
                bugs[bugid]['label'] = label
                bugs.save()

    @bot.add_command(
        'bug:user',
        Arg('bug', type=int, help="Bug ID"),
        Arg('user', type=UserType(bot), help="Username or ID")
    )
    async def cmd_bug_user(self, message, args):
        """
        `$!bug:user <bug ID> <Username or ID>` : Subscribes a user to a bug report.
        Example: `$!bug:user 2 $ID` (that's my user ID)
        """
        async with ListDatabase('bugs.json') as bugs:
            bugid = args.bug
            if bugid >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                bugs[bugid]['users'].append(args.user.id)
                await self.send_message(
                    args.user,
                    "You have been added to the following issue by %s:\n"
                    '[%d] [%s] : %s\n'
                    'If you would like to unsubscribe from this issue, '
                    'type `$!bug:unsubscribe %d`'% (
                        str(message.author),
                        bugid,
                        bugs[bugid]['status'],
                        bugs[bugid]['label'],
                        bugid
                    )
                )
                await self.send_message(
                    message.channel,
                    "Added user to issue"
                )
                bugs.save()

    @bot.add_command(
        'bug:unsubscribe',
        Arg('bug', type=int, help="Bug ID")
    )
    async def cmd_bug_unsubscribe(self, message, args):
        """
        `$!bug:unsubscribe <bug ID>` : Unsubscribes yourself from a bug report.
        Example: `$!bug:unsubscribe 2`
        """
        async with ListDatabase('bugs.json') as bugs:
            bugid = args.bug
            if bugid >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                if bugs[bugid]['users'][0] == message.author.id:
                    await self.send_message(
                        message.channel,
                        "As the creator of this issue, you cannot unsubscribe"
                    )
                elif message.author.id not in bugs[bugid]['users']:
                    await self.send_message(
                        message.channel,
                        "You are not subscribed to this issue"
                    )
                else:
                    bugs[bugid]['users'].remove(message.author.id)
                    await self.send_message(
                        message.channel,
                        "You have been unsubscribed from this issue:\n"
                        '[%d] [%s] : %s' % (
                            bugid,
                            bugs[bugid]['status'],
                            bugs[bugid]['label']
                        )
                    )
                    bugs.save()

    return bot
