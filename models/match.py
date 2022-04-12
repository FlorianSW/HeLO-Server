"""
first level class
"""

from database.db import db


class Match(db.Document):
    # something like "StDb-91.-2022-01-07" what ever
    match_id = db.StringField(required=True, unique=True)
    # unique identifiers (very long number) of the clan -> oid of the clan object in DB
    clans1_ids = db.ListField()
    clans2_ids = db.ListField()
    # clan tag mapped to the number of players they fielded
    # e.g. {"CoRe": 30, "StDb": 20}
    # player distribution is not required, and should be None if not provided
    player_dist1 = db.DictField()
    player_dist2 = db.DictField()
    # allies or axis
    side1        = db.StringField()
    side2        = db.StringField()
    # strong points hold at the end of the game
    caps1        = db.IntField()
    caps2        = db.IntField()
    # number of players on each side (assuming both teams had the same number of players)
    players      = db.IntField()
    map          = db.StringField()
    date         = db.DateTimeField(required=True)
    # how long the game lasted, max is 90 min
    duration     = db.IntField()
    # competitive factor, see HeLO calculations
    factor       = db.FloatField()
    # name of the tournament, of just a training match
    event        = db.StringField()
    # confirmation, very important
    # match must be confirmed from both sides (representatives) in order to
    # take the match into account
    # user id of the user who confirmed the match for clan1
    conf1        = db.StringField()
    # user id of the user who confirmed the match for clan2
    conf2        = db.StringField()
    # flag to check whether corresponding score objects to the match exist or not
    score_posted = db.BooleanField()
    # reserved for admins, necessary to start a recalculate process for this match
    # will be set only temporarily
    recalculate = db.BooleanField()
    meta = {
        "indexes": [
            {
                "fields": ["$match_id", "$map", "$event"]
            }
        ]
    }

    def needs_confirmations(self):
        if (self.conf1 != "" and self.conf1 is not None) and (self.conf2 != "" and self.conf2 is not None):
            # do the calcs then
            return False
        else:
            return True
