# rest/statistics.py
from this import d
from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from mongoengine.queryset.visitor import Q

from models.clan import Clan
from models.match import Match
from ._common import get_response, handle_error, admin_required, empty, validate_query


class WinrateApi(Resource):

    def get(self, oid):
        try:
            # for winrate per map
            map = request.args.get("map")
            # for winrate per side, allowed values: Axis, Allies
            side = request.args.get("side")

            clan = Clan.objects.get(id=oid)
            # get all matches where the clan was either on side1 and caps1 > caps2 (condition 1)
            # or on side2 and caps1 < caps2 (condition 2)
            win_cond1 = Q(clans1_ids=str(clan.id)) & Q(caps1__gte=3)
            win_cond2 = Q(clans2_ids=str(clan.id)) & Q(caps2__gte=3)

            # if a side has been specified, the clan id must be on that side
            side_cond1 = Q(clans1_ids=str(clan.id)) & Q(side1__iexact=side)
            side_cond2 = Q(clans2_ids=str(clan.id)) & Q(side2__iexact=side)

            # only map is specified
            if not empty(map) and empty(side):
                total = Match.objects((Q(clans1_ids=str(clan.id)) | Q(clans2_ids=str(clan.id)))
                                        & Q(map__iexact=map)).count()
                wins = Match.objects((win_cond1 | win_cond2) & Q(map__iexact=map)).count()

            # only side is specified
            elif not empty(side) and empty(map):
                total = Match.objects(side_cond1 | side_cond2).count()
                wins = Match.objects((win_cond1 | win_cond2) & (side_cond1 | side_cond2)).count()

            # map and side are specified
            elif not empty(map) and not empty(side):
                total = Match.objects((side_cond1 | side_cond2) & Q(map__iexact=map)).count()
                wins = Match.objects((win_cond1 | win_cond2) & (side_cond1 | side_cond2)
                                    & Q(map__iexact=map)).count()

            # neither map nor side is specified, user requested general winrate
            else:
                total = clan.num_matches
                wins = Match.objects((win_cond1 |win_cond2)).count()
            
            return get_response({
                "total": total,
                "wins": wins,
                "winrate": round(wins / total, 3)
            })

        except ZeroDivisionError:
            return get_response({
                "total": 0,
                "wins": 0,
                "winrate": 0
            })
