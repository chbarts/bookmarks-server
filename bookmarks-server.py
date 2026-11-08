#!/usr/bin/env python3

from http.server import HTTPServer as BaseHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, UTC
from functools import partial
import argparse
import sqlite3
import html
import time
import sys
import os
import re

# http://base/?min=1996-12-19T16:40:00&max=1996-12-19T16:50:05
base = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Bookmarks Server</title></head>
<body>
<form action="/search" method="GET">

<div>
<label for="tag">Tag: </label>
<input id="tag" name="tag" type="text" value="{tag}">
</div>

<div>
<label for="min">Beginning date and time: </label>
<input id="min" name="min" type="datetime-local" value="{mindef}" step=1>
</div>

<div>
<label for="max">Ending date and time: </label>
<input id="max" name="max" type="datetime-local" value="{maxdef}" step=1>
</div>

<div>
<label for="title">Title regular expression: </label>
<input id="title" name="title" type="text" value="{treg}">
</div>

<div>
<label for="url">URL regular expression: </label>
<input id="url" name="url" type="text" value="{ureg}">
</div>

<div>
<input type="submit" value="Submit">
</div>

</form>
<p><a href="/">Reset all filters</a></p>
<p><a href="/tags">Show all tags</a></p>
{res}
</body>
"""

class BookmarksSearch:
    def regex(self, expr, item):
        reg = re.compile(expr)
        return reg.search(item) is not None


    def make_connection(self):
        con = sqlite3.connect("file:{}?immutable=1".format(self.dbfile))
        con.create_function("REGEXP", 2, self.regex)
        return con

    def get_all_tags(self):
        return []

    

class Firefox(BookmarksSearch):
    def __init__(self, dbfile):
        self.dbfile = dbfile


    queryByTag = '''SELECT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = :tagid AND p.id = b.fk) i
    WHERE i.id = b.fk AND title NOT NULL'''

    queryTagId = "SELECT id FROM moz_bookmarks WHERE parent = 4 AND title = :tag"

    queryTags = "SELECT title FROM moz_bookmarks WHERE parent = 4 ORDER BY title"

    queryByAdded = '''SELECT DISTINCT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL ORDER BY dateAdded ASC'''

    queryByTagAndAdded = '''SELECT DISTINCT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = :tagid AND p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL ORDER BY dateAdded ASC'''

    queryByTitleRegexAndAdded = '''SELECT DISTINCT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (title REGEXP :regex) ORDER BY dateAdded ASC'''

    queryByUrlRegexAndAdded = '''SELECT DISTINCT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (url REGEXP :regex) ORDER BY dateAdded ASC'''

    queryByTitleAndUrlRegexAndAdded = '''SELECT DISTINCT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (title REGEXP :tregex) AND (url REGEXP :uregex) ORDER BY dateAdded ASC'''

    queryByTitleRegexAndTagAndAdded = '''SELECT DISTINCT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = :tagid AND p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (title REGEXP :regex) ORDER BY dateAdded ASC'''

    queryByUrlRegexAndTagAndAdded = '''SELECT DISTINCT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = :tagid AND p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (url REGEXP :regex) ORDER BY dateAdded ASC'''

    queryByTitleAndUrlRegexAndTagAndAdded = '''SELECT DISTINCT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = :tagid AND p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (title REGEXP :tregex) AND (url REGEXP :uregex) ORDER BY dateAdded ASC'''

    queryTagsByBookmark = '''SELECT id,title
    FROM moz_bookmarks b
    JOIN
      (SELECT parent FROM moz_bookmarks WHERE fk = :bmid) i
    WHERE b.parent = 4 AND b.id = i.parent'''


    def make_date(self, stamp):
        return time.localtime(int(stamp) / 1000000)


    def find_tags(self, bmid):
        res = []
        db = self.make_connection()
        cursor = db.cursor()
        for row in cursor.execute(self.queryTagsByBookmark, ({"bmid": bmid})):
            res.append(row[1])
        db.close()
        return res

    
    def get_tagid(self, tag):
        db = self.make_connection()
        cursor = db.cursor()
        cursor.execute(self.queryTagId, ({"tag": tag}))
        res = cursor.fetchone()
        db.close()
        if res:
            return res[0]
        return None


    def get_all_tags(self):
        db = self.make_connection()
        cursor = db.cursor()
        res = []
        for row in cursor.execute(self.queryTags):
            res.append(row[0])
        db.close()
        return res


    def get_bookmarks_by_added(self, beg, end):
        res = []
        db = self.make_connection()
        cursor = db.cursor()
        for row in cursor.execute(self.queryByAdded, ({"beg": beg, "end": end})):
            res += [{"id": row[0], "title": row[1], "url": row[2], "added": self.make_date(row[3]), "modified": self.make_date(row[4])}]
        db.close()
        return res


    def get_bookmarks_by_tag_and_added(self, beg, end, tagid):
        res = []
        db = self.make_connection()
        cursor = db.cursor()
        for row in cursor.execute(self.queryByTagAndAdded, ({"tagid": tagid, "beg": beg, "end": end})):
            res += [{"id": row[0], "title": row[1], "url": row[2], "added": self.make_date(row[3]), "modified": self.make_date(row[4])}]
        db.close()
        return res


    def get_bookmarks_by_title_regex_and_added(self, regex, beg, end):
        res = []
        db = self.make_connection()
        cursor = db.cursor()
        for row in cursor.execute(self.queryByTitleRegexAndAdded, ({"regex": regex, "beg": beg, "end": end})):
            res += [{"id": row[0], "title": row[1], "url": row[2], "added": self.make_date(row[3]), "modified": self.make_date(row[4])}]
        db.close()
        return res


    def get_bookmarks_by_url_regex_and_added(self, regex, beg, end):
        res = []
        db = self.make_connection()
        cursor = db.cursor()
        for row in cursor.execute(self.queryByUrlRegexAndAdded, ({"regex": regex, "beg": beg, "end": end})):
            res += [{"id": row[0], "title": row[1], "url": row[2], "added": self.make_date(row[3]), "modified": self.make_date(row[4])}]
        db.close()
        return res


    def get_bookmarks_by_title_and_url_regex_and_added(self, tregex, uregex, beg, end):
        res = []
        db = self.make_connection()
        cursor = db.cursor()
        for row in cursor.execute(self.queryByTitleAndUrlRegexAndAdded, ({"tregex": tregex, "uregex": uregex, "beg": beg, "end": end})):
            res += [{"id": row[0], "title": row[1], "url": row[2], "added": self.make_date(row[3]), "modified": self.make_date(row[4])}]
        db.close()
        return res


    def get_bookmarks_by_title_regex_and_tag_and_added(self, regex, tagid, beg, end):
        res = []
        db = self.make_connection()
        cursor = db.cursor()
        for row in cursor.execute(self.queryByTitleRegexAndTagAndAdded, ({"regex": regex, "beg": beg, "end": end, "tagid": tagid})):
            res += [{"id": row[0], "title": row[1], "url": row[2], "added": self.make_date(row[3]), "modified": self.make_date(row[4])}]
        db = close()
        return res


    def get_bookmarks_by_url_regex_and_tag_and_added(self, regex, tagid, beg, end):
        res = []
        db = self.make_connection()
        cursor = db.cursor()
        for row in cursor.execute(self.queryByUrlRegexAndAdded, ({"regex": regex, "beg": beg, "end": end, "tagid": tagid})):
            res += [{"id": row[0], "title": row[1], "url": row[2], "added": self.make_date(row[3]), "modified": self.make_date(row[4])}]
        db.close()
        return res


    def get_bookmarks_by_title_and_url_regex_and_tag_and_added(self, tregex, uregex, tagid, beg, end):
        res = []
        db = self.make_connection()
        cursor = db.cursor()
        for row in cursor.execute(self.queryByTitleAndUrlRegexAndAdded, ({"tregex": tregex, "uregex": uregex, "beg": beg, "end": end, "tagid": tagid})):
            res += [{"id": row[0], "title": row[1], "url": row[2], "added": self.make_date(row[3]), "modified": self.make_date(row[4])}]
        db.close()
        return res


    def get_dates(self):
        db = self.make_connection()
        cursor = db.cursor()
        cursor.execute("SELECT MIN(dateAdded), MAX(dateAdded) FROM moz_bookmarks")
        res = cursor.fetchone()
        db.close()
        return [time.strftime("%Y-%m-%dT%H:%M:%S", self.make_date(int(res[0]) - 1000000)), time.strftime("%Y-%m-%dT%H:%M:%S", self.make_date(int(res[1]) + 1000000))]


    def get_datestamps(self):
        db = self.make_connection()
        cursor = db.cursor()
        cursor.execute("SELECT MIN(dateAdded), MAX(dateAdded) FROM moz_bookmarks")
        res = cursor.fetchone()
        db.close()
        return res


    def parse_date(self, stamp):
        dt = datetime.fromisoformat(stamp)
        dt = dt.astimezone(tz=None)
        return int(dt.timestamp()) * 1000000

    
    def search(self, title=None, url=None, start=None, end=None, tag=None):
        res = []
        val = []
        datestamps = self.get_datestamps()
        if not start:
            start = datestamps[0]
        else:
            start = self.parse_date(start)
        if not end:
            end = datestamps[1]
        else:
            end = self.parse_date(end)
        if not tag:
            if title and url:
                val = self.get_bookmarks_by_title_and_url_regex_and_added( title, url, start, end)
            elif title and not url:
                val = self.get_bookmarks_by_title_regex_and_added( title, start, end)
            elif not title and url:
                val = self.get_bookmarks_by_url_regex_and_added(url, start, end)
            else:
                val = self.get_bookmarks_by_added(start, end)
        else:
            tagid = self.get_tagid(tag)
            if title and url:
                val = self.get_bookmarks_by_title_and_url_regex_and_tag_and_added(title, url, tagid, start, end)
            elif title and not url:
                val = self.get_bookmarks_by_title_regex_and_tag_and_added(title, tagid, start, end)
            elif not title and url:
                val = self.get_bookmarks_by_url_regex_and_tag_and_added(url, tagid, start, end)
            else:
                val = self.get_bookmarks_by_tag_and_added(start, end, tagid)
        for row in val:
            elt = {}
            elt['tags'] = self.find_tags(row['id'])
            elt['title'] = row['title']
            elt['url'] = row['url']
            elt['added'] = row['added']
            elt['modified'] = row['modified']
            res.append(elt)
        return res


class Simple(BookmarksSearch):
    def __init__(self, dbfile):
        self.dbfile = dbfile


    def get_datestamps(self):
        db = self.make_connection()
        cursor = db.cursor()
        cursor.execute("SELECT MIN(time_added), MAX(time_added) FROM pocket")
        res = cursor.fetchone()
        db.close()
        return res


    def parse_date(self, stamp):
        dt = datetime.fromisoformat(stamp)
        dt = dt.astimezone(tz=None)
        return int(dt.timestamp())


    def todatetime(self, stamp):
        return time.localtime(int(stamp))


    def execute_query(self, query, args):
        db = self.make_connection()
        cursor = db.cursor()
        cursor.execute(query, args)
        res = []
        for row in cursor.fetchall():
            res.append(row)
        db.close()
        return res


    def search(self, title=None, url=None, start=None, end=None):
        res = []
        val = []
        datestamps = self.get_datestamps()
        if not start:
            start = datestamps[0]
        else:
            start = self.parse_date(start)
        if not end:
            end = datestamps[1]
        else:
            end = self.parse_date(end)
        if title and url:
            val = self.execute_query("SELECT title,url,time_added FROM pocket WHERE time_added BETWEEN :beg AND :end AND url REGEXP :ure AND title REGEXP :tre ORDER BY time_added ASC", ({"beg": start, "end": end, "ure": url, "tre": title}))
        elif title and not url:
            val = self.execute_query("SELECT title,url,time_added FROM pocket WHERE time_added BETWEEN :beg AND :end AND title REGEXP :tre ORDER BY time_added ASC", ({"beg": start, "end": end, "tre": title}))
        elif not title and url:
            val = self.execute_query("SELECT title,url,time_added FROM pocket WHERE time_added BETWEEN :beg AND :end AND url REGEXP :ure ORDER BY time_added ASC", ({"beg": start, "end": end, "ure": url}))
        else:
            val = self.execute_query("SELECT title,url,time_added FROM pocket WHERE time_added BETWEEN :beg AND :end ORDER BY time_added ASC", ({"beg": start, "end": end}))
        for row in val:
            elt = {}
            elt['title'] = row[0]
            elt['url'] = row[1]
            elt['added'] = self.todatetime(row[2])
            res.append(elt)
        return res


sources = []


def make_response(path):
    if "/tags" == path:
        tags = []
        for source in sources:
            tags += source.get_all_tags()
        tags.sort()
        res = "<ul>\n"
        for tag in tags:
            res += "<li><a href=\"/search?tag={}\">{}</a></li>\n".format(tag, tag)
        res += "</ul>\n"
        return base.format(res=res, mindef="", maxdef="", treg="", ureg="", tag="")
    if "search" in path:
        title_re = None
        url_re = None
        ttag = None
        tmin = None
        tmax = None
        parsed = urlparse(path)
        pquery = parse_qs(parsed.query)
        if 'min' in pquery and len(pquery['min'][0]) > 0:
            tmin = pquery['min'][0]
        if 'max' in pquery and len(pquery['max'][0]) > 0:
            tmax = pquery['max'][0]
        if 'title' in pquery and len(pquery['title'][0]) > 0:
            title_re = pquery['title'][0]
        if 'url' in pquery and len(pquery['url'][0]) > 0:
            url_re = pquery['url'][0]
        if 'tag' in pquery and len(pquery['tag'][0]) > 0:
            ttag = pquery['tag'][0]
        vals = []
        if ttag:
            for source in sources:
                if isinstance(source, Firefox):
                    vals += source.search(title=title_re, url=url_re, start=tmin, end=tmax, tag=ttag)
        else:
            for source in sources:
                vals += source.search(title=title_re, url=url_re, start=tmin, end=tmax)
        vals.sort(key=lambda elt: time.mktime(elt['added']))
        res = "<ol>\n"
        for row in vals:
            added = time.strftime("%A, %B %d, %Y %T %z", row['added'])
            resline = ""
            if 'modified' in row:
                modified = time.strftime("%A, %B %d, %Y %T %z", row['modified'])
                resline = "{} ({}) &mdash; <a href=\"{}\">{}</a>".format(added, modified, row['url'].replace('"', '%22'), html.escape(row['title']))
            else:
                resline = "{} &mdash; <a href=\"{}\">{}</a>".format(added, row['url'].replace('"', '%22'), html.escape(row['title']))
            if ('tags' in row) and (len(row['tags']) > 0):
                resline += " ("
                if len(row['tags']) > 1:
                    for tag in row['tags'][:-1]:
                        resline += "<a href=\"/search?tag={}\">{}</a>, ".format(tag.replace(" ", "+"), html.escape(tag))
                resline += "<a href=\"/search?tag={}\">{}</a>)".format(row['tags'][-1].replace(" ", "+"), html.escape(row['tags'][-1]))
            res += "<li>{}</li>\n".format(resline)
        res += "</ol>\n"
        if not title_re:
            title_re = ""
        if not url_re:
            url_re = ""
        if not ttag:
            ttag = ""
        if not tmin:
            tmin = ""
        if not tmax:
            tmax = ""
        return base.format(res=res, mindef=tmin, maxdef=tmax, treg=html.escape(title_re), ureg=html.escape(url_re), tag=html.escape(ttag))
    else:
        return base.format(res="", mindef="", maxdef="", treg="", ureg="", tag="")


class HTTPHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(make_response(self.path).encode())


class HTTPServer(BaseHTTPServer):
    def __init__(self, server_address, RequestHandlerClass=HTTPHandler):
        BaseHTTPServer.__init__(self, server_address, RequestHandlerClass)


parser = argparse.ArgumentParser(description='Bookmarks Server')

parser.add_argument('-f', '--firefox-bookmarks', metavar='FIREFOX', type=str, nargs='*', help='Firefox places.sqlite file or files to serve.')
parser.add_argument('-s', '--simple-bookmarks', metavar='SIMPLE', type=str, nargs='*', help='Simple (Pocket) bookmarks file or files to serve.')
parser.add_argument('-p', '--port', metavar='PORT', type=int, nargs=1, required=True, help='Port to serve responses on.')

args = parser.parse_args()


for ff in args.firefox_bookmarks:
    sources.append(Firefox(ff))


for sim in args.simple_bookmarks:
    sources.append(Simple(sim))


httpd = HTTPServer(("", args.port[0]), RequestHandlerClass=HTTPHandler)
httpd.serve_forever()

