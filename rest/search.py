# rest/search.py

from flask_restful import Resource
from flask import request
from werkzeug.exceptions import BadRequest

from logic._getter import get_model
from schemas.query_schemas import SearchQuerySchema
from ._common import get_response, validate_schema, handle_error


class SearchApi(Resource):

    def get(self):
        try:
            validate_schema(SearchQuerySchema(), request.args)
            # example: '/search?q=core&type=match
            # query string, keyword to look for
            q = request.args.get("q")
            # type to search across, allowed values: 'clan', 'match', 'score'
            t = request.args.get("type")
            # optional, maximum number of results to return
            limit = request.args.get("limit", default=0, type=int)
            offset = request.args.get("offset", default=0, type=int)
            sort_by = request.args.get("sort_by", default=None, type=str)
            # descending order
            desc = request.args.get("desc", default=None, type=str)

            # https://www.tutorialspoint.com/mongoengine/mongoengine_text_search.htm
            # https://docs.mongoengine.org/guide/text-indexes.html
            # https://stackoverflow.com/questions/1863399/mongodb-is-it-possible-to-make-a-case-insensitive-query
            # https://www.tutorialspoint.com/mongoengine/mongoengine_indexes.htm
            cls = get_model(t)
            if desc is None:
                docs = cls.objects.search_text(q).limit(limit).skip(offset).order_by(f"+{sort_by}")
            else:
                docs = cls.objects.search_text(q).limit(limit).skip(offset).order_by(f"-{sort_by}")

        except BadRequest as e:
            # TODO: better error response
            return handle_error(f"Bad Request, terminated with: {e}", 400)
        except ValueError:
            return {
                "error": "query paramter is not valid or got an illegal value",
                "query paramters": {
                    "select": {
                        "mandatory": True,
                        "allowed_values": "any string"
                    },
                    "type": {
                        "mandatory": True,
                        "allowed_values": ["clan", "match", "score"]
                    },
                    "limit": {
                        "mandatory": False,
                        "allowed_value": "positive integers"
                    },
                    "offset": {
                        "mandatory": False,
                        "allowed_value": "positive integers"
                    }
                },
                "example": ".../search?select=core&type=match&limit=5"
            }, 422
        
        else:
            return get_response(docs)
