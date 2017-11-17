from .core import CoreBot
from .utils import load_db, save_db, getname
import asyncio

def EnableBugs(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_command('!bug')
    async def cmd_bug(self, message, content):
        """
        `!bug [feedback or bug report]` : Opens a new ticket with your
        feedback. Example: `!bug Beymax didn't understand me in a help session`
        """
        bugs = load_db('bugs.json', [])
        bugs.append({
            'users': [message.author.id],
            'status': 'Pending', #pending->investigating->solution in progress->testing solution->closed
            'content': ' '.join(content[1:]),
            'comments':[],
            'label': ' '.join(content[1:])
        })
        await self.send_message(
            self.bug_channel,
            'New issue reported: <@&308683717419991043>\n' #@Developer
            '[%d] [Pending] %s : %s' % (
                len(bugs)-1,
                message.author.mention,
                bugs[-1]['content']
            )
        )
        save_db(bugs, 'bugs.json')

    @bot.add_command('!thread', '!bug:thread')
    async def cmd_thread(self, message, content):
        """
        `!thread <bug ID>` : Displays the full comment thread for a bug.
        Example: `!thread 2`
        """
        bugs = load_db('bugs.json', [])
        try:
            bugid = int(content[1])
            if bugid >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                body = '[%d] [%s] %s : %s\n' % (
                    bugid,
                    bugs[bugid]['status'],
                    ' '.join(
                        self.users[user]['name'] for user in
                        bugs[bugid]['users']
                    ),
                    bugs[bugid]['label'],
                )
                body += 'Issue: %s\n' % bugs[bugid]['content']
                for comment in bugs[bugid]['comments']:
                    body += 'Comment by %s\n' % comment
                await self.send_message(
                    message.channel,
                    body
                )
        except:
            await self.send_message(
                message.channel,
                "Unable to parse the bug ID from the message"
            )

    @bot.add_command('!comment', '!bug:comment')
    async def cmd_comment(self, message, content):
        """
        `!comment <bug ID> [Your comments]` : Adds your comments to the bug's
        thread. Example: `!comment 2 The help system is working great!`
        """
        bugs = load_db('bugs.json', [])
        try:
            bugid = int(content[1])
            if bugid >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                comment = ' '.join(content[2:])
                bugs[bugid]['comments'].append(
                    '%s : %s' % (
                        getname(message.author),
                        comment
                    )
                )
                await self.send_message(
                    self.bug_channel,
                    'New comment on issue:\n'
                    '[%d] [%s] %s : %s\n'
                    'Comment: [%s] : %s' % (
                        bugid,
                        bugs[bugid]['status'],
                        ' '.join(
                            self.users[user]['mention'] for user in
                            bugs[bugid]['users']
                        ),
                        bugs[bugid]['label'],
                        message.author.mention,
                        comment
                    )
                )
                save_db(bugs, 'bugs.json')
        except:
            await self.send_message(
                message.channel,
                "Unable to parse the bug ID from the message"
            )

    @bot.add_command('!bug:status')
    async def cmd_bug_status(self, message, content):
        """
        `!bug:status <bug ID> <New status>` : Sets the status for the bug.
        Example: `!bug:status 2 In Progress`
        """
        bugs = load_db('bugs.json', [])
        try:
            bugid = int(content[1])
            if bugid >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                bugs[bugid]['status'] = ' '.join(content[2:])
                await self.send_message(
                    self.bug_channel,
                    'Issue status changed:\n'
                    '[%d] [%s] %s : %s' % (
                        bugid,
                        bugs[bugid]['status'],
                        ' '.join(
                            self.users[user]['mention'] for user in
                            bugs[bugid]['users']
                        ),
                        bugs[bugid]['label'],
                    )
                )
                save_db(bugs, 'bugs.json')
        except:
            await self.send_message(
                message.channel,
                "Unable to parse the bug ID from the message"
            )

    @bot.add_command('!bug:label')
    async def cmd_bug_label(self, message, content):
        """
        `!bug:label <bug ID> <New label>` : Sets the label for a bug report.
        Example: `!bug:label 2 Beymax's help system`
        """
        bugs = load_db('bugs.json', [])
        try:
            bugid = int(content[1])
            if bugid >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                label = ' '.join(content[2:])
                await self.send_message(
                    self.bug_channel,
                    'Issue label changed:\n'
                    '[%d] [%s] %s : %s\n'
                    'New label: %s' % (
                        bugid,
                        bugs[bugid]['status'],
                        ' '.join(
                            self.users[user]['mention'] for user in
                            bugs[bugid]['users']
                        ),
                        bugs[bugid]['label'],
                        label
                    )
                )
                bugs[bugid]['label'] = label
                save_db(bugs, 'bugs.json')
        except:
            await self.send_message(
                message.channel,
                "Unable to parse the bug ID from the message"
            )

    @bot.add_command('!bug:user')
    async def cmd_bug_user(self, message, content):
        """
        `!bug:user <bug ID> <User ID>` : Subscribes a user to a bug report.
        Example: `!bug:user 2 310283932341895169` (that's my user ID)
        """
        bugs = load_db('bugs.json', [])
        try:
            bugid = int(content[1])
            if bugid >= len(bugs):
                await self.send_message(
                    message.channel,
                    "No bug with that ID"
                )
            else:
                try:
                    user = await self.get_user_info(content[2])
                    bugs[bugid]['users'].append(user.id)
                    await self.send_message(
                        user,
                        "You have been added to the following issue by %s:\n"
                        '[%d] [%s] : %s\n'
                        'If you would like to unsubscribe from this issue, '
                        'type `!bug:unsubscribe %d`'% (
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
                    save_db(bugs, 'bugs.json')
                except:
                    await self.send_message(
                        message.channel,
                        "No user with that ID"
                    )
        except:
            await self.send_message(
                message.channel,
                "Unable to parse the bug ID from the message"
            )

    @bot.add_command('!bug:unsubscribe')
    async def cmd_bug_unsubscribe(self, message, content):
        """
        `!bug:unsubscribe <bug ID>` : Unsubscribes yourself from a bug report.
        Example: `!bug:unsubscribe 2`
        """
        bugs = load_db('bugs.json', [])
        try:
            bugid = int(content[1])
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
                    save_db(bugs, 'bugs.json')
        except:
            await self.send_message(
                message.channel,
                "Unable to parse the bug ID from the message"
            )

    return bot
