import datetime
from enum import Enum

from flask import current_app, redirect, request
from flask_jwt_extended import create_access_token
from flask_restful import Resource
from models.clan import Clan
from mongoengine import DoesNotExist

from ._error_handling import handle_error


class Role(Enum):
    User = 'USER'
    Admin = 'ADMIN'
    TeamManager = 'TEAM_MANAGER'


class DiscordLogin(Resource):
    discord = None

    def __init__(self, discord):
        self.discord = discord

    def get(self):
        redirect_uri = request.args.get('redirect_uri')
        if redirect_uri != current_app.config['DISCORD_AUTH_SETTINGS']['redirectUri']:
            return 'invalid_redirect_uri', 400
        return self.discord.create_session(scope=['guilds.members.read'], data=dict(redirect=redirect_uri))


class DiscordCallback(Resource):
    discord = None

    def __init__(self, discord):
        self.discord = discord

    def __resolve_guild(self, user):
        guilds = user.fetch_guilds()
        required_guild_id = int(current_app.config['DISCORD_AUTH_SETTINGS']['guildId'])
        for g in guilds:
            if g.id == required_guild_id:
                return g

        return None

    def __resolve_roles_clans(self, user_guild):
        info = self.discord.request(f'/users/@me/guilds/{user_guild.id}/member')
        helo_roles = [Role.User.value]
        helo_clans = []
        for r in info['roles']:
            if r == current_app.config['DISCORD_AUTH_SETTINGS']['adminRole']:
                helo_roles.append(Role.Admin.value)
            elif r == current_app.config['DISCORD_AUTH_SETTINGS']['teamManagerRole']:
                helo_roles.append(Role.TeamManager.value)
            else:
                try:
                    clan = Clan.objects.get(role_id=r)
                    helo_clans.append(clan.tag)
                except DoesNotExist:
                    continue
                except Exception:
                    return handle_error(f"error resolving clan membership", 500)

        return helo_roles, helo_clans

    def get(self):
        state = self.discord.callback()
        if state.get('redirect_uri') is None:
            return 'bad_request', 400
        user = self.discord.fetch_user()
        guild = self.__resolve_guild(user)

        if guild is None:
            return 'not in guild', 401

        helo_roles, helo_clans = self.__resolve_roles_clans(guild)
        access_token = create_access_token(
            identity=user.id,
            expires_delta=datetime.timedelta(hours=8),
            additional_claims={
                'roles': helo_roles,
                'clans': helo_clans,
            }
        )

        return redirect(state.get('redirect_uri') + '#' + access_token)
