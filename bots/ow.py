from .core import CoreBot
from .utils import load_db, save_db
import os
import requests
import asyncio
import random
import shutil

random.seed()


def get_mmr(user):
    url = 'http://localhost:4444/api/v3/u/%s/stats' % user
    response = requests.get(
        url,
        timeout = 3
    )
    if response.status_code == 404:
        raise ValueError("Bad Username")
    data = response.json()
    rank = data['us']['stats']['competitive']['overall_stats']['comprank']
    img = data['us']['stats']['competitive']['overall_stats']['avatar']
    return (rank if rank is not None else 0, img)

def rank(rating):
    if rating <=1499:
        return (1,'Bronze')
    elif rating <=1999:
        return (2,'Silver')
    elif rating <=2499:
        return (3,'Gold')
    elif rating <=2999:
        return (4,'Platinum')
    elif rating <=3499:
        return (5,'Diamond')
    elif rating <=3999:
        return (6,'Master')
    return (7,'Grand Master')

def encourage(n):
    if n <=2:
        pool = [
            "Good show! You gave it your all, and that's is an achivement in itself",
            "Well done! You certainly did better than I could have",
            "Meh."
        ]
    elif n<=4:
        pool = [
            "Excellent! That's no small feat!",
            "Very well done! I'm sure I could learn something from you",
            "Fantastic job! I'm proud of you!",
            "That's like, okay, I guess"
        ]
    elif n<=6:
        pool = [
            "Incredible! Advancing beyond Platinum is a monumental achivement!",
            "Wow! You climbed out of the masses and found yourself at the very peak!",
            "I've seen better"
        ]
    else:
        pool = [
            "Holy shit! You put your skills to the test, and came out on the very top!  Nicely, done!"
        ]
    return random.sample(pool,1)[0]

def postfix(n):
    if n[-1] == '1':
        return n+'st'
    elif n[-1] == '2':
        return n+'nd'
    elif n[-1] == '3':
        return n+'rd'
    return n+'th'

def EnableOverwatch(bot):
    if not isinstance(bot, CoreBot):
        raise TypeError("This function must take a CoreBot")

    @bot.add_task(3600) # 1 hour
    @bot.add_command('!owupdate')
    async def update_overwatch(self, *args): #ignore message and content args
        if os.path.isfile('stats_interim.json'):
            return
        state = load_db('stats.json')
        for uid, data in state.items():
            tag = data['tag']
            rating = data['rating']
            try:
                current, img = get_mmr(tag)
                state[uid]['rating'] = current
                state[uid]['avatar'] = img
                currentRank = rank(current)
                oldRank = rank(int(rating))
                if currentRank[0] > oldRank[0]:
                    body = "Everyone put your hands together for "
                    body += self.users[uid]['mention'] if uid in self.users else tag
                    body += " who just reached "
                    body += currentRank[1]
                    body += " in Overwatch!"
                    if 'avatar' in state[uid]:
                        body += '\n'+state[uid]['avatar']
                    if currentRank[0] >= 4:
                        # Ping the channel for anyone who reached platinum or above
                        body = body.replace('Everyone', '@everyone')
                    await self.send_message(
                        self.general, #for now
                        body
                    )
            except:
                pass
        save_db(state, 'stats.json')

    @bot.add_command('!ow')
    async def cmd_ow(self, message, content):
        path = 'stats_interim.json' if os.path.isfile('stats_interim.json') else 'stats.json'
        if len(content) != 2:
            await self.send_message(
                message.channel,
                "I need you to provide your battle tag\n"
                "For example, `!ow beymax#1234`"
            )
        else:
            username = content[1].replace('#', '-')
            try:
                state = load_db(path)
                get_mmr(username)
                state[message.author.id] = {
                    'tag': username,
                    'rating': 0
                }
                save_db(state, path)
                await self.send_message(
                    message.channel,
                    "Alright! I'll keep track of your stats"
                )
                await asyncio.sleep(15)
                await self.update_overwatch()
            except:
                await self.send_message(
                    message.channel,
                    "I wasn't able to find your Overwatch ranking via the Overwatch API.\n"
                    "Battle-tags are case-sensitive, so make sure you typed everything correctly"
                )

    @bot.add_command('!_owreset')
    async def cmd_owreset(self, message, content):
        state = load_db('stats.json')
        if len(state):
            for uid, data in state.items():
                tag = data['tag']
                rating = data['rating']
                try:
                    current, img = get_mmr(tag)
                    state[uid]['rating'] = current
                    state[uid]['avatar'] = img
                except:
                    pass
            ranked = [(data['tag'], uid, int(data['rating']), rank(int(data['rating']))) for uid, data in state.items()]
            ranked.sort(key=lambda x:(x[-1][1], x[-2])) #prolly easier just to sort by mmr
            await self.send_message(
                self.general, # for now
                "It's that time again, folks!\n"
                "The current Overwatch season has come to an end.  Let's see how well all of you did, shall we?"
            )
            index = {
                ranked[i][0]:postfix(str(len(ranked)-i)) for i in range(len(ranked))
            }
            for tag,uid,rating,(rn,rclass) in ranked:
                await self.send_message(
                    self.general,
                    "In "+index[tag]+" place, "+
                    (self.users[uid]['mention'] if uid in self.users else tag)+
                    " with a rating of "+str(rating)+"\n"
                    +encourage(rn) + (
                        ('\n'+state[uid]['avatar']) if 'avatar' in state[uid]
                        else ''
                    )
                )
            await self.send_message(
                self.general,
                "Let's give everyone a round of applause.  Great show from everybody!\n"
                "I can't wait to see how you all do next time! [Competitive ranks reset]"
            )
        for uid in state:
            state[uid]['rating'] = 0
        save_db(state, 'stats_interim.json')
        if os.path.isfile('stats.json'):
            os.remove('stats.json')


    @bot.add_command('!_owinit')
    async def cmd_owinit(self, message, content):
        shutil.move('stats_interim.json', 'stats.json')
        body = "The new Overwatch season has started! Here are the users I'm "
        body += "currently tracking statistics for:\n"
        stats = load_db('stats.json')
        for uid in stats:
            body += '%s as %s\n' % (
                self.users[uid]['name'],
                stats[uid]['tag']
            )
            stats[uid]['rating'] = 0
        body += "If anyone else would like to be tracked, use the `!ow` command."
        body += " Good luck to you all!"
        await self.send_message(
            self.general,
            body
        )
        save_db(stats, 'stats.json')

    return bot
