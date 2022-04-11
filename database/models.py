# database/models.py
from datetime import date

from logic.calculations import get_new_scores, get_coop_scores
from .db import db
from mongoengine.queryset.visitor import Q
from mongoengine.errors import DoesNotExist
from flask_bcrypt import generate_password_hash, check_password_hash


"""
first level class
"""
class Clan(db.Document):
    # e.g. StDb for Stoßtrupp Donnerbalken
    tag = db.StringField(required=True, unique=True)
    # full name
    name = db.StringField()
    # discord icon flag, e.g. :flag_eu:, :flag_de:, ...
    flag = db.StringField()
    # discord invite link to a clan's discord server
    invite = db.StringField()
    # current HeLO Score
    score = db.IntField(default=600)
    # number of games
    num_matches = db.IntField(default=0)
    # confirmation, reserved ??
    conf = db.StringField()
    # alternative tags, if a clan was renamed, reserved
    alt_tags = db.ListField()
    

"""
first level class
"""
class Event(db.Document):
    # acronym of the event, like HPL = Hell Let Loose Premier League
    tag = db.StringField(required=True, unique=True)
    # corresponding name to the tag
    name = db.StringField()
    # event emoji, e.g. :hpl:
    emoji = db.StringField()
    # factor for score, e.g. extra sweaty = 1.2
    factor = db.FloatField()
    # discord invite link to the event's discord server
    invite = db.StringField()
    # confirmation, reserved ??
    conf = db.StringField()


"""
first level class
"""
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

    def needs_confirmations(self):
        if (self.conf1 != "" and self.conf1 is not None) and (self.conf2 != "" and self.conf2 is not None):
            # do the calcs then
            return False
        else:
            return True

    def get_clan_objects(self):
        clans1 = [Clan.objects.get(id=oid) for oid in self.clans1_ids]
        clans2 = [Clan.objects.get(id=oid) for oid in self.clans2_ids]
        return clans1, clans2

    def calc_scores(self, scores1=None, num_matches1=None, scores2=None, num_matches2=None, recalculate=False):
        clans1, clans2 = self.get_clan_objects()
        # hier nihct aus clan, sondern letztes Match object (vor diesem nehmen)
        # z.b. über datum
        if scores1 is None and num_matches1 is None and scores2 is None and num_matches2 is None:
            scores1, scores2 = [[clan.score for clan in clans1], [clan.score for clan in clans2]]
            num_matches1, num_matches2 = [[clan.num_matches for clan in clans1], [clan.num_matches for clan in clans2]]
        # else:
        #     scores1, scores2 = scores[0], scores[1]
        #     num_matches1, num_matches2 = num_matches[0], num_matches[1]

        if set(clans1) & set(clans2):
            # a clan cannot play against itself
            raise RuntimeError

        # check if it is a coop game or a normal game
        if len(self.clans1_ids) == 1 and len(self.clans2_ids) == 1:
            score1, score2, err = get_new_scores(scores1[0], scores2[0],
                                                        self.caps1, self.caps2,
                                                        num_matches1[0],
                                                        num_matches2[0],
                                                        self.factor, self.players)
            # for compatibility reasons
            scores1, scores2 = [score1], [score2]
        
        else:
            scores1, scores2, err = get_coop_scores(scores1, scores2, self.caps1,
                                                            self.caps2, self.factor,
                                                            self.player_dist1.items(),
                                                            self.player_dist2.items(),
                                                            self.players)

        self._save_clans_and_scores(clans1, clans2, scores1, scores2, num_matches1, num_matches2, recalculate=recalculate)
        self.score_posted = True
        self.save()

        return err

    def _save_clans_and_scores(self, clans1, clans2, scores1, scores2, num_matches1, num_matches2, recalculate=False):
        for clan, score, num_matches in list(zip(clans1, scores1, num_matches1)) + list(zip(clans2, scores2, num_matches2)):
            # get the score object which matches the match_id and the clan (id)
            score_queryset = Score.objects(Q(match_id=self.match_id) & Q(clan=str(clan.id)))
            # update or insert if it does not exist
            res = score_queryset.update_one(set__score=score, upsert=True, full_result=True)

            # check if it was an insert or update, this is important for the number of matches
            if res.raw_result.get("updatedExisting"):
                clan.update(score=score)

            else:
                clan.update(score=score, inc__num_matches=1)

                if recalculate:
                    # +1, because the num_matches is before the score has been calculated
                    # we need to replace the matching score object's num_matches after the calculation
                    num = num_matches + 1
                    # update all scores after the match
                    # TODO: make this all more efficient
                    # all matches after the match that is new (including the match itself, because of 'gte' but ...)
                    matches_after = Match.objects(Q(date__gte=self.date))
                    # all scores after the match that is new
                    scores_after = [Score.objects(Q(clan=str(clan.id)) & Q(match_id=match.match_id)) for match in matches_after]
                    # update every match that comes after the new match
                    for score in scores_after:
                        score.update_one(inc__num_matches=1)
                    # ... it does not matter, because we are setting the num_matches to the correct value here
                    score_queryset.update_one(set__num_matches=num)

                else:
                    clan.reload()
                    # TODO: BUG, if there is no Score object and we recalculate, the num_matches is set
                    # to the clan's num_matches, even if this isn't the true num_matches
                    # edit: bug fixed for the moment with 'if recalculate'
                    score_queryset.update_one(set__num_matches=clan.num_matches)

    def start_recalculation(self):
        clans1, clans2 = self.get_clan_objects()
        scores1, num_matches1 = zip(*[self._get_score_and_num_matches(clan) for clan in clans1])
        scores2, num_matches2 = zip(*[self._get_score_and_num_matches(clan) for clan in clans2])
        print(self.match_id)
        # calculate new scores
        err = self.calc_scores(scores1, num_matches1, scores2, num_matches2, recalculate=True)

        # get all updated teams
        updated_teams = clans1 + clans2

        # get all matches where date is greater
        # note, that some teams play multiple games on one day
        # that's why we use gte = greater than or equal to
        # but this also delivers the same match as self ...
        all_matches = []
        for match in Match.objects(date__gte=self.date):
            # ... just discard it
            if match.match_id == self.match_id:
                continue
            else:
                all_matches.append(match)

        # sort all matches by ascending date
        all_matches.sort(key=lambda x: x.date)
        for match in all_matches:
            clans1, clans2 = match.get_clan_objects()
            updated_teams.extend(clans1 + clans2)
            # makes searching more efficient if there are no dublicates
            updated_teams = list(set(updated_teams))
            # get the scores and number of matches for the recalculation
            # TODO: make this more efficient by storing all scores and num_matches
            # then we do not have to make database calls
            scores1, num_matches1 = zip(*[match._get_score_and_num_matches(clan) for clan in clans1])
            scores2, num_matches2 = zip(*[match._get_score_and_num_matches(clan) for clan in clans2])
            _ = match.calc_scores(scores1, num_matches1, scores2, num_matches2, recalculate=True)

        self.recalculate = False
        self.save()

    def _get_score_and_num_matches(self, clan):
        score_obj = Score.get_by_clan_id(self, str(clan.id))
        num = score_obj.num_matches
        # if there does not exist a score object, because the match was added afterwards,
        # then we do not have to go back another step / take the score object before that
        # otherwise we need to use the old score (one match before the given match)
        if self.score_posted:
            score_obj = Score.get_by_num_matches(str(clan.id), num - 1)
        score = score_obj.score
        return score, num
        


        
"""
second level class
"""
class User(db.Document):
    # discord id, very long number
    userid = db.StringField(required=True, unique=True)
    # required for login
    pin = db.StringField()
    name = db.StringField()
    # admin or teamrep (team representative)
    role = db.StringField(required=True)
    clan = db.StringField()
    # confirmation of a user (id), reserved ??
    conf = db.StringField()
 
    def hash_password(self):
        self.pin = generate_password_hash(self.pin).decode('utf8')
 
    def check_password(self, pin):
        return check_password_hash(self.pin, pin)


"""
class to store all scores from all clans, this class should be understood as QoL class,
that make things easier in the long run, but should not be considered as "first level class"
Every new score will be stored in a Score object. The maximum amount of score objects
for one clan is the sum of all matches of the clan.
One match results automatically in at least two Score Objects.
"""
class Score(db.Document):
    clan = db.StringField(required=True)
    # number of games, = 31 means it's the score gained from the 31st match
    num_matches = db.IntField(required=True)
    # match id of the match where the score calculation
    # is based on, something like "StDb-91.-2022-01-07"
    match_id = db.StringField(required=True)
    score = db.IntField(required=True)
    # redundant, because with "count" and "clan" we can extract the old score
    # besides when creating the Score object, we don't need to care about
    # double checking whether the score in the corresponding clan object is the same
    # IMPORTANT: clan.score must be updated first!
    # score_before = db.IntField(required=True)

    def __init__(self, clan: str, num_matches: int, match_id: str, score: int, *args, **kwargs):
        super().__init__()
        self.clan = clan
        self.num_matches = num_matches
        self.match_id = match_id
        self.score = score

    @classmethod
    def from_match(cls, match: Match, clan: Clan):
        """Alternative constructor.

        Args:
            match (Match): Match object the calculation is based on
            clan (Clan): Clan that the score belongs to

        Returns:
            Score: the new Score object
        """
        # clan.id is the oid of the Clan object in the DB
        return cls(str(clan.id), clan.num_matches, match.match_id, clan.score)

    @staticmethod
    def get_by_clan_id(match: Match, clan_id: str):
        try:
            return Score.objects.get(Q(match_id=match.match_id) & Q(clan=clan_id))
        # if the match haven't been confirmed, there won't be a matching Score object
        # in this case, find the last (before the given one) match by date
        except DoesNotExist:
            matches = []
            for m in Match.objects(Q(date__lte=match.date) & (Q(clans1_ids__in=[clan_id]) | (Q(clans2_ids__in=[clan_id])))):
                # discard the match itself, but we need 'lte' in case there is
                # another match on this day
                if m.match_id == match.match_id:
                    continue
                else:
                    matches.append(m)
            # sort matches, latest (before the current) first
            # e.g. 2022-03-03 -> 2022-03-02 -> ...
            matches.sort(key=lambda x: x.date, reverse=True)
            # if there is no match at all, return default score object with 600
            try:
                return Score.get_by_clan_id(matches[0], clan_id)
            except IndexError:
                return Score(clan_id, 0, "DefaultScore", 600)

    @staticmethod
    def get_by_num_matches(clan_id: str, num_matches: int):
        try:
            return Score.objects.get(Q(clan=clan_id) & Q(num_matches=num_matches))
        except DoesNotExist:
            return Score(clan_id, 0, "DefaultScore", 600)
