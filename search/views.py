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
        try:
            re_datas.append(sourse["title"])
        except KeyError:
            re_datas.append(sourse["content"][:50])
    return re_datas


# Create your views here.
class SearchSuggest(View):
    def get(self, request):
        key_words = request.GET.get('s', '')
        s_type = request.GET.get('s_type', '')
        re_datas = []
        if key_words:
            if s_type == "article":
                re_datas = index_suggest(ArticleType, key_words)
            elif s_type == "job":
                re_datas = index_suggest(LaGou, key_words)
            elif s_type == "question":
                if key_words:
                    re_datas = index_suggest(ZhihuQuestionType, key_words)
                else:
                    re_datas = index_suggest(ZhihuAnswerType, key_words)
        return HttpResponse(json.dumps(re_datas), content_type="application/json")


def client_search(tag, key_words, page):
    # 代码复用， 定义搜索项目
    return client.search(
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
                "post_tags": ['</span>'],
                "fields": {
                    "title": {},
                    "content": {},
                }
            }
        }
    )


def get_hit_dict(s_type, hit_dict, hit, content, create_date):
    # 代码复用，把数据传进client_search
    hit_dict["from"] = s_type
    try:
        if "title" in hit.get("highlight", ""):
            hit_dict["title"] = "".join(hit["highlight"]["title"])
        else:
            hit_dict["title"] = hit["_source"]["title"]
    except KeyError:
        hit_dict["title"] = hit["_source"][content][:50]
    if "content" in hit.get("highlight", ""):
        hit_dict["content"] = "".join(hit["highlight"][content])[:500]
    else:
        hit_dict["content"] = hit["_source"][content][:500]
    try :
        hit_dict["create_date"] = hit["_source"][create_date]
    except KeyError:
        hit_dict["create_date"] = hit["_source"]["crawl_time"]
    try:
        hit_dict["tags"] = hit["_source"]["topics"]
    except KeyError:
        hit_dict["tags"] = hit["_source"][content][:50]
    try:
        hit_dict["url"] = hit["_source"]["url"]
    except KeyError:
        hit_dict["url"] = "https://www.zhihu.com/question/{0}".format(hit["_source"]["question_id"])
    hit_dict["score"] = hit["_score"]
    return hit_dict


# class Detail(View):
def SearchResult(key_words, page, s_type):
    # 单独定义获取搜索页面所需要的数据，以便代码复用
    tag = ""
    if s_type == "article":
        tag = "jobbole"
    if s_type == "job":
        tag = "lagou"
    if s_type == "question":
        tag = "zhihu"
    return client_search(tag, key_words, page)


def GetTagDetail(response, s_type):
    hit_list = []
    for hit in response["hits"]["hits"]:
        hit_dict = {}
        if s_type == "article":
            name = "伯乐在线"
            time = "create_date"
            content = "content"
            hit_dict = get_hit_dict(name, hit_dict, hit, content, time)
        if s_type == "job":
            name = "拉勾网"
            time = "publish_time"
            content = "job_desc"
            hit_dict = get_hit_dict(name, hit_dict, hit, content, time)
        if s_type == "question":
            name = "知乎"
            time = "create_date"
            content = "content"
            hit_dict = get_hit_dict(name, hit_dict, hit, content, time)
        hit_list.append(hit_dict)
    return hit_list


class SearchView(View):
    def get(self, request):
        key_words = request.GET.get("q", "")
        # click_words = request.GET.get('s_type', '')
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
        ZhihuQuestion_count = redis_cli.get("ZhihuQuestion_count")
        ZhihuAnswer_count = redis_cli.get("ZhihuAnswer_count")
        start_time = datetime.now()
        response = SearchResult(key_words, page, s_type)
        end_time = datetime.now()
        last_seconds = (end_time - start_time).total_seconds()
        total_nums = int(response["hits"]["total"])
        if (page % 10) > 0:
            page_nums = int(total_nums / 10) + 1
        else:
            page_nums = int(total_nums / 10)
        hit_list = GetTagDetail(response, s_type)
        return render(request, "result.html", {"page": page,
                                               "s_type": s_type,
                                               "all_hits": hit_list,
                                               "key_words": key_words,
                                               "total_nums": total_nums,
                                               "page_nums": page_nums,
                                               "last_seconds": last_seconds,
                                               "jobbole_count": jobbole_count,
                                               "lagoujob_count": lagoujob_count,
                                               "ZhihuQuestion_count": ZhihuQuestion_count,
                                               "ZhihuAnswer_count": ZhihuAnswer_count,
                                               "topn_search": topn_search})
