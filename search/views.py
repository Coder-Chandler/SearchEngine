import json
from django.shortcuts import render
from django.views.generic.base import View
from search.models import ArticleType, ZhihuQuestionType, ZhihuAnswerType, LaGou
from django.http import HttpResponse
from elasticsearch import Elasticsearch
from datetime import datetime
import redis

client = Elasticsearch(hosts="127.0.0.1")
redis_cli = redis.StrictRedis()


class IndexView(View):
    # 首页
    def get(self, request):
        topn_search = redis_cli.zrevrangebyscore("search_keywords_set", "+inf", "-inf", start=0, num=5)
        return render(request, "index.html", {"topn_search": topn_search})


def index_suggest(value, key_words):
    # 搜索建议的辅助函数
    re_datas = []
    s = value.search()
    s = s.suggest('my_suggest', key_words, completion={
        "field": "suggest", "fuzzy": {
            "fuzziness": 2
        },
        "size": 10
    })
    suggestions = s.execute_suggest()
    for match in suggestions.my_suggest[0].options:
        sourse = match._source
        re_datas.append(sourse["title"])
    return re_datas


# Create your views here.
class SearchSuggest(View):
    def get(self, request):
        key_words = request.GET.get('s', '')
        click_words = request.GET.get('s_type', '')
        re_datas = []
        if key_words:
            if click_words == "article":
                re_datas = index_suggest(ArticleType, key_words)
            elif click_words == "job":
                re_datas = index_suggest(LaGou, key_words)
        return HttpResponse(json.dumps(re_datas), content_type="application/json")


def SearchResult(tag, key_words, page):
    response = client.search(
        index=tag,
        body={
            "query": {
                "multi_match": {
                    "query": key_words,
                    "fields": ["tags", "title", "content"]
                }
            },
            "from": (page - 1) * 10,
            "size": 10,
            "highlight": {
                "pre_tags": ['<span class="keyWord">'],
                "post_tags": ['</span class="keyWord">'],
                "fields": {
                    "title": {},
                    "content": {},
                }
            }
        }
    )
    return response


class SearchView(View):
    def get(self, request):
        key_words = request.GET.get("q", "")
        s_type = request.GET.get("s_type", "article")
        redis_cli.zincrby("search_keywords_set", key_words)

        topn_search = redis_cli.zrevrangebyscore("search_keywords_set", "+inf", "-inf", start=0, num=5)
        page = request.GET.get("p", "1")
        try:
            page = int(page)
        except:
            page = 1
        jobbole_count = redis_cli.get("jobbole_count")
        lagoujob_count = redis_cli.get("lagoujob_count")
        start_time = datetime.now()
        response = SearchResult("jobbole", key_words, page)
        end_time = datetime.now()
        last_seconds = (end_time - start_time).total_seconds()
        total_nums = response["hits"]["total"]
        if (page % 10) > 0:
            page_nums = int(total_nums/10) + 1
        else:
            page_nums = int(total_nums/10)
        hit_list = []
        for hit in response["hits"]["hits"]:
            hit_dict = {}
            if "title" in hit["highlight"]:
                hit_dict["title"] = "".join(hit["highlight"]["title"])
            else:
                hit_dict["title"] = hit["_source"]["title"]
            if "content" in hit["highlight"]:
                hit_dict["content"] = "".join(hit["highlight"]["content"])[:500]
            else:
                hit_dict["content"] = hit["_source"]["content"][:500]

            hit_dict["create_date"] = hit["_source"]["create_date"]
            hit_dict["url"] = hit["_source"]["url"]
            hit_dict["score"] = hit["_score"]

            hit_list.append(hit_dict)
        return render(request, "result.html", {"page": page,
                                               "s_type": s_type,
                                               "all_hits": hit_list,
                                               "key_words": key_words,
                                               "total_nums": total_nums,
                                               "page_nums": page_nums,
                                               "last_seconds": last_seconds,
                                               "jobbole_count": jobbole_count,
                                               "lagoujob_count": lagoujob_count,
                                               "topn_search": topn_search})
