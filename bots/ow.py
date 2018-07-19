from .core import CoreBot
from .utils import Database, get_attr, getname
from .args import Arg, DateType
import os
import requests
from requests.exceptions import RequestException
import asyncio
import random
import shutil
from datetime import datetime

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
    tier = data['us']['stats']['competitive']['overall_stats']['tier']
    return (rank if rank is not None else 0, img, tier.title() if tier is not None else 'Unranked')

def rank(rating):
    ranks = {
        'Unranked':0,
        'Bronze':1,
        'Silver':2,
        'Gold':3,
        'Platinum':4,
        'Diamond':5,
        'Master':6,
        'Grand Master':7
    }
    return ranks[rating] if rating in ranks else 0

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
    async def update_overwatch(self):
        if os.path.isfile('stats_interim.json'):
            return
        async with Database('metadata.json') as meta:
            if 'overwatch_end_date' in meta and datetime.today() >= datetime.fromtimestamp(meta['overwatch_end_date']):
                self.dispatch('ow_season_end')
                return
        async with Database('stats.json') as state:
            for uid, data in state.items():
                tag = data['tag']
                rating = data['rating']
                old_tier = data['tier'] if 'tier' in data else 'Unranked'
                try:
                    current, img, tier = get_mmr(tag)
                    state[uid]['rating'] = current
                    state[uid]['avatar'] = img
                    state[uid]['tier'] = tier
                    currentRank = rank(tier)
                    oldRank = rank(old_tier)
                    if currentRank > oldRank:
                        body = "Everyone put your hands together for "
                        body += get_attr(self.get_user(uid), 'mention', tag)
                        body += " who just reached "
                        body += tier
                        body += " in Overwatch!"
                        if 'avatar' in state[uid]:
                            body += '\n'+state[uid]['avatar']
                        if currentRank >= 4:
                            # Ping the channel for anyone who reached platinum or above
                            body = body.replace('Everyone', '@everyone')
                        await self.send_message(
                            self.fetch_channel('general'), #for now
                            body
                        )
                except RequestException:
                    pass
            state.save()

    @bot.add_command('owupdate', empty=True)
    async def cmd_update(self, message, content):
        """
        `$!owupdate` : Manually triggers an overwatch stats update (normally once per hour)
        """
        self.dispatch('task:update_overwatch')

    @bot.add_command('ow', Arg('username', help="Your battle#tag"))
    async def cmd_ow(self, message, args):
        """
        `$!ow <battle#tag>` : Enables overwatch stats tracking
        Example: `$!ow $FULLNAME`
        """
        path = 'stats_interim.json' if os.path.isfile('stats_interim.json') else 'stats.json'
        username = args.username.replace('#', '-')
        try:
            async with Database(path) as state:
                get_mmr(username)
                state[message.author.id] = {
                    'tag': username,
                    'rating': 0,
                    'avatar':'',
                    'tier':'Unranked'
                }
                state.save()
            await self.send_message(
                message.channel,
                "Alright! I'll keep track of your stats"
            )
            if 'interim' not in path:
                await asyncio.sleep(15)
                self.dispatch('task:update_overwatch')
        except ValueError:
            await self.send_message(
                message.channel,
                "I wasn't able to find your Overwatch ranking via the Overwatch API.\n"
                "Battle-tags are case-sensitive, so make sure you typed everything correctly"
            )
        except RequestException:
            await self.send_message(
                message.channel,
                "I wasn't able to find your Overwatch ranking via the Overwatch API.\n"
                "Battle-tags are case-sensitive, so make sure you typed everything correctly"
            )

    @bot.subscribe('ow_season_end')
    async def cmd_owreset(self, event):
        async with Database('stats.json') as state:
            if len(state):
                for uid, data in state.items():
                    tag = data['tag']
                    rating = data['rating']
                    old_tier = data['tier'] if 'tier' in data else 'Unranked'
                    try:
                        current, img, tier = get_mmr(tag)
                        state[uid]['rating'] = current
                        state[uid]['avatar'] = img
                        state[uid]['tier'] = tier
                    except RequestException:
                        pass
                ranked = [(data['tag'], uid, data['tier'], int(data['rating']), rank(data['tier'])) for uid, data in state.items()]
                ranked.sort(key=lambda x:(x[-1], x[-2])) #prolly easier just to sort by mmr
                await self.send_message(
                    self.fetch_channel('general'), # for now
                    "It's that time again, folks!\n"
                    "The current Overwatch season has come to an end.  Let's see how well all of you did, shall we?"
                )
                index = {
                    ranked[i][0]:postfix(str(len(ranked)-i)) for i in range(len(ranked))
                }
                for tag,uid,tier,rating,rn in ranked:
                    await self.send_message(
                        self.fetch_channel('general'),
                        "In "+index[tag]+" place, "+
                        get_attr(self.get_user(uid), 'mention', tag)+
                        " who made "+tier+
                        " with a rating of "+str(rating)+"\n"
                        +encourage(rn) + (
                            ('\n'+state[uid]['avatar']) if 'avatar' in state[uid]
                            else ''
                        )
                    )
                await self.send_message(
                    self.fetch_channel('general'),
                    "Let's give everyone a round of applause.  Great show from everybody!\n"
                    "I can't wait to see how you all do next time! [Competitive ranks reset]"
                )
            for uid in state:
                state[uid]['rating'] = 0
                state[uid]['tier'] = 'Unranked'
            await state.save_to('stats_interim.json')
        if os.path.isfile('stats.json'):
            os.remove('stats.json')


    @bot.add_command('_owinit', Arg('end', type=DateType, help="Season end date"))
    async def cmd_owinit(self, message, args):
        """
        `$!_owinit <End Date MM/DD/YYYY>` : Triggers the overwatch start-of-season message and takes stats tracking out of interim mode
        Example: `$!_owinit 01/02/2003`
        """
        async with Database('metadata.json') as meta:
            meta['overwatch_end_date'] = args.end.timestamp()
            meta.save()
        shutil.move('stats_interim.json', 'stats.json')
        body = "The new Overwatch season has started! Here are the users I'm "
        body += "currently tracking statistics for:\n"
        async with Database('stats.json') as stats:
            for uid in stats:
                body += '%s as %s\n' % (
                    getname(self.get_user(uid)),
                    stats[uid]['tag']
                )
                stats[uid]['rating'] = 0
                stats[uid]['tier'] = 'Unranked'
            body += "If anyone else would like to be tracked, use the `!ow` command."
            body += " Good luck to you all!"
            await self.send_message(
                self.fetch_channel('general'),
                body
            )
            stats.save()

    return bot
