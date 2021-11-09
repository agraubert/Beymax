from .utils import DBView
from agutil import hashfile
import yaml
from collections import namedtuple
import warnings
import sys
import os

Rule = namedtuple("Rule", ['allow', 'deny', 'underscore', 'type', 'data'])

class PermissionsFile(object):
    _FALLBACK_DEFAULT = Rule(['$all'], [], False, None, {})

    @staticmethod
    def validate_rule(obj, is_default=False):
        if is_default:
            if 'role' in obj or 'users' in obj:
                raise TypeError("role and users cannot be set on default permissions")
        else:
            if not (('role' in obj) ^ ('users' in obj)):
                raise TypeError("role or users must be set on each permissions object")
        if not ('allow' in obj or 'deny' in obj  or 'underscore' in obj):
            raise TypeError("Permissions object must set some permission (allow, deny, or underscore)")
        # return Rule(
        #     obj['allow'] if 'allow' in obj else None,
        #     obj['deny'] if 'deny' in obj else None,
        #     obj['underscore'] if 'underscore' in obj else None,
        #     rule_type,
        #     0 if is_default else (
        #         bot.primary
        #     )
        # )

    async def fingerprint(self, bot, filepath, users, roles):
        sha1 = hashfile(filepath).hex()
        async with DBView('permissions', permissions={}) as db:
            if not ('sha1' in db['permissions'] and db['permissions']['sha1'] == sha1):
                # File changed, reprint
                db['permissions'] = {
                    'sha1': sha1,
                    'users': {uname: uid for uname, uid in users.items()},
                    'roles': {rname: [(gid, rid) for gid,rid in role_matches] for rname, role_matches in roles.items()}
                }
                return
            mismatch = []
            if 'users' in db['permissions']:
                for uname, uid in db['permissions']['users'].items():
                    if not (uname in users and uid == users[uname]):
                        mismatch.append(
                            'User Reference "{}" previously matched User ID {} but now matches User ID {}'.format(
                                uname,
                                uid,
                                users[uname] if uname in users else '<None>'
                            )
                        )
            # if {*roles} != {*db['permissions']['roles']}:
            #     mismatch.append(
            #         "Different roles matched. Previously, these roles were matched {}, but now these roles are matched {}".format(
            #             ', '.join(db['permissions']['roles']),
            #             ', '.join(roles)
            #         )
            #     )
            for r in {*roles} | {*db['permissions']['roles']}:
                if r in roles and r in db['permissions']['roles']:
                    new_matches = [
                        (gid, rid) for gid, rid in roles[r]
                        if (gid, rid) not in db['permissions']['roles'][r]
                    ]
                    old_matches = [
                        (gid, rid) for gid, rid in db['permissions']['roles'][r]
                        if (gid, rid) not in roles[r]
                    ]
                    changed_matches = [
                        (gid, rid) for gid, rid in db['permissions']['roles'][r]
                        if (gid, rid) not in roles[r] and gid in {g for g,_ in roles[r]}
                    ]
                    if len(new_matches) + len(old_matches) + len(changed_matches) > 0:
                        mismatch.append(
                            'Role "{}" has changed matches. New matches in new guilds: {}. '
                            'Missing matches in old guilds: {}. Changed matches in old guilds: {}'.format(
                                r,
                                ', '.join(
                                    '{} in server {}'.format(
                                        rid, gid
                                    )
                                    for gid, rid in new_matches
                                ),
                                ', '.join(
                                    '{} in server {}'.format(
                                        rid, gid
                                    )
                                    for gid, rid in old_matches
                                ),
                                ', '.join(
                                    '{} in server {}'.format(
                                        rid, gid
                                    )
                                    for gid, rid in changed_matches
                                )
                            )
                        )
                elif r not in roles:
                    mismatch.append(
                        'Role "{}" no longer has any matches, but previously matched {}'.format(
                            r,
                            ', '.join(
                                '{} in server {}'.format(
                                    rid, gid
                                )
                                for gid, rid in db['permissions']['roles'][r]
                            )
                        )
                    )
                else:
                    mismatch.append(
                        'Role "{}" previously had no matches but now matches {}'.format(
                            r,
                            ', '.join(
                                '{} in server {}'.format(
                                    rid, gid
                                )
                                for gid, rid in roles[r]
                            )
                        )
                    )
            if len(mismatch) > 0:
                handling = bot.config_get('permissions_matching', default='previous')
                print('\n'.join(mismatch))
                if handling == 'strict':
                    sys.exit("\nPlease update references in permissions file to match new entities")
                elif handling == 'previous':
                    for uname, cid in db['permissions']['users'].items():
                        oid = users[uname]
                        if cid != oid:
                            for i in range(len(self.user_rules[oid])):
                                if self.user_rules[oid][i].data['reference'] == uname:
                                    print("Moving rule referenced by", uname, "from", oid, "to", cid)
                                    if cid not in self.user_rules:
                                        self.user_rules[cid] = []
                                    self.user_rules[cid].append(self.user_rules[oid][i])
                                    self.user_rules[oid][i] = Rule(
                                        [],
                                        [],
                                        None,
                                        'user',
                                        {
                                            'reference': '<None>',
                                            'priority': 1000
                                        }
                                    )
                    for rname in db['permissions']['roles']:
                        for cgid, crid in db['permissions']['roles'][rname]:
                            o_guild = roles[rname]
                            for ogid, orid in o_guild:
                                if cgid != ogid or crid != orid:
                                    for i in range(len(self.guild_rules[ogid])):
                                        if self.guild_rules[ogid][i].data['name'] == rname and cgid in {g.id for g in bot.guilds}:
                                            print("Moving rule referenced by", rname, "from", ogid, orid, "to", cgid, crid)
                                        if cgid not in self.guild_rules:
                                            self.guild_rules[cgid] = []
                                        self.guild_rules[cgid].append(self.guild_rules[ogid][i])
                                        self.guild_rules[ogid][i] = Rule(
                                            [],
                                            [],
                                            None,
                                            'role',
                                            {
                                                'name': '<None>',
                                                'gid': ogid,
                                                'id': orid,
                                                'priority': 1000
                                            }
                                        )
                elif handling == 'update':
                    db['permissions'] = {
                        'sha1': sha1,
                        'users': {uname: uid for uname, uid in users.items()},
                        'roles': {rname: [(gid, rid) for gid,rid in role_matches] for rname, role_matches in roles.items()}
                    }

    @staticmethod
    async def load(bot, filepath):
        self = PermissionsFile()
        self.bot = bot
        self.default = PermissionsFile._FALLBACK_DEFAULT
        self.user_rules = {} #uid: [rules]
        self.guild_rules = {
            guild.id: []
            for guild in bot.guilds
        }  #gid: sorted(rules, key=guild's hierarchy)
        if os.path.exists(filepath):
            with open(filepath) as reader:
                permissions = yaml.load(reader, Loader=yaml.SafeLoader)
                if not isinstance(permissions, dict):
                    raise TypeError("Permissions file '{}' must be a dictionary".format(filepath))
                if 'defaults' not in permissions:
                    raise TypeError("Permissions file '{}' must define a 'defaults' key".format(filepath))
                PermissionsFile.validate_rule(permissions['defaults'], True)
                self.default = Rule(
                    permissions['defaults']['allow'] if 'allow' in permissions['defaults'] else [],
                    permissions['defaults']['deny'] if 'deny' in permissions['defaults'] else [],
                    permissions['defaults']['underscore'] if 'underscore' in permissions['defaults'] else None,
                    None,
                    {}
                )
                # load rules, validate each, and separate into user and role lists
                users = {}
                fingerprint_roles = {}
                guild_roles = {
                    guild.id: [*guild.roles]
                    for guild in bot.guilds
                }
                if 'rules' in permissions:
                    if not isinstance(permissions['rules'], list):
                        raise TypeError("Permissions file '{}' rules must be a list".format(filepath))
                    seen_roles = set()

                    for i, rule in enumerate(permissions['rules']):
                        PermissionsFile.validate_rule(rule)
                        if 'role' in rule:
                            if rule['role'] in seen_roles:
                                raise TypeError(
                                    "Duplicate role '{}' encountered in permissions file '{}'".format(
                                        rule['role'],
                                        filepath
                                    )
                                )
                            seen_roles.add(rule['role'])
                            matched = False
                            for gid, roles in guild_roles.items(): # in hierarchy order
                                for pri, r in enumerate(roles):
                                    if rule['role'] == r.id or rule['role'] == r.name:
                                        matched = True
                                        if rule['role'] not in fingerprint_roles:
                                            fingerprint_roles[rule['role']] = []
                                        fingerprint_roles[rule['role']].append((gid, r.id))
                                        self.guild_rules[gid].append(
                                            Rule(
                                                rule['allow'] if 'allow' in rule else [],
                                                rule['deny'] if 'deny' in rule else [],
                                                rule['underscore'] if 'underscore' in rule else None,
                                                'role',
                                                {
                                                    'name': r.name,
                                                    'gid': gid,
                                                    'id': r.id,
                                                    'priority': pri
                                                }
                                            )
                                        )
                            if matched is False:
                                raise ValueError("Rule for role '{}' in permissions file '{}' did not match any guilds".format(
                                    rule['role'],
                                    filepath
                                ))
                        else:
                            # Load user rules
                            for reference in rule['users']:
                                try:
                                    uid = bot.getid(reference)
                                    users[reference] = uid
                                    if uid not in self.user_rules:
                                        self.user_rules[uid] = []
                                    self.user_rules[uid].append(Rule(
                                        rule['allow'] if 'allow' in rule else [],
                                        rule['deny'] if 'deny' in rule else [],
                                        rule['underscore'] if 'underscore' in rule else None,
                                        'user',
                                        {
                                            'priority': len(rule['users']),
                                            'reference': reference
                                        }
                                    ))
                                except NameError:
                                    raise ValueError("User reference '{}' in permissions file '{}' did not match any users".format(
                                        reference,
                                        filepath
                                    )) from e

                # check fingerprint
                await self.fingerprint(
                    bot,
                    filepath,
                    users,
                    fingerprint_roles
                )
                # build permission chains:
                for gid in self.guild_rules:
                    self.guild_rules[gid].sort(key = lambda r:r.data['priority'])
                for uid in self.user_rules:
                    self.user_rules[uid].sort(key = lambda r:r.data['priority'])
        return self

    def query(self, user, cmd=None, *, _chain=None):
        """
        Queries user permissions.
        If cmd is provided, returns the following tuple:
        * Allowed: Boolean indicating if use of the given command is allowed in the user's context
        * Rule: The rule used for this decision
        If cmd is not provided (default), return a list of rules which apply to
        the user, in order from highest priority to lowest.
        """
        if _chain is None:
            _chain = []
            if user.id in self.user_rules:
                _chain += [rule for rule in self.user_rules[user.id]]
            if self.bot.primary_guild is not None:
                u = self.bot.primary_guild.get_member(user.id)
                if u is not None:
                    user = u
            if hasattr(user, 'roles') and hasattr(user, 'guild'):
                user_roles = {role.id for role in user.roles}
                if user.guild.id in self.guild_rules:
                    for rule in self.guild_rules[user.guild.id]:
                        if rule.data['id'] in user_roles:
                            _chain.append(rule)
            _chain += [self.default, PermissionsFile._FALLBACK_DEFAULT]
        if cmd is not None:
            for rule in _chain:
                if cmd in rule.allow or (not cmd.startswith('_') and '$all' in rule.allow):
                    return True, rule
                elif cmd in rule.deny or (not cmd.startswith('_') and '$all' in rule.deny):
                    return False, rule
                elif cmd.startswith('_') and rule.underscore is not None:
                    return rule.underscore, rule
            raise RuntimeError("There should always be a valid rule for any command")
        return _chain

    def query_underscore(self, user, *, _chain=None):
        """
        Checks if the given user has admin privileges.
        Returns the following tuple:
        * Allowed: Boolean indicating if underscore commands are allowed
        * Rule: The rule used for this decision
        """
        if _chain is None:
            _chain = self.query(user)
        for rule in _chain:
            if rule.underscore is not None:
                return rule.underscore, rule
        raise RuntimeError("There should always be a valid rule for any command")
