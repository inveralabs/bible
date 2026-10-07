#!/usr/bin/env python3
"""abide - read the Bible today, and still know it in a year.

    python3 abide.py serve                 # the app at http://127.0.0.1:7847
    python3 abide.py today                 # today's reading, in the terminal
    python3 abide.py read John.15          # any passage, in the terminal
    python3 abide.py review                # the verses that are due, in the terminal
    python3 abide.py log                   # what you read, and when
    python3 abide.py stats                 # the week, the streak, the coverage
    python3 abide.py key <YOUR-NLT-KEY>    # your own key from api.nlt.to
    python3 abide.py export > backup.json  # everything, as JSON

Four things, because reading without the other three does not stick:

  read       today's passage in the NLT, from Tyndale's own API, cached here forever
             after the first fetch. One chapter is one request, once, for good.
  recall     before you read, one question about the last thing you read. Thirty
             seconds. Retrieval beats rereading by a wide margin and this is the
             cheapest retrieval there is.
  keep       verses and your own notes on a spaced schedule (FSRS-6), so the thing
             you saw in Romans 8 in March comes back in June instead of dying in a
             notes list you never open.
  know       every reading logged with its date, its clock time and how long you
             stayed. A map of all 1,189 chapters, coloured by how often you have
             been there.

What the research changed about the design:

  Four days a week is the line, not seven. The Center for Bible Engagement's survey
  of 40,000 people found one, two or three days a week look like none at all, and
  four days a week look like a different life. So the headline number here is
  "days this week, out of seven, target four" - not an unbroken chain.

  One missed day costs nothing. Lally's habit study put the median at 66 days to
  automatic, and a single missed opportunity barely moved the curve; missing twice
  in a row is what stalls it. So abide is quiet after one miss and speaks up on the
  second, with a five-minute reading instead of a lecture.

  Nine percent of people who start a one-year plan finish it, and feeling behind is
  why most of the rest stop reading at all. So no plan here can put you behind.
  A plan is an ordered list, you are at a place in it, and the finish date moves.
  There is no debt, no red, and no "you missed 12 days".

  A streak can be gamed by tapping. So a reading counts when there is evidence of
  one - time on the passage, a note, a verse kept, a recall answered - and a
  tap-through is logged honestly as light.

Stdlib only. One SQLite file next to this script. Binds to 127.0.0.1 - there is no
account and no sync. The only thing that leaves the machine is a request to
api.nlt.to for text you have not read yet.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ABIDE_DB", HERE / "abide.db"))
DEFAULT_PORT = int(os.environ.get("ABIDE_PORT", 7847))
CA_CACHE = HERE / "data" / "ca-roots.pem"

SCHEMA_VERSION = 4
# app.html is read from disk on every request, so the browser picks up a change to the
# interface as soon as you reload. abide.py is not: it is the running process. That gap
# is how a new front end ends up asking an old server for something it does not serve,
# and getting a confidently wrong answer. So the server records when it started, and
# says so, and the page puts a banner up when the file on disk is newer than that.
STARTED_AT = time.time()
UA = "abide/1.0 (personal Bible reading log; stdlib python)"

API_BASE = "https://api.nlt.to/api"
# Tyndale's own documented limits. Anonymous: 50 verses a request, 500 requests a day.
# With a free key: 500 verses a request, 5,000 a day. abide fetches one chapter at a
# time and never fetches the same chapter twice, so a whole Bible costs 1,189 requests
# across a lifetime of reading.
ANON_VERSE_CAP = 50
KEYED_VERSE_CAP = 500
VERSIONS = ("NLT", "NLTUK", "NTV", "KJV")

TARGET_DAYS_PER_WEEK = 4        # the Center for Bible Engagement threshold
WORDS_PER_MINUTE = 200          # silent reading of prose, for the time estimates
ENGAGED_MIN_SECONDS = 60        # under a minute on a chapter is a tap, not a reading
ENGAGED_FRACTION = 0.35         # ...or this much of the chapter's estimated minutes
RESCUE_MINUTES = 5              # what the app offers after a second missed day
RECALL_LOOKBACK = 21            # how far back the recall question will reach, in days
PREFETCH_AHEAD = 3              # readings to pull into the cache after you finish one
NOTE_CAP = 40_000
CHECK_SAME_THREAD = False


# ============================================================== the sixty-six books
# abbr, api ref, title, testament, genre, chapters. The api ref column is what
# api.nlt.to accepts: numbered books have no space ("1Sam"), and a few are shorter
# than you would guess ("Song", "1Thes", "Phlm", "Jas"). Every one of these was
# checked against the API rather than assumed.
BOOKS: list[tuple[str, str, str, str, str, int]] = [
    ("Gen", "Gen", "Genesis", "OT", "law", 50),
    ("Exod", "Exod", "Exodus", "OT", "law", 40),
    ("Lev", "Lev", "Leviticus", "OT", "law", 27),
    ("Num", "Num", "Numbers", "OT", "law", 36),
    ("Deut", "Deut", "Deuteronomy", "OT", "law", 34),
    ("Josh", "Josh", "Joshua", "OT", "history", 24),
    ("Judg", "Judg", "Judges", "OT", "history", 21),
    ("Ruth", "Ruth", "Ruth", "OT", "history", 4),
    ("1Sam", "1Sam", "1 Samuel", "OT", "history", 31),
    ("2Sam", "2Sam", "2 Samuel", "OT", "history", 24),
    ("1Kgs", "1Kgs", "1 Kings", "OT", "history", 22),
    ("2Kgs", "2Kgs", "2 Kings", "OT", "history", 25),
    ("1Chr", "1Chr", "1 Chronicles", "OT", "history", 29),
    ("2Chr", "2Chr", "2 Chronicles", "OT", "history", 36),
    ("Ezra", "Ezra", "Ezra", "OT", "history", 10),
    ("Neh", "Neh", "Nehemiah", "OT", "history", 13),
    ("Esth", "Esth", "Esther", "OT", "history", 10),
    ("Job", "Job", "Job", "OT", "wisdom", 42),
    ("Ps", "Ps", "Psalms", "OT", "wisdom", 150),
    ("Prov", "Prov", "Proverbs", "OT", "wisdom", 31),
    ("Eccl", "Eccl", "Ecclesiastes", "OT", "wisdom", 12),
    ("Song", "Song", "Song of Songs", "OT", "wisdom", 8),
    ("Isa", "Isa", "Isaiah", "OT", "prophets", 66),
    ("Jer", "Jer", "Jeremiah", "OT", "prophets", 52),
    ("Lam", "Lam", "Lamentations", "OT", "prophets", 5),
    ("Ezek", "Ezek", "Ezekiel", "OT", "prophets", 48),
    ("Dan", "Dan", "Daniel", "OT", "prophets", 12),
    ("Hos", "Hos", "Hosea", "OT", "minor", 14),
    ("Joel", "Joel", "Joel", "OT", "minor", 3),
    ("Amos", "Amos", "Amos", "OT", "minor", 9),
    ("Obad", "Obad", "Obadiah", "OT", "minor", 1),
    ("Jonah", "Jonah", "Jonah", "OT", "minor", 4),
    ("Mic", "Mic", "Micah", "OT", "minor", 7),
    ("Nah", "Nah", "Nahum", "OT", "minor", 3),
    ("Hab", "Hab", "Habakkuk", "OT", "minor", 3),
    ("Zeph", "Zeph", "Zephaniah", "OT", "minor", 3),
    ("Hag", "Hag", "Haggai", "OT", "minor", 2),
    ("Zech", "Zech", "Zechariah", "OT", "minor", 14),
    ("Mal", "Mal", "Malachi", "OT", "minor", 4),
    ("Matt", "Matt", "Matthew", "NT", "gospel", 28),
    ("Mark", "Mark", "Mark", "NT", "gospel", 16),
    ("Luke", "Luke", "Luke", "NT", "gospel", 24),
    ("John", "John", "John", "NT", "gospel", 21),
    ("Acts", "Acts", "Acts", "NT", "acts", 28),
    ("Rom", "Rom", "Romans", "NT", "paul", 16),
    ("1Cor", "1Cor", "1 Corinthians", "NT", "paul", 16),
    ("2Cor", "2Cor", "2 Corinthians", "NT", "paul", 13),
    ("Gal", "Gal", "Galatians", "NT", "paul", 6),
    ("Eph", "Eph", "Ephesians", "NT", "paul", 6),
    ("Phil", "Phil", "Philippians", "NT", "paul", 4),
    ("Col", "Col", "Colossians", "NT", "paul", 4),
    ("1Thes", "1Thes", "1 Thessalonians", "NT", "paul", 5),
    ("2Thes", "2Thes", "2 Thessalonians", "NT", "paul", 3),
    ("1Tim", "1Tim", "1 Timothy", "NT", "paul", 6),
    ("2Tim", "2Tim", "2 Timothy", "NT", "paul", 4),
    ("Titus", "Titus", "Titus", "NT", "paul", 3),
    ("Phlm", "Phlm", "Philemon", "NT", "paul", 1),
    ("Heb", "Heb", "Hebrews", "NT", "general", 13),
    ("Jas", "Jas", "James", "NT", "general", 5),
    ("1Pet", "1Pet", "1 Peter", "NT", "general", 5),
    ("2Pet", "2Pet", "2 Peter", "NT", "general", 3),
    ("1Jn", "1Jn", "1 John", "NT", "general", 5),
    ("2Jn", "2Jn", "2 John", "NT", "general", 1),
    ("3Jn", "3Jn", "3 John", "NT", "general", 1),
    ("Jude", "Jude", "Jude", "NT", "general", 1),
    ("Rev", "Rev", "Revelation", "NT", "apocalypse", 22),
]
BOOK_BY_ABBR = {b[0]: i + 1 for i, b in enumerate(BOOKS)}          # abbr -> 1..66
GENRE_TITLES = {
    "law": "Law", "history": "History", "wisdom": "Wisdom & poetry",
    "prophets": "Major prophets", "minor": "Minor prophets", "gospel": "Gospels",
    "acts": "Acts", "paul": "Paul's letters", "general": "General letters",
    "apocalypse": "Revelation",
}

# Every alternative spelling worth accepting when you type a reference. Built from the
# titles plus the spellings people actually use, so "1 sam", "song of solomon",
# "revelations" and "psalm" all land in the right book.
_ALIASES: dict[str, str] = {
    "genesis": "Gen", "gn": "Gen", "ge": "Gen",
    "exodus": "Exod", "ex": "Exod", "exo": "Exod",
    "leviticus": "Lev", "lv": "Lev",
    "numbers": "Num", "nm": "Num", "nb": "Num",
    "deuteronomy": "Deut", "dt": "Deut", "deu": "Deut",
    "joshua": "Josh", "jos": "Josh", "jsh": "Josh",
    "judges": "Judg", "jdg": "Judg", "jg": "Judg",
    "ruth": "Ruth", "rth": "Ruth", "ru": "Ruth",
    "1samuel": "1Sam", "1sa": "1Sam", "1s": "1Sam", "isamuel": "1Sam", "1sm": "1Sam",
    "2samuel": "2Sam", "2sa": "2Sam", "2s": "2Sam", "iisamuel": "2Sam", "2sm": "2Sam",
    "1kings": "1Kgs", "1kg": "1Kgs", "1ki": "1Kgs", "1k": "1Kgs",
    "2kings": "2Kgs", "2kg": "2Kgs", "2ki": "2Kgs", "2k": "2Kgs",
    "1chronicles": "1Chr", "1ch": "1Chr", "1chron": "1Chr",
    "2chronicles": "2Chr", "2ch": "2Chr", "2chron": "2Chr",
    "ezra": "Ezra", "ezr": "Ezra",
    "nehemiah": "Neh", "ne": "Neh",
    "esther": "Esth", "est": "Esth", "es": "Esth",
    "job": "Job", "jb": "Job",
    "psalms": "Ps", "psalm": "Ps", "psa": "Ps", "pss": "Ps", "psm": "Ps", "pslm": "Ps",
    "proverbs": "Prov", "proverb": "Prov", "pro": "Prov", "prv": "Prov", "pr": "Prov",
    "ecclesiastes": "Eccl", "ecc": "Eccl", "ec": "Eccl", "qoheleth": "Eccl",
    "songofsongs": "Song", "songofsolomon": "Song", "canticles": "Song", "sos": "Song",
    "sng": "Song", "ss": "Song", "cant": "Song",
    "isaiah": "Isa", "is": "Isa", "isa": "Isa",
    "jeremiah": "Jer", "jr": "Jer", "je": "Jer",
    "lamentations": "Lam", "la": "Lam",
    "ezekiel": "Ezek", "eze": "Ezek", "ezk": "Ezek",
    "daniel": "Dan", "dn": "Dan", "da": "Dan",
    "hosea": "Hos", "ho": "Hos",
    "joel": "Joel", "jl": "Joel", "joe": "Joel",
    "amos": "Amos", "am": "Amos",
    "obadiah": "Obad", "ob": "Obad", "oba": "Obad",
    "jonah": "Jonah", "jon": "Jonah", "jnh": "Jonah",
    "micah": "Mic", "mi": "Mic", "mc": "Mic",
    "nahum": "Nah", "na": "Nah",
    "habakkuk": "Hab", "hb": "Hab",
    "zephaniah": "Zeph", "zep": "Zeph", "zp": "Zeph",
    "haggai": "Hag", "hg": "Hag",
    "zechariah": "Zech", "zec": "Zech", "zc": "Zech",
    "malachi": "Mal", "ml": "Mal",
    "matthew": "Matt", "mt": "Matt", "mat": "Matt",
    "mark": "Mark", "mk": "Mark", "mrk": "Mark", "mr": "Mark",
    "luke": "Luke", "lk": "Luke", "luk": "Luke",
    "john": "John", "jn": "John", "jhn": "John", "joh": "John",
    "acts": "Acts", "ac": "Acts", "act": "Acts",
    "romans": "Rom", "ro": "Rom", "rm": "Rom",
    "1corinthians": "1Cor", "1co": "1Cor", "1c": "1Cor",
    "2corinthians": "2Cor", "2co": "2Cor", "2c": "2Cor",
    "galatians": "Gal", "ga": "Gal",
    "ephesians": "Eph", "ep": "Eph", "eic": "Eph",
    "philippians": "Phil", "php": "Phil", "philip": "Phil", "pp": "Phil",
    "colossians": "Col", "co": "Col",
    "1thessalonians": "1Thes", "1th": "1Thes", "1thess": "1Thes",
    "2thessalonians": "2Thes", "2th": "2Thes", "2thess": "2Thes",
    "1timothy": "1Tim", "1ti": "1Tim", "1tm": "1Tim",
    "2timothy": "2Tim", "2ti": "2Tim", "2tm": "2Tim",
    "titus": "Titus", "ti": "Titus", "tit": "Titus",
    "philemon": "Phlm", "phm": "Phlm", "philem": "Phlm",
    "hebrews": "Heb", "hbr": "Heb", "he": "Heb",
    "james": "Jas", "jm": "Jas", "jam": "Jas", "ja": "Jas",
    "1peter": "1Pet", "1pe": "1Pet", "1pt": "1Pet", "1p": "1Pet",
    "2peter": "2Pet", "2pe": "2Pet", "2pt": "2Pet", "2p": "2Pet",
    "1john": "1Jn", "1jo": "1Jn", "1jhn": "1Jn", "1j": "1Jn",
    "2john": "2Jn", "2jo": "2Jn", "2jhn": "2Jn", "2j": "2Jn",
    "3john": "3Jn", "3jo": "3Jn", "3jhn": "3Jn", "3j": "3Jn",
    "jude": "Jude", "jud": "Jude", "jde": "Jude",
    "revelation": "Rev", "revelations": "Rev", "rv": "Rev", "re": "Rev", "apocalypse": "Rev",
}
for _b in BOOKS:                                   # the abbr and the full title, always
    _ALIASES.setdefault(_b[0].lower(), _b[0])
    _ALIASES.setdefault(_b[2].lower().replace(" ", ""), _b[0])


# The verse count and the word count of every one of the 1,189 chapters, read off the
# NLT itself once and kept here so the app never has to ask. Verse counts drive the
# request splitting (a chapter over the anonymous 50-verse cap has to be fetched in
# pieces) and word counts drive every "about 4 minutes" you see, at 200 words a minute.
# Not the text - only its shape. Footnotes were stripped before counting.
_VERSES_RAW = "Gen:31,25,24,26,32,22,24,22,29,32,32,20,18,24,21,16,27,33,38,18,34,24,20,67,34,35,46,22,35,43,55,32,20,31,29,43,36,30,23,23,57,38,34,34,28,34,31,22,33,26|Exod:22,25,22,31,23,30,25,32,35,29,10,51,22,31,27,36,16,27,25,26,36,31,33,18,40,37,21,43,46,38,18,35,23,35,35,38,29,31,43,38|Lev:17,16,17,35,19,30,38,36,24,20,47,8,59,57,33,34,16,30,37,27,24,33,44,23,55,46,34|Num:54,34,51,49,31,27,89,26,23,36,35,16,33,45,41,50,13,32,22,29,35,41,30,25,18,65,23,31,40,16,54,42,56,29,34,13|Deut:46,37,29,49,33,25,26,20,29,22,32,32,18,29,23,22,20,22,21,20,23,30,25,22,19,19,26,68,29,20,30,52,29,12|Josh:18,24,17,24,15,27,26,35,27,43,23,24,33,15,63,10,18,28,51,9,45,34,16,33|Judg:36,23,31,24,31,40,25,35,57,18,40,15,25,20,20,31,13,31,30,48,25|Ruth:22,23,18,22|1Sam:28,36,21,22,12,21,17,22,27,27,15,25,23,52,35,23,58,30,24,42,15,23,29,22,44,25,12,25,11,31,13|2Sam:27,32,39,12,25,23,29,18,13,19,27,31,39,33,37,23,29,33,43,26,22,51,39,25|1Kgs:53,46,28,34,18,38,51,66,28,29,43,33,34,31,34,34,24,46,21,43,29,53|2Kgs:18,25,27,44,27,33,20,29,37,36,21,21,25,29,38,20,41,37,37,21,26,20,37,20,30|1Chr:54,55,24,43,26,81,40,40,44,14,47,40,14,17,29,43,27,17,19,8,30,19,32,31,31,32,34,21,30|2Chr:17,18,17,22,14,42,22,18,31,19,23,16,22,15,19,14,19,34,11,37,20,12,21,27,28,23,9,27,36,27,21,33,25,33,27,23|Ezra:11,70,13,24,17,22,28,36,15,44|Neh:11,20,32,23,19,19,73,18,38,39,36,47,31|Esth:22,23,15,17,14,14,10,17,32,3|Job:22,13,26,21,27,30,21,22,35,22,20,25,28,22,35,22,16,21,29,29,34,30,17,25,6,14,23,28,25,31,40,22,33,37,16,33,24,41,30,24,34,17|Ps:6,12,8,8,12,10,17,9,20,18,7,8,6,7,5,11,15,50,14,9,13,31,6,10,22,12,14,9,11,12,24,11,22,22,28,12,40,22,13,17,13,11,5,26,17,11,9,14,20,23,19,9,6,7,23,13,11,11,17,12,8,12,11,10,13,20,7,35,36,5,24,20,28,23,10,12,20,72,13,19,16,8,18,12,13,17,7,18,52,17,16,15,5,23,11,13,12,9,9,5,8,28,22,35,45,48,43,13,31,7,10,10,9,8,18,19,2,29,176,7,8,9,4,8,5,6,5,6,8,8,3,18,3,3,21,26,9,8,24,13,10,7,12,15,21,10,20,14,9,6|Prov:33,22,35,27,23,35,27,36,18,32,31,28,25,35,33,33,28,24,29,30,31,29,35,34,28,28,27,28,27,33,31|Eccl:18,26,22,16,20,12,29,17,18,20,10,14|Song:17,17,11,16,16,13,13,14|Isa:31,22,26,6,30,13,25,22,21,34,16,6,22,32,9,14,14,7,25,6,17,25,18,23,12,21,13,29,24,33,9,20,24,17,10,22,38,22,8,31,29,25,28,28,25,13,15,22,26,11,23,15,12,17,13,12,21,14,21,22,11,12,19,12,25,24|Jer:19,37,25,31,31,30,34,22,26,25,23,17,27,22,21,21,27,23,15,18,14,30,40,10,38,24,22,17,32,24,40,44,26,22,19,32,21,28,18,16,18,22,13,30,5,28,7,47,39,46,64,34|Lam:22,22,66,22,22|Ezek:28,10,27,17,17,14,27,18,11,22,25,28,23,23,8,63,24,32,14,49,32,31,49,27,17,21,36,26,21,26,18,32,33,31,15,38,28,23,29,49,26,20,27,31,25,24,23,35|Dan:21,49,30,37,31,28,28,27,27,21,45,13|Hos:11,23,5,19,15,11,16,14,17,15,12,14,16,9|Joel:20,32,21|Amos:15,16,15,13,27,14,17,14,15|Obad:21|Jonah:17,10,10,11|Mic:16,13,12,13,15,16,20|Nah:15,13,19|Hab:17,20,19|Zeph:18,15,20|Hag:15,23|Zech:21,13,10,14,11,15,14,23,17,12,17,14,9,21|Mal:14,17,18,6|Matt:25,23,17,25,48,34,29,34,38,42,30,50,58,36,39,28,27,35,30,34,46,46,39,51,46,75,66,20|Mark:45,28,35,41,43,56,37,38,50,52,33,44,37,72,47,20|Luke:80,52,38,44,39,49,50,56,62,42,54,59,35,35,32,31,37,43,48,47,38,71,56,53|John:51,25,36,54,47,71,53,59,41,42,57,50,38,31,27,33,26,40,42,31,25|Acts:26,47,26,37,42,15,60,40,43,48,30,25,52,28,41,40,34,28,41,38,40,30,35,27,27,32,44,31|Rom:32,29,31,25,21,23,25,39,33,21,36,21,14,23,33,27|1Cor:31,16,23,21,13,20,40,13,27,33,34,31,13,40,58,24|2Cor:24,17,18,18,21,18,16,24,15,18,33,21,14|Gal:24,21,29,31,26,18|Eph:23,22,21,32,33,24|Phil:30,30,21,23|Col:29,23,25,18|1Thes:10,20,13,18,28|2Thes:12,17,18|1Tim:20,15,16,16,25,21|2Tim:18,26,17,22|Titus:16,15,15|Phlm:25|Heb:14,18,19,16,14,20,28,13,28,39,40,29,25|Jas:27,26,18,17,20|1Pet:25,25,22,19,14|2Pet:21,22,18|1Jn:10,29,24,21,21|2Jn:13|3Jn:15|Jude:25|Rev:20,29,22,11,14,17,17,13,21,11,19,18,18,20,8,21,18,24,21,15,27,21"
_WORDS_RAW = "Gen:712,566,654,608,445,505,486,466,568,467,606,482,432,599,455,403,626,823,1028,481,688,577,415,1707,657,865,1100,592,821,986,1491,789,475,741,626,811,934,853,538,477,1348,1010,862,856,707,703,851,668,721,676|Exod:435,657,699,864,580,704,630,916,859,815,317,1427,659,859,663,1039,468,710,676,586,930,823,867,483,703,731,488,1030,1190,814,427,1000,654,1059,742,790,554,782,946,739|Lev:476,449,438,1027,684,828,972,983,641,667,1018,268,1651,1528,843,1111,491,666,856,801,557,889,1273,552,1514,1212,920|Num:549,490,1070,1145,835,741,1915,630,644,769,975,344,627,1185,949,1304,278,1068,686,750,880,1076,717,593,409,1356,528,768,1029,391,974,966,833,406,808,338|Deut:1219,967,820,1366,847,606,803,539,917,638,860,965,503,663,626,696,598,556,599,541,668,787,583,594,469,602,552,1767,803,638,947,1278,800,293|Josh:515,678,488,610,438,771,888,982,701,1155,626,473,844,445,895,232,651,703,769,321,777,1133,469,943|Judg:887,601,766,636,718,1199,824,833,1425,402,1057,381,684,677,605,1040,337,856,886,1165,674|Ruth:585,710,500,624|1Sam:677,1025,461,651,390,661,500,434,784,855,432,698,674,1403,888,645,1415,712,658,1115,391,651,716,612,1173,709,303,687,336,747,337|2Sam:628,793,1016,395,609,625,813,386,350,542,685,861,998,920,954,627,897,969,1251,762,676,842,819,761|1Kgs:1374,1311,798,656,470,841,1265,1885,733,766,1151,922,987,873,878,958,592,1351,707,1253,707,1404|2Kgs:615,774,810,1281,933,944,765,869,1126,1106,711,574,684,813,966,598,1184,1160,1152,618,697,626,1391,464,870|1Chr:660,856,322,791,585,971,723,455,902,338,928,924,376,337,651,792,755,365,542,269,862,585,670,599,561,747,741,741,894|2Chr:478,566,481,522,432,1228,685,472,829,497,441,453,588,461,499,460,397,979,354,1082,565,411,740,861,860,672,219,829,1099,843,696,992,737,1097,872,721|Ezra:317,660,490,679,489,734,801,907,611,860|Neh:345,642,921,639,599,529,851,640,1271,655,682,1078,980|Esth:639,745,547,473,443,440,325,594,866,96|Job:568,333,407,312,429,442,340,332,567,368,311,386,427,371,515,332,238,287,427,427,512,470,252,451,71,186,331,431,369,456,628,346,474,566,235,488,359,603,460,321,463,400|Ps:111,209,134,161,254,163,292,160,347,324,135,153,113,147,95,197,287,858,278,171,225,587,123,164,342,178,325,223,175,225,496,236,320,377,544,210,653,309,276,430,230,262,121,454,309,207,150,267,304,399,338,193,149,139,395,268,254,202,370,248,145,256,199,175,271,326,124,658,650,118,463,372,431,364,213,200,327,1176,278,346,299,123,266,277,203,305,125,322,818,287,270,240,102,326,197,222,182,176,162,82,157,436,344,580,654,759,618,220,491,152,162,158,117,122,258,279,30,448,2325,99,110,155,83,114,102,94,121,101,124,122,77,301,78,50,309,334,165,176,405,241,192,155,224,304,331,178,282,191,133,78|Prov:521,301,518,402,358,535,384,502,274,497,441,386,372,492,482,436,425,323,432,440,461,430,516,530,464,423,436,456,383,552,418|Eccl:321,616,447,347,482,310,502,416,468,358,228,378|Song:328,320,256,338,368,297,289,358|Isa:777,524,475,172,856,349,643,535,588,868,468,132,534,821,241,383,426,230,652,170,419,639,433,521,338,480,342,782,647,934,294,406,584,470,285,707,1151,534,240,741,762,640,721,817,788,326,422,613,825,336,700,391,376,451,374,365,531,469,580,626,337,355,541,297,773,808|Jer:487,1063,784,814,817,808,941,679,728,662,672,488,685,697,680,632,793,553,516,530,417,839,1198,284,1080,765,653,444,867,632,1180,1250,741,588,526,879,544,832,484,571,446,601,370,1008,139,745,205,1089,1120,1307,1675,907|Lam:736,788,856,557,306|Ezek:684,237,678,473,531,407,669,553,348,565,656,723,700,652,164,1486,690,794,358,1442,840,697,1206,732,476,612,717,722,619,692,599,936,927,879,366,1038,783,651,800,1438,688,543,819,931,805,832,693,818|Dan:570,1323,818,1186,899,818,875,783,882,599,1370,381|Hos:334,693,155,481,376,237,380,343,522,462,308,323,407,243|Joel:482,914,546|Amos:466,433,375,415,655,399,478,402,497|Obad:694|Jonah:464,220,241,311|Mic:447,402,327,456,388,450,593|Nah:387,312,500|Hab:401,538,443|Zeph:531,454,581|Hag:420,632|Zech:564,305,305,309,292,374,355,697,513,378,479,416,290,649|Mal:509,578,621,166|Matt:542,579,432,546,1070,743,613,759,833,898,710,1131,1332,688,774,685,590,825,667,738,1105,843,863,1036,1033,1606,1346,430|Mark:931,652,670,895,925,1254,773,885,1122,1198,736,1082,821,1612,921,499|Luke:1416,1045,1029,939,926,1166,1186,1453,1389,1020,1331,1321,828,776,730,809,728,898,1025,982,756,1414,1085,1024|John:994,490,754,1072,938,1385,1052,1276,833,833,1077,1060,784,748,570,738,617,897,951,680,624|Acts:632,999,594,826,1002,341,1403,829,1006,1012,662,618,1302,656,889,954,871,674,960,852,1008,714,791,597,639,755,1079,795|Rom:826,695,693,631,588,568,700,1061,837,518,998,478,391,610,876,576|1Cor:728,393,516,564,382,523,1078,342,746,709,769,731,289,981,1320,478|2Cor:688,420,479,481,557,429,500,620,418,464,791,626,387|Gal:517,701,838,791,589,426|Eph:567,587,461,662,586,534|Phil:747,662,558,533|Col:760,538,518,397|1Thes:302,568,324,430,462|2Thes:303,440,393|1Tim:529,284,387,360,621,554|2Tim:496,567,399,482|Titus:444,348,352|Phlm:522|Heb:348,499,413,426,345,518,720,407,848,917,1111,773,545|Jas:584,609,405,437,503|1Pet:727,616,592,498,374|2Pet:529,635,517|1Jn:277,791,604,569,482|2Jn:321|3Jn:363|Jude:769|Rev:584,862,682,340,433,500,411,371,508,321,562,505,526,597,241,567,543,737,608,459,655,572"


def _unpack(raw: str) -> dict[str, tuple[int, ...]]:
    out: dict[str, tuple[int, ...]] = {}
    for part in raw.split("|"):
        abbr, nums = part.split(":", 1)
        out[abbr] = tuple(int(n) for n in nums.split(","))
    return out


VERSE_COUNTS = _unpack(_VERSES_RAW)
WORD_COUNTS = _unpack(_WORDS_RAW)
TOTAL_CHAPTERS = sum(b[5] for b in BOOKS)
TOTAL_VERSES = sum(sum(v) for v in VERSE_COUNTS.values())
TOTAL_WORDS = sum(sum(v) for v in WORD_COUNTS.values())


def verses_in(abbr: str, ch: int) -> int:
    row = VERSE_COUNTS.get(abbr)
    return row[ch - 1] if row and 1 <= ch <= len(row) else 0


def words_in(abbr: str, ch: int) -> int:
    row = WORD_COUNTS.get(abbr)
    return row[ch - 1] if row and 1 <= ch <= len(row) else 0


def chapters_in(abbr: str) -> int:
    for b in BOOKS:
        if b[0] == abbr:
            return b[5]
    return 0


def book_title(abbr: str) -> str:
    for b in BOOKS:
        if b[0] == abbr:
            return b[2]
    return abbr


def book_row(abbr: str) -> tuple[str, str, str, str, str, int] | None:
    for b in BOOKS:
        if b[0] == abbr:
            return b
    return None


# =================================================================== references
# A reference in abide is always (book, chapter, first verse, last verse), where the
# verses are None for a whole chapter. Its canonical written form is what api.nlt.to
# accepts - "Rom.8", "John.3.16-18" - so the same string is the cache key, the API
# parameter and what gets stored in a row.
_REF_RE = re.compile(
    r"""^\s*
    (?P<book>(?:[1-3]|i{1,3})?\s*[A-Za-z][A-Za-z\s]*?)   # "1 sam", "Song of Songs"
    \s*[\s.]?\s*
    (?P<ch>\d{1,3})
    (?:\s*[:.]\s*(?P<v1>\d{1,3})(?:\s*-\s*(?P<v2>\d{1,3}))?
       |\s*-\s*(?P<ch2>\d{1,3})(?![:.]\d))?
    \s*$""",
    re.X,
)


class Ref:
    """One chapter, or a verse range inside one chapter."""

    __slots__ = ("abbr", "ch", "v1", "v2")

    def __init__(self, abbr: str, ch: int, v1: int | None = None, v2: int | None = None):
        self.abbr, self.ch = abbr, ch
        self.v1, self.v2 = v1, (v2 if v2 else v1)

    # -- identity -------------------------------------------------------------
    def key(self) -> str:
        if self.v1 is None:
            return f"{self.abbr}.{self.ch}"
        if self.v2 == self.v1:
            return f"{self.abbr}.{self.ch}.{self.v1}"
        return f"{self.abbr}.{self.ch}.{self.v1}-{self.v2}"

    def chapter_key(self) -> str:
        return f"{self.abbr}.{self.ch}"

    def label(self) -> str:
        t = book_title(self.abbr)
        if self.abbr == "Ps":
            t = "Psalm"                      # the book is Psalms; one of them is a Psalm
        one = chapters_in(self.abbr) == 1
        if self.v1 is None:
            # Obadiah, Philemon, 2 John, 3 John and Jude have one chapter and no need
            # of a number after their name
            return t if one else f"{t} {self.ch}"
        # ...and their verses are cited without one either: Jude 3, not Jude 1:3
        head = t if one else f"{t} {self.ch}:"
        sep = " " if one else ""
        if self.v2 == self.v1:
            return f"{head}{sep}{self.v1}"
        return f"{head}{sep}{self.v1}-{self.v2}"

    def short(self) -> str:
        one = chapters_in(self.abbr) == 1
        if self.v1 is None:
            return self.abbr if one else f"{self.abbr} {self.ch}"
        head = f"{self.abbr} " if one else f"{self.abbr} {self.ch}:"
        return f"{head}{self.v1}" + (f"-{self.v2}" if self.v2 != self.v1 else "")

    # -- shape ----------------------------------------------------------------
    def verse_count(self) -> int:
        n = verses_in(self.abbr, self.ch)
        if self.v1 is None:
            return n
        return max(0, min(self.v2 or self.v1, n) - self.v1 + 1)

    def word_count(self) -> int:
        whole = words_in(self.abbr, self.ch)
        n = verses_in(self.abbr, self.ch)
        if self.v1 is None or not n:
            return whole
        return int(round(whole * self.verse_count() / n))

    def minutes(self) -> float:
        return self.word_count() / WORDS_PER_MINUTE

    def sort_key(self) -> tuple[int, int, int]:
        return (BOOK_BY_ABBR.get(self.abbr, 99), self.ch, self.v1 or 0)

    def __repr__(self) -> str:
        return f"Ref({self.key()})"

    def __eq__(self, other) -> bool:
        return isinstance(other, Ref) and self.key() == other.key()

    def __hash__(self) -> int:
        return hash(self.key())


def _book_from(text: str) -> str | None:
    t = re.sub(r"[^a-z0-9]", "", text.lower())
    t = re.sub(r"^iii", "3", t)
    t = re.sub(r"^ii", "2", t)
    t = re.sub(r"^i(?=[a-z])", "1", t)
    return _ALIASES.get(t)


def parse_ref(text: str) -> list[Ref]:
    """Read one written reference into a list of Refs. Chapter ranges expand.

    Accepts what a person types: "john 3:16-18", "Ps 23", "1 sam 17", "Gen 1-3",
    "Rom.8", "Jude", "Philemon". A bare book name means its whole first chapter is
    the start and every chapter comes back.
    """
    text = (text or "").strip().replace("–", "-").replace("—", "-")
    if not text:
        return []
    out: list[Ref] = []
    for piece in re.split(r"\s*;\s*", text):
        if not piece.strip():
            continue
        abbr = _book_from(piece)                       # a bare book name
        if abbr:
            out += [Ref(abbr, c) for c in range(1, chapters_in(abbr) + 1)]
            continue
        m = _REF_RE.match(piece)
        if not m:
            continue
        abbr = _book_from(m.group("book") or "")
        if not abbr:
            continue
        nch = chapters_in(abbr)
        ch = max(1, min(int(m.group("ch")), nch))
        v1raw, ch2raw = m.group("v1"), m.group("ch2")
        if nch == 1 and not v1raw and (ch2raw or int(m.group("ch")) > 1):
            # Obadiah, Philemon, 2-3 John and Jude have one chapter, so "Jude 3" and
            # "Philemon 6-7" mean verses. A bare "Jude 1" still means the whole thing.
            n = verses_in(abbr, 1) or 200
            a = max(1, min(int(m.group("ch")), n))
            b = max(a, min(int(ch2raw or a), n))
            out.append(Ref(abbr, 1, a, b))
        elif ch2raw:
            ch2 = max(ch, min(int(ch2raw), nch))
            out += [Ref(abbr, c) for c in range(ch, ch2 + 1)]
        elif v1raw:
            n = verses_in(abbr, ch) or 200
            a = max(1, min(int(v1raw), n))
            b = max(a, min(int(m.group("v2") or a), n))
            out.append(Ref(abbr, ch, a, b))
        else:
            out.append(Ref(abbr, ch))
    return out


def one_ref(text: str) -> Ref | None:
    got = parse_ref(text)
    return got[0] if got else None


def refs_label(refs: list[Ref]) -> str:
    """The shortest honest way to say a set of references.

    Runs that touch join up, so a chronological plan's twelve slices of Ezekiel and
    Jeremiah come back as "Ezekiel 24:15-25:17; Jeremiah 34:1-22" rather than as a
    list you would never read out loud.
    """
    if not refs:
        return ""

    def ends_at(r: Ref) -> tuple[int, int]:
        return (r.ch, r.v2 if r.v2 is not None else (verses_in(r.abbr, r.ch) or 999))

    def starts_at(r: Ref) -> tuple[int, int]:
        return (r.ch, r.v1 if r.v1 is not None else 1)

    def touches(a: Ref, b: Ref) -> bool:
        if a.abbr != b.abbr:
            return False
        (ac, av), (bc, bv) = ends_at(a), starts_at(b)
        if bc == ac and bv == av + 1:
            return True
        return bc == ac + 1 and bv == 1 and av >= (verses_in(a.abbr, ac) or 999)

    def say(run: list[Ref]) -> str:
        if len(run) == 1:
            return run[0].label()
        first, last = run[0], run[-1]
        whole = first.v1 is None and last.v2 is None
        t = "Psalm" if first.abbr == "Ps" else book_title(first.abbr)
        if whole:
            return (t if chapters_in(first.abbr) == 1
                    else f"{t} {first.ch}-{last.ch}")
        a = first.v1 if first.v1 is not None else 1
        b = last.v2 if last.v2 is not None else (verses_in(last.abbr, last.ch) or 1)
        if first.ch == last.ch:
            if chapters_in(first.abbr) == 1:
                return f"{t} {a}-{b}"
            return f"{t} {first.ch}:{a}-{b}"
        return f"{t} {first.ch}:{a}-{last.ch}:{b}"

    parts: list[str] = []
    run: list[Ref] = [refs[0]]
    for r in refs[1:]:
        if touches(run[-1], r):
            run.append(r)
        else:
            parts.append(say(run))
            run = [r]
    parts.append(say(run))
    return "; ".join(parts)


# ============================================================ talking to api.nlt.to
_SSL_CTX: ssl.SSLContext | None = None


def ssl_context() -> ssl.SSLContext:
    """A verifying context that works on a python.org build with no certs installed.

    Those builds ship without CA roots until you run Install Certificates.command, and
    every HTTPS call fails with CERTIFICATE_VERIFY_FAILED. Rather than ask for that,
    take the roots macOS already trusts. Verification stays on either way.
    """
    global _SSL_CTX
    if _SSL_CTX is not None:
        return _SSL_CTX
    ctx = ssl.create_default_context()
    try:
        import certifi                                   # if it happens to be around
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    if not ctx.get_ca_certs():
        pem = ""
        if CA_CACHE.exists() and CA_CACHE.stat().st_size > 1000:
            pem = CA_CACHE.read_text()
        elif sys.platform == "darwin":
            for store in ("/System/Library/Keychains/SystemRootCertificates.keychain",
                          "/Library/Keychains/System.keychain"):
                try:
                    out = subprocess.run(["security", "find-certificate", "-a", "-p", store],
                                         capture_output=True, text=True, timeout=30)
                    pem += out.stdout
                except Exception:
                    pass
            if pem.count("BEGIN CERTIFICATE") > 20:
                CA_CACHE.parent.mkdir(parents=True, exist_ok=True)
                CA_CACHE.write_text(pem)
        if pem:
            try:
                ctx.load_verify_locations(cadata=pem)
            except Exception:
                pass
    _SSL_CTX = ctx
    return ctx


class ApiError(RuntimeError):
    pass


_API_LOCK = threading.Lock()
_LAST_CALL = [0.0]
API_MIN_GAP = 0.34                      # be a polite guest: at most three a second


def api_get(path: str, params: dict[str, str], key: str = "", timeout: int = 45) -> str:
    """One GET against api.nlt.to. `key` empty means anonymous, which is allowed."""
    q = dict(params)
    q["key"] = key or "TEST"           # TEST is Tyndale's own documented demo key
    url = f"{API_BASE}/{path}?" + urllib.parse.urlencode(q)
    with _API_LOCK:
        wait = API_MIN_GAP - (time.monotonic() - _LAST_CALL[0])
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL[0] = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            if e.code in (400, 401, 403, 404):
                raise ApiError(f"api.nlt.to said {e.code}. {body.strip()}") from e
            last = e
        except Exception as e:
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise ApiError(f"could not reach api.nlt.to ({last})")


# =========================================================== reading the API's HTML
# The API answers with a page, not JSON: a #bibletext div holding <verse_export>
# elements, each carrying bk/ch/vn attributes. Inside are the pieces the NLT actually
# marks up - paragraph classes for prose and poetry, <span class="red"> for the words
# of Christ, <span class="sc"> for LORD in small caps, and a footnote as an <a> next
# to a <span class="tn">. abide takes that apart into blocks and verses of its own,
# so nothing from the network is ever handed to the browser as markup.
_VE_RE = re.compile(
    r"<verse_export\b([^>]*)>(.*?)(?=<verse_export\b|</section>|</div>|\Z)", re.S | re.I)
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_HEAD_RE = re.compile(r"<h([1-6])\b([^>]*)>(.*?)</h\1\s*>", re.S | re.I)
_PARA_RE = re.compile(r"<p\b([^>]*)>", re.I)
# The verse number the API prints inside the text. Usually "3"; where a verse runs on
# from the previous chapter it is "8:1", so this takes whatever is in there.
_VN_RE = re.compile(r'<span[^>]*class="vn"[^>]*>.*?</span>', re.S | re.I)
_ATN_RE = re.compile(r'<a\b[^>]*class="a-tn"[^>]*>.*?</a>', re.S | re.I)
_TN_OPEN = re.compile(r'<span\b[^>]*class="tn"[^>]*>', re.I)
_SPAN_TOK = re.compile(r"<span\b[^>]*>|</span\s*>", re.I)
_TNREF_RE = re.compile(r'<span\b[^>]*class="tn-ref"[^>]*>.*?</span>', re.S | re.I)
_CLASS_RE = re.compile(r'class="([^"]*)"', re.I)
_TAG_RE = re.compile(r"<(/?)([a-zA-Z_][\w-]*)((?:\s[^>]*)?)>", re.S)
_KILL_RE = re.compile(r"<(script|style|link|iframe|object|embed)\b.*?</\1\s*>", re.S | re.I)
_KILL_SOLO = re.compile(r"<(script|style|link|iframe|meta|base)\b[^>]*/?>", re.I)
_BR_RE = re.compile(r"<br\b[^>]*>", re.I)
_KEEP_TAGS = {"em", "i", "b", "strong", "span", "br", "sup", "sub", "small"}
# the NLT's own inline marks, and nothing else: the words of Christ, LORD in small
# caps, a translator's addition, a footnote marker abide put there itself.
_KEEP_CLASSES = {"red", "sc", "subhead-sc", "divine-name", "nd", "wj", "add", "it",
                 "fn", "vt"}
FN_MARK = "\x00fn\x00"

# The API's paragraph classes, once the positional suffixes are off. "poet1-vn-sp" is
# a first-level poetry line that happens to start a verse and wants space above it -
# which is layout, not structure, so it comes back as poet1 with a flag.
_PARA_BASE = {
    "body": "body", "poet1": "poet1", "poet2": "poet2", "poet3": "poet3",
    "poet4": "poet3", "sp": "speaker", "speaker": "speaker", "psa-title": "psalm-title",
    "psalm-title": "psalm-title", "hebrew-title": "psalm-title", "title": "psalm-title",
    "list1": "list", "list2": "list", "list": "list", "extract": "extract",
    "citation": "citation", "acrostic": "acrostic", "sub": "subhead",
    "subhead": "subhead", "iex": "body", "otpoetry": "poet1", "ss": "body",
}
_SUFFIXES = ("-vn", "-sp", "-hd", "-fl", "-ch", "-nb", "-cn", "-first")


def _para_class(raw: str) -> tuple[str, bool]:
    """"poet1-vn-sp" -> ("poet1", True). Unknown classes read as prose."""
    cls = (raw or "").strip().lower()
    spaced = "-sp" in cls
    changed = True
    while changed:
        changed = False
        for suf in _SUFFIXES:
            if cls.endswith(suf):
                cls, changed = cls[: -len(suf)], True
    return _PARA_BASE.get(cls, "body"), spaced


def _plain(frag: str) -> str:
    """Every tag gone, entities left alone, whitespace tidied. A line break is a
    space; an inline tag is nothing at all, so "the <span>Lord</span>." does not
    come back as "the Lord ."."""
    frag = _KILL_RE.sub(" ", frag)
    frag = _BR_RE.sub(" ", frag)
    # a footnote marker abide put there itself goes with its asterisk, so the plain
    # text of a verse is the verse - what a card, a search or a recital compares against
    frag = re.sub(r'<span class="fn"[^>]*>.*?</span>', "", frag, flags=re.S | re.I)
    frag = re.sub(r"</?(p|div|h[1-6]|verse_export|section|li|tr|td)\b[^>]*>", " ", frag, flags=re.I)
    frag = re.sub(r"<[^>]+>", "", frag)
    frag = frag.replace("&nbsp;", " ").replace(FN_MARK, "")
    return re.sub(r"\s+", " ", frag).strip()


def _clean_inline(frag: str) -> str:
    """Keep the NLT's own inline marks, drop every other tag, keep no attribute but a
    class abide recognises. Nothing off the network keeps a tag we did not choose, and
    no href, style or event handler survives this."""
    frag = _KILL_RE.sub(" ", frag)
    frag = _KILL_SOLO.sub(" ", frag)

    def one(m: re.Match) -> str:
        closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3) or ""
        if name not in _KEEP_TAGS:
            return ""
        if closing:
            return f"</{name}>"
        if name == "br":
            return "<br>"
        classes = [c for group in _CLASS_RE.findall(attrs) for c in group.split()]
        classes = [c for c in classes if c in _KEEP_CLASSES]
        return f'<{name} class="{" ".join(classes)}">' if classes else f"<{name}>"

    frag = _TAG_RE.sub(one, frag)
    return re.sub(r"[ \t]+", " ", frag).strip()


def _take_footnotes(frag: str) -> tuple[str, list[str]]:
    """Lift the translator's notes out, leaving a marker where each one stood.

    The API writes a note as <a class="a-tn">*</a> followed by a <span class="tn">
    that has another span nested inside it, so a non-greedy match stops in the wrong
    place and leaks the note into the verse. This walks the spans instead.
    """
    frag = _ATN_RE.sub(FN_MARK, frag)
    notes: list[str] = []
    out: list[str] = []
    pos = 0
    while True:
        m = _TN_OPEN.search(frag, pos)
        if not m:
            out.append(frag[pos:])
            break
        out.append(frag[pos:m.start()])
        depth, k, close_at = 1, m.end(), len(frag)
        while depth:
            t = _SPAN_TOK.search(frag, k)
            if not t:
                close_at, k = len(frag), len(frag)
                break
            depth += 1 if t.group(0).lower().startswith("<span") else -1
            k = t.end()
            if not depth:
                close_at = t.start()
        inner = _TNREF_RE.sub("", frag[m.end():close_at])
        notes.append(_plain(inner))
        pos = k
    body = "".join(out)
    if body.count(FN_MARK) == len(notes):
        it = iter(notes)
        body = re.sub(re.escape(FN_MARK),
                      lambda _m: '<span class="fn" data-fn="%s">*</span>'
                      % html_escape(next(it), quote=True), body)
    else:                                  # markers and notes out of step: keep both
        body = body.replace(FN_MARK, '<span class="fn">*</span>')
    return body, [n for n in notes if n]


def parse_passage(html: str) -> dict:
    """The API's page -> {"blocks", "verses", "order", "footnotes", "header"}.

    A block is one paragraph of the passage: a class ("body", "poet1", "subhead"), the
    verse-by-verse parts abide is willing to render, and the verse numbers it covers.
    Keeping the parts separate is what lets a verse range be sliced out of a cached
    chapter later without going back to the network.
    """
    body = html
    header = ""
    hm = re.search(r'<h2[^>]*class="[^"]*bk_ch_vs_header[^"]*"[^>]*>(.*?)</h2>', body,
                   re.S | re.I)
    if hm:
        header = _plain(hm.group(1))
    if 'id="bibletext"' in body:
        body = body.split('id="bibletext"', 1)[1]
        body = body.split(">", 1)[1] if ">" in body else body
    blocks: list[dict] = []
    verses: dict[str, str] = {}
    order: list[str] = []
    footnotes: list[dict] = []
    cur: dict | None = None

    def open_block(cls: str, spaced: bool = False) -> dict:
        nonlocal cur
        cur = {"cls": cls, "parts": [], "verses": []}
        if spaced:
            cur["sp"] = 1
        blocks.append(cur)
        return cur

    def add_heading(cls: str, inner: str) -> None:
        nonlocal cur
        text = _clean_inline(inner)
        if _plain(inner):
            blocks.append({"cls": cls, "text": text, "parts": [], "verses": []})
            cur = None

    for m in _VE_RE.finditer(body):
        attrs = dict(_ATTR_RE.findall(m.group(1)))
        vn = attrs.get("vn") or ""
        inner = m.group(2)
        # headings first: a subhead belongs above the verse it sits inside, and the
        # API's own chapter-number heading is thrown away - abide prints its own.
        def heading(hmatch: re.Match) -> str:
            cls = " ".join(_CLASS_RE.findall(hmatch.group(2) or ""))
            if "subhead" in cls:
                add_heading("subhead", hmatch.group(3))
            elif "title" in cls:
                add_heading("psalm-title", hmatch.group(3))
            return ""

        inner = _HEAD_RE.sub(heading, inner)
        inner, notes = _take_footnotes(inner)
        for n in notes:
            footnotes.append({"vn": vn, "text": n})
        # split the verse across any paragraph break it contains
        pieces: list[tuple[tuple[str, bool] | None, str]] = []
        last = 0
        for pm in _PARA_RE.finditer(inner):
            if pm.start() > last:
                pieces.append((None, inner[last:pm.start()]))
            raw = " ".join(_CLASS_RE.findall(pm.group(1) or ""))
            pieces.append((_para_class(raw.split()[0] if raw.split() else ""), ""))
            last = pm.end()
        pieces.append((None, inner[last:]))
        text_parts: list[str] = []
        for cls, frag in pieces:
            if cls is not None:
                if cls[0] == "psalm-title":
                    open_block("psalm-title", cls[1])
                else:
                    open_block(cls[0], cls[1])
                if not frag.strip():
                    continue
            if cur is None:
                open_block("body")
            frag = _VN_RE.sub("", frag)
            clean = _clean_inline(frag)
            if not clean:
                continue
            # a psalm's superscription is carried on verse 1 in the API's markup, but
            # it is not part of the verse: it stays on screen and out of the text a
            # card, a search or a recital works from
            if cur["cls"] != "psalm-title":
                text_parts.append(_plain(frag))
            cur["parts"].append({"v": vn, "html": clean})
            if vn and vn not in cur["verses"]:
                cur["verses"].append(vn)
        if vn:
            joined = re.sub(r"\s+", " ", " ".join(p for p in text_parts if p)).strip()
            if vn in verses:
                verses[vn] = (verses[vn] + " " + joined).strip()
            else:
                verses[vn] = joined
                order.append(vn)
    blocks = [b for b in blocks if b["parts"] or b.get("text")]
    return {"blocks": blocks, "verses": verses, "order": order,
            "footnotes": footnotes, "header": header}


# ==================================================================== the database
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);

-- the text, once fetched, kept for good. One row per chapter per version.
CREATE TABLE IF NOT EXISTS passage(
  version TEXT NOT NULL, abbr TEXT NOT NULL, ch INTEGER NOT NULL,
  blocks TEXT NOT NULL, footnotes TEXT, verses INTEGER, words INTEGER,
  fetched_at TEXT, PRIMARY KEY(version, abbr, ch));
CREATE TABLE IF NOT EXISTS verse(
  version TEXT NOT NULL, abbr TEXT NOT NULL, ch INTEGER NOT NULL,
  vn INTEGER NOT NULL, text TEXT NOT NULL,
  PRIMARY KEY(version, abbr, ch, vn));

-- a plan is an ordered list you are somewhere in. No dates, so you cannot be behind.
CREATE TABLE IF NOT EXISTS plan(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, spec TEXT NOT NULL,
  created_at TEXT, started_on TEXT, active INTEGER DEFAULT 1, finished_on TEXT,
  pace TEXT, days_mask TEXT DEFAULT '1111111', note TEXT);
CREATE TABLE IF NOT EXISTS plan_item(
  id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL, seq INTEGER NOT NULL,
  refs TEXT NOT NULL, label TEXT, verses INTEGER, words INTEGER,
  done_on TEXT, reading_id INTEGER, skipped INTEGER DEFAULT 0,
  UNIQUE(plan_id, seq));
CREATE INDEX IF NOT EXISTS plan_item_open ON plan_item(plan_id, done_on, seq);

-- what you read, and when. The heart of it.
CREATE TABLE IF NOT EXISTS reading(
  id INTEGER PRIMARY KEY, day TEXT NOT NULL, started_at TEXT, ended_at TEXT,
  seconds INTEGER DEFAULT 0, refs TEXT NOT NULL, label TEXT,
  verses INTEGER DEFAULT 0, words INTEGER DEFAULT 0,
  plan_id INTEGER, plan_seq INTEGER, mode TEXT DEFAULT 'free',
  scroll INTEGER DEFAULT 0, note_count INTEGER DEFAULT 0, card_count INTEGER DEFAULT 0,
  recalled INTEGER DEFAULT 0, engaged INTEGER DEFAULT 0, finished INTEGER DEFAULT 0,
  -- 1 only when you said so. Opening a passage is not reading it, and no amount of
  -- time on screen is allowed to claim otherwise.
  confirmed INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS reading_day ON reading(day);
CREATE TABLE IF NOT EXISTS reading_chapter(
  reading_id INTEGER NOT NULL, abbr TEXT NOT NULL, ch INTEGER NOT NULL,
  v1 INTEGER, v2 INTEGER, day TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS rc_place ON reading_chapter(abbr, ch);
CREATE INDEX IF NOT EXISTS rc_reading ON reading_chapter(reading_id);

-- what you wrote. Notes are not a dead log here: they come back as cards.
CREATE TABLE IF NOT EXISTS note(
  id INTEGER PRIMARY KEY, created_at TEXT, updated_at TEXT, day TEXT,
  kind TEXT DEFAULT 'plain', ref TEXT, label TEXT, abbr TEXT, ch INTEGER,
  v1 INTEGER, v2 INTEGER, body TEXT, tags TEXT, reading_id INTEGER,
  starred INTEGER DEFAULT 0, card_id INTEGER);
CREATE INDEX IF NOT EXISTS note_place ON note(abbr, ch);
-- One note, many verses. A verse-by-verse note is a single entry you saved once,
-- with a row here per verse you actually wrote against, so the text can be filed and
-- searched and kept by the verse it belongs to rather than as one undifferentiated blob.
CREATE TABLE IF NOT EXISTS note_item(
  id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL, seq INTEGER,
  ref TEXT, label TEXT, abbr TEXT, ch INTEGER, v1 INTEGER, v2 INTEGER,
  text TEXT, card_id INTEGER,
  -- a comment can be written with any method: "verses" is one box, "soap" is four.
  -- `text` is always the plain reading of it; `body` keeps the fields for editing.
  kind TEXT DEFAULT 'verses', body TEXT);
CREATE INDEX IF NOT EXISTS note_item_note ON note_item(note_id, seq);
CREATE INDEX IF NOT EXISTS note_item_place ON note_item(abbr, ch, v1);
CREATE INDEX IF NOT EXISTS note_day ON note(day);
CREATE TABLE IF NOT EXISTS highlight(
  id INTEGER PRIMARY KEY, created_at TEXT, abbr TEXT, ch INTEGER,
  v1 INTEGER, v2 INTEGER, color TEXT DEFAULT 'yellow', snippet TEXT,
  ref TEXT, label TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS hl_place ON highlight(abbr, ch);

-- what you are keeping. FSRS-6 state lives on the card.
CREATE TABLE IF NOT EXISTS card(
  id INTEGER PRIMARY KEY, created_at TEXT, kind TEXT DEFAULT 'verse',
  ref TEXT, label TEXT, abbr TEXT, ch INTEGER, v1 INTEGER, v2 INTEGER,
  front TEXT, back TEXT, state INTEGER DEFAULT 0,
  stability REAL, difficulty REAL, due TEXT, last_review TEXT,
  reps INTEGER DEFAULT 0, lapses INTEGER DEFAULT 0, suspended INTEGER DEFAULT 0,
  note_id INTEGER, project_id INTEGER, tags TEXT);
CREATE INDEX IF NOT EXISTS card_due ON card(suspended, due);
CREATE TABLE IF NOT EXISTS review(
  id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL, at TEXT, day TEXT,
  rating INTEGER, state INTEGER, elapsed REAL, scheduled REAL, seconds INTEGER,
  stability REAL, difficulty REAL, accuracy REAL);
CREATE INDEX IF NOT EXISTS review_card ON review(card_id, at);
CREATE INDEX IF NOT EXISTS review_day ON review(day);

-- memorising a whole passage the slow way: ten times aloud, one verse a day,
-- then a hundred days of saying the lot. Andrew Davis's method, tracked.
CREATE TABLE IF NOT EXISTS project(
  id INTEGER PRIMARY KEY, created_at TEXT, name TEXT, refs TEXT, abbr TEXT,
  ch1 INTEGER, ch2 INTEGER, phase TEXT DEFAULT 'learning',
  learned INTEGER DEFAULT 0, review_day INTEGER DEFAULT 0,
  active INTEGER DEFAULT 1, last_on TEXT, target_days INTEGER DEFAULT 100);
CREATE TABLE IF NOT EXISTS project_log(
  id INTEGER PRIMARY KEY, project_id INTEGER, day TEXT, at TEXT,
  minutes REAL, added INTEGER, phase TEXT, note TEXT);

-- the thirty seconds before you read: what do you remember of the last one?
CREATE TABLE IF NOT EXISTS recall(
  id INTEGER PRIMARY KEY, at TEXT, day TEXT, ref TEXT, label TEXT,
  reading_id INTEGER, prompt TEXT, answer TEXT, grade INTEGER,
  seconds INTEGER, age_days INTEGER);
CREATE INDEX IF NOT EXISTS recall_day ON recall(day);
"""

DEFAULT_SETTINGS = {
    "version": "NLT",
    "api_key": "",
    "target_days": "4",             # the Power-of-4 threshold, changeable
    "theme": "dark",
    "reading_time": "06:30",        # the cue you are aiming at, not an alarm
    "retention": "0.90",            # FSRS desired retention
    "red_letters": "1",
    "footnotes": "1",
    "font_size": "18",
    "measure": "34",                # reading column width, in em
    "serif": "1",
    "journal_default": "verses",
    "recall_on": "1",
    "prefetch": "1",
    "new_cards_per_day": "5",
    "max_reviews_per_day": "60",
    # FSRS will happily push a well-known verse out nine years. A verse you are
    # keeping should come back at least once a year, so the schedule is capped.
    "max_interval": "365",
}

_LOCAL = threading.local()


def db() -> sqlite3.Connection:
    """One connection per thread, WAL on, foreign keys off (nothing cascades here)."""
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        first = not DB_PATH.exists()
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=CHECK_SAME_THREAD)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=15000")
        _LOCAL.conn = conn
        if first:
            init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    conn = conn or db()
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta(k, v) VALUES('schema_version', ?)",
                 (str(SCHEMA_VERSION),))
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(k, v) VALUES(?, ?)", (k, v))
    conn.commit()


def migrate() -> None:
    """Bring an older file up to date. New tables and columns only - nothing is dropped."""
    conn = db()
    conn.executescript(SCHEMA)
    have = {r["name"] for r in conn.execute("PRAGMA table_info(reading)")}
    icols = {r["name"] for r in conn.execute("PRAGMA table_info(note_item)")}
    if "kind" not in icols:
        conn.execute("ALTER TABLE note_item ADD COLUMN kind TEXT DEFAULT 'verses'")
        conn.execute("ALTER TABLE note_item ADD COLUMN body TEXT")
        conn.commit()
    if "confirmed" not in have:
        conn.execute("ALTER TABLE reading ADD COLUMN confirmed INTEGER DEFAULT 0")
        # anything already marked as counted was counted under the old rule, where
        # pressing the button was the only way to finish one
        conn.execute("UPDATE reading SET confirmed = 1 WHERE finished = 1 AND engaged = 1")
        conn.commit()
    have = {r["k"]: r["v"] for r in conn.execute("SELECT k, v FROM meta")}
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(k, v) VALUES(?, ?)", (k, v))
    if have.get("schema_version") != str(SCHEMA_VERSION):
        conn.execute("INSERT OR REPLACE INTO meta(k, v) VALUES('schema_version', ?)",
                     (str(SCHEMA_VERSION),))
    conn.commit()


def setting(k: str, default: str = "") -> str:
    row = db().execute("SELECT v FROM settings WHERE k = ?", (k,)).fetchone()
    return row["v"] if row else DEFAULT_SETTINGS.get(k, default)


def set_setting(k: str, v: str) -> None:
    conn = db()
    conn.execute("INSERT INTO settings(k, v) VALUES(?, ?) "
                 "ON CONFLICT(k) DO UPDATE SET v = excluded.v", (k, str(v)))
    conn.commit()


def settings_all() -> dict[str, str]:
    out = dict(DEFAULT_SETTINGS)
    for r in db().execute("SELECT k, v FROM settings"):
        out[r["k"]] = r["v"]
    return out


def _code_is_newer() -> bool:
    """Has abide.py been edited since this process started? If so the page is newer than
    the server answering it, and the two will disagree."""
    try:
        return os.path.getmtime(__file__) > STARTED_AT + 1
    except Exception:
        return False


def today_str() -> str:
    return date.today().isoformat()


def now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def d(s: str) -> date:
    return date.fromisoformat(s[:10])


# ============================================================== the passage cache
# One chapter is the unit. Every fetch stores the whole chapter, so a verse range is
# sliced out of what is already here rather than asked for again. Read the Bible twice
# and the second time costs nothing and works on a plane.
def _verse_cap() -> int:
    return KEYED_VERSE_CAP if setting("api_key") else ANON_VERSE_CAP


def fetch_chapter(abbr: str, ch: int, version: str = "") -> dict:
    """Pull one chapter from api.nlt.to, in as few requests as the caps allow."""
    version = version or setting("version") or "NLT"
    key = setting("api_key")
    total = verses_in(abbr, ch)
    cap = _verse_cap()
    windows: list[str] = []
    if total and total > cap:                    # Psalm 119 anonymously: four requests
        v = 1
        while v <= total:
            windows.append(f"{abbr}.{ch}.{v}-{min(v + cap - 1, total)}")
            v += cap
    else:
        windows.append(f"{abbr}.{ch}")
    merged: dict = {"blocks": [], "verses": {}, "order": [], "footnotes": []}
    for w in windows:
        got = parse_passage(api_get("passages", {"ref": w, "version": version}, key))
        if not got["order"] and not got["blocks"]:
            raise ApiError(f"api.nlt.to returned nothing for {w}")
        merged["blocks"] += got["blocks"]
        merged["footnotes"] += got["footnotes"]
        for vn in got["order"]:
            if vn not in merged["verses"]:
                merged["order"].append(vn)
            merged["verses"][vn] = got["verses"][vn]
    return merged


def store_chapter(abbr: str, ch: int, parsed: dict, version: str) -> None:
    conn = db()
    words = sum(len(t.split()) for t in parsed["verses"].values())
    conn.execute(
        "INSERT INTO passage(version, abbr, ch, blocks, footnotes, verses, words, fetched_at)"
        " VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(version, abbr, ch) DO UPDATE SET"
        " blocks=excluded.blocks, footnotes=excluded.footnotes, verses=excluded.verses,"
        " words=excluded.words, fetched_at=excluded.fetched_at",
        (version, abbr, ch, json.dumps(parsed["blocks"], separators=(",", ":")),
         json.dumps(parsed["footnotes"], separators=(",", ":")),
         len(parsed["order"]), words, now_str()))
    for vn, text in parsed["verses"].items():
        n = int(re.sub(r"\D", "", vn) or 0)
        if n:
            conn.execute("INSERT INTO verse(version, abbr, ch, vn, text) VALUES(?,?,?,?,?)"
                         " ON CONFLICT(version, abbr, ch, vn) DO UPDATE SET text=excluded.text",
                         (version, abbr, ch, n, text))
    conn.commit()


def chapter(abbr: str, ch: int, version: str = "", fetch: bool = True) -> dict:
    """A whole chapter, from the cache if it is here and from Tyndale if it is not."""
    version = version or setting("version") or "NLT"
    row = db().execute("SELECT * FROM passage WHERE version=? AND abbr=? AND ch=?",
                       (version, abbr, ch)).fetchone()
    if row:
        verses = {str(r["vn"]): r["text"] for r in db().execute(
            "SELECT vn, text FROM verse WHERE version=? AND abbr=? AND ch=? ORDER BY vn",
            (version, abbr, ch))}
        return {"blocks": json.loads(row["blocks"]),
                "footnotes": json.loads(row["footnotes"] or "[]"),
                "verses": verses, "order": list(verses.keys()),
                "cached": True, "fetched_at": row["fetched_at"], "words": row["words"]}
    if not fetch:
        return {}
    parsed = fetch_chapter(abbr, ch, version)
    store_chapter(abbr, ch, parsed, version)
    parsed["cached"] = False
    parsed["words"] = sum(len(t.split()) for t in parsed["verses"].values())
    return parsed


def _vnum(v: str | int) -> int:
    return int(re.sub(r"\D", "", str(v)) or 0)


def passage(ref: Ref, version: str = "", fetch: bool = True) -> dict:
    """One Ref as blocks ready to render, sliced from the cached chapter."""
    version = version or setting("version") or "NLT"
    chap = chapter(ref.abbr, ref.ch, version, fetch=fetch)
    if not chap:
        return {}
    if ref.v1 is None:
        blocks = chap["blocks"]
        verses = chap["verses"]
    else:
        lo, hi = ref.v1, (ref.v2 or ref.v1)
        blocks = []
        for b in chap["blocks"]:
            parts = [p for p in b.get("parts", []) if lo <= _vnum(p.get("v")) <= hi]
            if parts:
                nb = dict(b)
                nb["parts"] = parts
                nb["verses"] = [p["v"] for p in parts]
                blocks.append(nb)
            elif b.get("text") and blocks:
                pass                                # a subhead inside the range only
        verses = {k: v for k, v in chap["verses"].items() if lo <= _vnum(k) <= hi}
    fns = chap.get("footnotes", [])
    if ref.v1 is not None:
        lo, hi = ref.v1, (ref.v2 or ref.v1)
        fns = [f for f in fns if lo <= _vnum(f.get("vn")) <= hi]
    return {
        "ref": ref.key(), "label": ref.label(), "short": ref.short(),
        "abbr": ref.abbr, "ch": ref.ch, "v1": ref.v1, "v2": ref.v2,
        "book": book_title(ref.abbr), "chapters": chapters_in(ref.abbr),
        "blocks": blocks, "verses": verses,
        "footnotes": fns,
        "words": sum(len(t.split()) for t in verses.values()),
        "verse_count": len(verses), "cached": chap.get("cached", False),
        "version": version,
    }


def passage_text(ref: Ref, version: str = "", numbers: bool = True,
                 fetch: bool = True) -> str:
    """The passage as plain text, for the terminal, a card, or a recall answer."""
    p = passage(ref, version, fetch=fetch)
    if not p:
        return ""
    out = []
    for vn, text in sorted(p["verses"].items(), key=lambda kv: _vnum(kv[0])):
        out.append(f"{vn} {text}" if numbers else text)
    return " ".join(out)


def have_cached(ref: Ref, version: str = "") -> bool:
    version = version or setting("version") or "NLT"
    return bool(db().execute("SELECT 1 FROM passage WHERE version=? AND abbr=? AND ch=?",
                             (version, ref.abbr, ref.ch)).fetchone())


_PREFETCH_SEEN: set[str] = set()


def prefetch(refs: list[Ref], version: str = "") -> None:
    """Warm the cache in the background so tomorrow's reading is already here."""
    if setting("prefetch") != "1":
        return
    version = version or setting("version") or "NLT"
    todo = [r for r in refs if not have_cached(r, version)
            and f"{version}:{r.chapter_key()}" not in _PREFETCH_SEEN]
    if not todo:
        return
    for r in todo:
        _PREFETCH_SEEN.add(f"{version}:{r.chapter_key()}")

    def run() -> None:
        for r in todo:
            try:
                chapter(r.abbr, r.ch, version)
            except Exception:
                _PREFETCH_SEEN.discard(f"{version}:{r.chapter_key()}")
                return

    threading.Thread(target=run, daemon=True).start()


def render_text(blocks: list[dict], width: int = 78, numbers: bool = True) -> str:
    """Blocks as something readable in a terminal: poetry indented, headings bare,
    a verse number printed once where the verse starts and not on every line of it."""
    lines: list[str] = []
    seen: set[str] = set()
    for b in blocks:
        cls = b.get("cls", "body")
        if b.get("text"):
            t = _plain(b["text"])
            lines += ["", t.upper() if cls == "subhead" else t, ""]
            continue
        indent = {"poet1": 2, "poet2": 6, "poet3": 10, "speaker": 2, "acrostic": 2,
                  "extract": 4, "citation": 4, "list": 4, "psalm-title": 2}.get(cls, 0)
        text = ""
        for p in b.get("parts", []):
            t = _plain(p["html"])
            if not t:
                continue
            v = str(p.get("v") or "")
            if numbers and v and v not in seen and cls != "psalm-title":
                seen.add(v)
                text += f"{v} "
            text += t + " "
        text = text.strip()
        if not text:
            continue
        if b.get("sp") and lines and lines[-1].strip():
            lines.append("")
        words, line, wrapped = text.split(), "", []
        for w in words:
            if len(line) + len(w) + 1 > max(20, width - indent):
                wrapped.append(line)
                line = w
            else:
                line = (line + " " + w).strip()
        if line:
            wrapped.append(line)
        lines += [" " * indent + w for w in wrapped]
        if cls in ("body", "extract", "citation"):
            lines.append("")
    out: list[str] = []
    for ln in lines:                                  # never two blank lines running
        if ln.strip() or (out and out[-1].strip()):
            out.append(ln)
    return "\n".join(out).strip()


# ============================================================ what you read, and when
# One row per sitting. A sitting starts when a passage opens, gets a heartbeat while
# the tab is in front of you, and ends when you say you are done. What makes it count
# is the evidence: time on it, a note, a verse kept, a recall answered. A tap-through
# is still recorded - it just does not get to call itself a reading.
def refs_from_json(raw: str) -> list[Ref]:
    out: list[Ref] = []
    for k in json.loads(raw or "[]"):
        r = one_ref(k.replace(".", " ", 1) if k.count(".") == 1 else k)
        if r is None:
            m = re.match(r"^([1-3]?[A-Za-z]+)\.(\d+)(?:\.(\d+)(?:-(\d+))?)?$", k)
            if m:
                r = Ref(m.group(1), int(m.group(2)),
                        int(m.group(3)) if m.group(3) else None,
                        int(m.group(4)) if m.group(4) else None)
        if r:
            out.append(r)
    return out


def refs_to_json(refs: list[Ref]) -> str:
    return json.dumps([r.key() for r in refs], separators=(",", ":"))


def estimated_seconds(refs: list[Ref]) -> int:
    """How long this should take, from the real word count where we have the text."""
    total = 0.0
    for r in refs:
        p = db().execute("SELECT words FROM passage WHERE version=? AND abbr=? AND ch=?",
                         (setting("version"), r.abbr, r.ch)).fetchone()
        words = r.word_count()
        if p and p["words"] and r.v1 is None:
            words = p["words"]
        total += words / WORDS_PER_MINUTE * 60
    return int(total)


def start_reading(refs: list[Ref], plan_id: int | None = None, plan_seq: int | None = None,
                  mode: str = "free") -> int:
    conn = db()
    # coming back to the same passage on the same day carries on the same sitting rather
    # than starting a second one: three rows called "Genesis 1" is noise, not history
    open_row = conn.execute(
        "SELECT id FROM reading WHERE day = ? AND refs = ? AND finished = 0"
        " ORDER BY id DESC LIMIT 1", (today_str(), refs_to_json(refs))).fetchone()
    if open_row:
        return int(open_row["id"])
    cur = conn.execute(
        "INSERT INTO reading(day, started_at, refs, label, verses, words, plan_id,"
        " plan_seq, mode) VALUES(?,?,?,?,?,?,?,?,?)",
        (today_str(), now_str(), refs_to_json(refs), refs_label(refs),
         sum(r.verse_count() for r in refs), sum(r.word_count() for r in refs),
         plan_id, plan_seq, mode))
    conn.commit()
    return int(cur.lastrowid or 0)


def touch_reading(rid: int, seconds: int | None = None, scroll: int | None = None) -> None:
    conn = db()
    if seconds is not None:
        conn.execute("UPDATE reading SET seconds = MAX(seconds, ?) WHERE id = ?",
                     (int(seconds), rid))
    if scroll is not None:
        conn.execute("UPDATE reading SET scroll = MAX(scroll, ?) WHERE id = ?",
                     (min(100, int(scroll)), rid))
    conn.commit()


def note_evidence(rid: int) -> int:
    """How many notes this sitting still has anything in. Counted live, because a tally
    that only ever goes up will keep insisting you read something long after you have
    deleted every note you made on it."""
    if not rid:
        return 0
    rows = db().execute(
        "SELECT n.id, n.body, (SELECT COUNT(*) FROM note_item i WHERE i.note_id = n.id) k"
        " FROM note n WHERE n.reading_id = ?", (rid,)).fetchall()
    n = 0
    for r in rows:
        if r["k"]:
            n += 1
            continue
        try:
            body = json.loads(r["body"] or "{}")
        except Exception:
            body = {}
        if any(str(v).strip() for v in body.values()):
            n += 1
    return n


def recompute_reading(rid: int) -> dict:
    """Work out again whether a sitting counts, and put the plan back in step with it.

    Deleting the notes you made on a passage should take back the claim that you read
    it - including the day of the plan it consumed."""
    conn = db()
    row = conn.execute("SELECT * FROM reading WHERE id = ?", (rid,)).fetchone()
    if not row:
        return {}
    live = note_evidence(rid)
    if live != (row["note_count"] or 0):
        conn.execute("UPDATE reading SET note_count = ? WHERE id = ?", (live, rid))
        conn.commit()
        row = conn.execute("SELECT * FROM reading WHERE id = ?", (rid,)).fetchone()
    if not row["finished"]:
        return reading_dict(row)
    eng = _engaged(row, refs_from_json(row["refs"]))
    if eng != (row["engaged"] or 0):
        conn.execute("UPDATE reading SET engaged = ? WHERE id = ?", (eng, rid))
        if row["plan_id"] and row["plan_seq"] is not None:
            if eng:
                conn.execute("UPDATE plan_item SET done_on = ?, reading_id = ?"
                             " WHERE plan_id = ? AND seq = ?",
                             (row["day"], rid, row["plan_id"], row["plan_seq"]))
            else:
                conn.execute("UPDATE plan_item SET done_on = NULL, reading_id = NULL"
                             " WHERE reading_id = ?", (rid,))
        conn.commit()
    return reading_dict(conn.execute("SELECT * FROM reading WHERE id = ?",
                                     (rid,)).fetchone())


def _engaged(row: sqlite3.Row, refs: list[Ref]) -> int:
    """Does this sitting count as a reading?

    Two ways to qualify, and time on screen is not one of them. Either you said you read
    it - which settles it, in either direction, whenever you like - or you left something
    behind: a note that is still there, a verse kept, a recall answered. Opening a chapter
    and leaving it open is not reading it, and an app that decides otherwise is lying to
    you about your own week.
    """
    if _col(row, "confirmed") == -1:         # you said this one was only a look
        return 0
    if _col(row, "confirmed") == 1:          # you said you read it, and that settles it
        return 1
    if note_evidence(row["id"]) or row["card_count"] or row["recalled"]:
        return 1
    return 0                                 # time on screen, on its own, is not a reading


def _col(row: sqlite3.Row, name: str, default=0):
    try:
        return row[name]
    except Exception:
        return default


def finish_reading(rid: int, seconds: int | None = None, scroll: int | None = None,
                   advance_plan: bool = True, confirm: bool = True) -> dict:
    conn = db()
    if seconds is not None or scroll is not None:
        touch_reading(rid, seconds, scroll)
    if confirm:
        conn.execute("UPDATE reading SET confirmed = 1 WHERE id = ?", (rid,))
        conn.commit()
    row = conn.execute("SELECT * FROM reading WHERE id = ?", (rid,)).fetchone()
    if not row:
        return {}
    refs = refs_from_json(row["refs"])
    conn.execute("DELETE FROM reading_chapter WHERE reading_id = ?", (rid,))
    for r in refs:
        conn.execute("INSERT INTO reading_chapter(reading_id, abbr, ch, v1, v2, day)"
                     " VALUES(?,?,?,?,?,?)", (rid, r.abbr, r.ch, r.v1, r.v2, row["day"]))
    words = 0
    for r in refs:
        p = passage(r, fetch=False)
        words += p.get("words", 0) or r.word_count()
    engaged = _engaged(row, refs)
    conn.execute("UPDATE reading SET ended_at=?, finished=1, engaged=?, words=?"
                 " WHERE id=?", (now_str(), engaged, words, rid))
    if advance_plan and engaged and row["plan_id"] and row["plan_seq"] is not None:
        conn.execute("UPDATE plan_item SET done_on=?, reading_id=? WHERE plan_id=? AND seq=?",
                     (row["day"], rid, row["plan_id"], row["plan_seq"]))
    conn.commit()
    if row["plan_id"]:
        prefetch(upcoming_refs(int(row["plan_id"]), PREFETCH_AHEAD))
    return {"id": rid, "engaged": engaged, "words": words,
            "seconds": row["seconds"], "label": row["label"]}


SETTLE_IDLE_MINUTES = 30         # ...after this long with no heartbeat, it is over
SETTLE_GLANCE_SECONDS = 20       # ...and under this, with nothing written, it was a glance


def settle_readings() -> int:
    """Close out sittings that ended without anyone saying so.

    Closing the tab is the normal way of leaving a passage, so these have to be tidied
    up - but tidying them up is not the same as claiming you read them. A sitting closed
    this way is filed as a look, not a reading: it does not count toward the week and it
    does not advance the plan. If there was real time on it, Today asks you afterwards
    whether you finished it, and your answer decides. A glance with nothing to show for
    it is thrown away rather than logged at all.
    """
    conn = db()
    now = datetime.now()
    settled = 0
    for row in conn.execute("SELECT * FROM reading WHERE finished = 0").fetchall():
        over = row["day"] < today_str()
        if not over:
            try:
                started = datetime.fromisoformat(row["started_at"])
                over = now > started + timedelta(
                    seconds=(row["seconds"] or 0) + SETTLE_IDLE_MINUTES * 60)
            except Exception:
                over = True
        if not over:
            continue
        refs = refs_from_json(row["refs"])
        engaged = _engaged(row, refs)
        nothing = (not engaged and (row["seconds"] or 0) < SETTLE_GLANCE_SECONDS
                   and not row["note_count"] and not row["card_count"])
        if nothing:
            conn.execute("DELETE FROM reading_chapter WHERE reading_id = ?", (row["id"],))
            conn.execute("DELETE FROM reading WHERE id = ?", (row["id"],))
            conn.commit()
        else:
            finish_reading(int(row["id"]), advance_plan=bool(engaged), confirm=False)
        settled += 1
    return settled


def unconfirmed_readings(days: int = 4) -> list[dict]:
    """Sittings with real time on them that nobody ever claimed. Today asks about these
    rather than deciding for you."""
    floor = (date.today() - timedelta(days=days)).isoformat()
    out = []
    for row in db().execute(
            "SELECT * FROM reading WHERE finished = 1 AND confirmed = 0 AND engaged = 0"
            " AND day >= ? ORDER BY day DESC, id DESC LIMIT 6", (floor,)):
        refs = refs_from_json(row["refs"])
        need = max(120, int(estimated_seconds(refs) * 0.45))
        if (row["seconds"] or 0) >= need:
            d0 = reading_dict(row)
            d0["minutes"] = round((row["seconds"] or 0) / 60)
            d0["estimated"] = round(estimated_seconds(refs) / 60, 1)
            out.append(d0)
    return out


def reading_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "day": row["day"], "started_at": row["started_at"],
        "ended_at": row["ended_at"], "seconds": row["seconds"] or 0,
        "label": row["label"], "refs": json.loads(row["refs"] or "[]"),
        "verses": row["verses"], "words": row["words"], "mode": row["mode"],
        "plan_id": row["plan_id"], "engaged": row["engaged"], "finished": row["finished"],
        "notes": row["note_count"], "cards": row["card_count"], "recalled": row["recalled"],
        "clock": (row["started_at"] or "")[11:16],
        "confirmed": _col(row, "confirmed"),
    }


def recent_readings(limit: int = 40, day: str = "") -> list[dict]:
    q = "SELECT * FROM reading WHERE finished = 1"
    args: list = []
    if day:
        q += " AND day = ?"
        args.append(day)
    q += " ORDER BY started_at DESC LIMIT ?"
    args.append(limit)
    return [reading_dict(r) for r in db().execute(q, args)]


# --------------------------------------------------------------- the week and the run
def engaged_days(since: str = "", until: str = "") -> list[str]:
    q = "SELECT DISTINCT day FROM reading WHERE finished = 1 AND engaged = 1"
    args: list = []
    if since:
        q += " AND day >= ?"
        args.append(since)
    if until:
        q += " AND day <= ?"
        args.append(until)
    return [r["day"] for r in db().execute(q + " ORDER BY day", args)]


def week_view(end: date | None = None) -> dict:
    """The last seven days, and how many of them had a reading in them.

    Four is the number that matters. The Center for Bible Engagement's survey of
    40,000 people found one, two or three days a week looked like none at all, and
    four looked like a different life. So this is the headline, not the streak.
    """
    end = end or date.today()
    start = end - timedelta(days=6)
    got = set(engaged_days(start.isoformat(), end.isoformat()))
    light = {r["day"] for r in db().execute(
        "SELECT DISTINCT day FROM reading WHERE finished=1 AND engaged=0"
        " AND day >= ? AND day <= ?", (start.isoformat(), end.isoformat()))}
    days = []
    for i in range(7):
        dd = start + timedelta(days=i)
        s = dd.isoformat()
        days.append({"day": s, "dow": dd.strftime("%a"), "n": dd.day,
                     "read": s in got, "light": s in light and s not in got,
                     "future": dd > date.today()})
    target = int(setting("target_days") or TARGET_DAYS_PER_WEEK)
    return {"days": days, "count": len(got), "target": target,
            "met": len(got) >= target, "left": max(0, target - len(got)),
            "remaining": sum(1 for x in days if x["future"] or x["day"] == today_str())}


def read_map() -> dict[str, list[int]]:
    """Which chapters you have actually finished, by book. Small enough to hand to the
    page on every load, which is what lets the book picker show where you have been."""
    out: dict[str, list[int]] = {}
    for r in db().execute(
            "SELECT abbr, ch FROM reading_chapter rc JOIN reading r ON r.id = rc.reading_id"
            " WHERE rc.v1 IS NULL AND r.engaged = 1 GROUP BY abbr, ch"):
        out.setdefault(r["abbr"], []).append(r["ch"])
    return out


def month_view(on: date | None = None) -> dict:
    """The month you are in, day by day. What Today shows across its top: seven days is
    too short a window to see whether a month is going well."""
    on = on or date.today()
    first = on.replace(day=1)
    nxt = (first + timedelta(days=31)).replace(day=1)
    last = nxt - timedelta(days=1)
    got = set(engaged_days(first.isoformat(), last.isoformat()))
    light = {r["day"] for r in db().execute(
        "SELECT DISTINCT day FROM reading WHERE finished=1 AND engaged=0"
        " AND day >= ? AND day <= ?", (first.isoformat(), last.isoformat()))} - got
    mins = {r["day"]: round((r["secs"] or 0) / 60) for r in db().execute(
        "SELECT day, SUM(seconds) secs FROM reading WHERE finished=1 AND day >= ?"
        " AND day <= ? GROUP BY day", (first.isoformat(), last.isoformat()))}
    days = []
    for i in range((last - first).days + 1):
        dd = first + timedelta(days=i)
        iso = dd.isoformat()
        days.append({"day": iso, "n": dd.day, "dow": dd.strftime("%a")[0],
                     "wd": dd.weekday(), "read": iso in got, "light": iso in light,
                     "minutes": mins.get(iso, 0), "future": dd > date.today(),
                     "today": dd == date.today()})
    elapsed = sum(1 for x in days if not x["future"])
    target = int(setting("target_days") or TARGET_DAYS_PER_WEEK)
    return {"label": on.strftime("%B %Y"), "days": days, "read_count": len(got),
            "light_count": len(light), "elapsed": elapsed,
            "minutes": sum(mins.values()),
            "target": max(1, round(target * elapsed / 7)),
            "per_week": round(len(got) / elapsed * 7, 1) if elapsed else 0.0}


def streak() -> dict:
    """Days in a row with a reading, plus the one thing worth a warning.

    Lally's habit study is the reason this is quiet after one missed day: a single
    miss barely moved the automaticity curve, and two in a row is what stalled it.
    So `warn` is only true when yesterday and the day before were both empty.
    """
    days = engaged_days()
    have = set(days)
    today = date.today()
    cur = 0
    probe = today if today.isoformat() in have else today - timedelta(days=1)
    while probe.isoformat() in have:
        cur += 1
        probe -= timedelta(days=1)
    longest = 0
    run = 0
    prev: date | None = None
    for s in days:
        dd = d(s)
        run = run + 1 if prev and (dd - prev).days == 1 else 1
        longest = max(longest, run)
        prev = dd
    y = (today - timedelta(days=1)).isoformat()
    y2 = (today - timedelta(days=2)).isoformat()
    read_today = today.isoformat() in have
    return {
        "current": cur, "longest": longest, "read_today": read_today,
        "read_yesterday": y in have, "days_total": len(days),
        "warn": (not read_today) and (y not in have) and (y2 not in have) and bool(days),
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
    }


def clock_habit() -> dict:
    """When you actually read, and how tightly. A fixed cue is most of the battle,
    so this reports the median start time and how far a normal day sits from it."""
    rows = db().execute(
        "SELECT started_at FROM reading WHERE finished=1 AND engaged=1"
        " AND started_at IS NOT NULL ORDER BY started_at DESC LIMIT 120").fetchall()
    mins = []
    for r in rows:
        try:
            t = datetime.fromisoformat(r["started_at"])
            mins.append(t.hour * 60 + t.minute)
        except Exception:
            pass
    if not mins:
        return {"n": 0}
    mins.sort()
    med = mins[len(mins) // 2]
    spread = sorted(abs(m - med) for m in mins)[len(mins) // 2]
    buckets = [0] * 24
    for m in mins:
        buckets[m // 60] += 1
    return {"n": len(mins), "median": f"{med // 60:02d}:{med % 60:02d}",
            "spread_minutes": spread, "hours": buckets,
            "aim": setting("reading_time")}


# ==================================================================== plans
# A plan is an ordered list and a place in it. That is the whole model, and it is a
# deliberate one: nine out of ten people who start a one-year plan do not finish it,
# and the reason most of them give up reading altogether is the feeling of being
# behind. Nothing here can put you behind. Miss a week and the list waits; the only
# thing that moves is the date it will finish, which the app works out from the pace
# you actually keep rather than the one you meant to keep.
def _abbrs(*genres: str) -> list[str]:
    return [b[0] for b in BOOKS if b[4] in genres]


def _testament(t: str) -> list[str]:
    return [b[0] for b in BOOKS if b[3] == t]


BOOK_SETS: dict[str, tuple[str, list[str]]] = {
    "whole": ("the whole Bible", [b[0] for b in BOOKS]),
    "ot": ("the Old Testament", _testament("OT")),
    "nt": ("the New Testament", _testament("NT")),
    "gospels": ("the four Gospels", _abbrs("gospel")),
    "torah": ("the Law", _abbrs("law")),
    "history": ("the histories", _abbrs("history")),
    "wisdom": ("wisdom and poetry", _abbrs("wisdom")),
    "prophets": ("the prophets", _abbrs("prophets", "minor")),
    "paul": ("Paul's letters", _abbrs("paul")),
    "letters": ("all the letters", _abbrs("paul", "general")),
    # The storyline, in the fourteen books that carry it. Reading these in order gets
    # you the plot of the whole thing without stalling in the middle of Leviticus,
    # which is where most one-year plans lose people in week three.
    "narrative": ("the storyline, in 14 books",
                  ["Gen", "Exod", "Num", "Josh", "Judg", "1Sam", "2Sam", "1Kgs",
                   "2Kgs", "Ezra", "Neh", "Dan", "Luke", "Acts"]),
}

# Professor Grant Horner's ten lists: one chapter from each, every day, each list
# looping on its own. Ten chapters a day, and no two days ever line up the same way.
HORNER_LISTS: list[list[str]] = [
    ["Matt", "Mark", "Luke", "John"],
    ["Gen", "Exod", "Lev", "Num", "Deut"],
    ["Rom", "1Cor", "2Cor", "Gal", "Eph", "Phil", "Col", "Heb"],
    ["1Thes", "2Thes", "1Tim", "2Tim", "Titus", "Phlm", "Jas", "1Pet", "2Pet",
     "1Jn", "2Jn", "3Jn", "Jude", "Rev"],
    ["Job", "Eccl", "Song"],
    ["Ps"],
    ["Prov"],
    ["Josh", "Judg", "Ruth", "1Sam", "2Sam", "1Kgs", "2Kgs", "1Chr", "2Chr",
     "Ezra", "Neh", "Esth"],
    ["Isa", "Jer", "Lam", "Ezek", "Dan", "Hos", "Joel", "Amos", "Obad", "Jonah",
     "Mic", "Nah", "Hab", "Zeph", "Hag", "Zech", "Mal"],
    ["Acts"],
]

# Short, steadying passages. What the app offers instead of a lecture when two days
# have gone by - five minutes, and the run starts again tonight.
RESCUE = ["Ps.23", "Ps.121", "Ps.46", "Ps.1", "Ps.130", "Ps.103.1-14", "Isa.40.28-31",
          "Matt.11.28-30", "John.15.1-11", "Rom.8.31-39", "Phil.4.4-9", "Lam.3.19-26",
          "2Cor.4.16-18", "Ps.63.1-8", "Heb.12.1-3", "Ps.139.1-12", "Mic.6.6-8",
          "1Pet.1.3-9", "Eph.3.14-21", "Ps.90.1-2", "Josh.1.1-9", "Ps.51.1-12"]

PLAN_TEMPLATES: list[dict] = [
    {"id": "storyline", "name": "The storyline, in 14 books", "kind": "list",
     "set": "narrative", "pace": {"per_day": 2},
     "why": "The plot of the Bible, start to finish, without the stretches that stop "
            "people in week three. 14 books, about 15 minutes a day."},
    {"id": "nt-year", "name": "The New Testament, one year", "kind": "list",
     "set": "nt", "pace": {"per_day": 1},
     "why": "One chapter a day. 260 chapters, so it finishes inside a year even if "
            "you read five days a week."},
    {"id": "gospels-90", "name": "The Gospels in 90 days", "kind": "list",
     "set": "gospels", "pace": {"per_day": 1},
     "why": "89 chapters, one a day. The best place to start if you are starting."},
    {"id": "whole-year", "name": "The whole Bible, one year", "kind": "list",
     "set": "whole", "pace": {"per_day": 4},
     "why": "1,189 chapters at four a day. Honest warning: this is the plan nine out "
            "of ten people abandon. It works here because falling behind is not a "
            "thing that can happen."},
    {"id": "whole-two-year", "name": "The whole Bible, two years", "kind": "list",
     "set": "whole", "pace": {"minutes": 10},
     "why": "Ten minutes a day, whatever that comes to in chapters. Slower than the "
            "one-year plan and far more likely to be the one you finish."},
    {"id": "two-track", "name": "Old and New together", "kind": "tracks",
     "tracks": ["ot", "nt"], "pace": {"per_day": 1},
     "why": "One Old Testament chapter and one New Testament chapter a day, each "
            "moving at its own speed. The New Testament finishes several times over."},
    {"id": "three-track", "name": "Old, New, and a psalm", "kind": "tracks",
     "tracks": ["ot", "nt", "psalms"], "pace": {"per_day": 1},
     "why": "Three chapters: history and prophecy, gospel and letter, and a psalm to "
            "pray. About 12 minutes."},
    {"id": "horner", "name": "Horner's ten lists", "kind": "tracks",
     "tracks": ["horner"], "pace": {"per_day": 1},
     "why": "Ten chapters a day from ten places at once - a Gospel, the Law, a "
            "letter, a psalm, a proverb. Nothing has time to get dull. It is a lot: "
            "about 35 minutes."},
    {"id": "psalms-month", "name": "The Psalms every month", "kind": "dated",
     "rule": "psalms5", "pace": {"per_day": 5},
     "why": "Five psalms a day by the date - the 8th means Psalm 8, 38, 68, 98, 128. "
            "All 150 in a month, every month."},
    {"id": "proverbs-month", "name": "A proverb a day", "kind": "dated",
     "rule": "proverbs", "pace": {"per_day": 1},
     "why": "Chapter matches the date. Thirty-one chapters, one a month, for years."},
    {"id": "oycb", "name": "One Year Chronological Bible", "kind": "api",
     "api_plan": "OYCB", "pace": {"per_day": 1},
     "why": "Tyndale's own chronological plan, in the order things happened, read "
            "straight from the NLT API a day at a time."},
    {"id": "one-book", "name": "One book, slowly", "kind": "list",
     "set": "", "pace": {"per_day": 1},
     "why": "Pick any book and take a chapter a day. The best way to actually know "
            "one letter rather than half-know all of them."},
]


def _chapters_of(abbrs: list[str]) -> list[Ref]:
    out: list[Ref] = []
    for a in abbrs:
        out += [Ref(a, c) for c in range(1, chapters_in(a) + 1)]
    return out


def _group_by_pace(refs: list[Ref], pace: dict) -> list[list[Ref]]:
    """Cut an ordered list of chapters into days. Chapters are never split."""
    per = int(pace.get("per_day") or 0)
    minutes = float(pace.get("minutes") or 0)
    if pace.get("in_days") and refs:
        # "John in 10 days": twenty-one chapters spread as evenly as they go
        n = max(1, min(int(pace["in_days"]), len(refs)))
        out: list[list[Ref]] = []
        for k in range(n):
            chunk = refs[k * len(refs) // n:(k + 1) * len(refs) // n]
            if chunk:
                out.append(chunk)
        return out
    if pace.get("finish_by") and refs:
        try:
            days = max(1, (d(str(pace["finish_by"])) - date.today()).days)
            per = max(1, math.ceil(len(refs) / days))
        except Exception:
            per = per or 1
    days: list[list[Ref]] = []
    if minutes > 0:
        # close the day at whichever count lands nearest the target, rather than always
        # overshooting: ten minutes of Genesis is four chapters, not five
        cur: list[Ref] = []
        got = 0.0
        for r in refs:
            m = r.minutes()
            if cur and abs(got - minutes) <= abs(got + m - minutes):
                days.append(cur)
                cur, got = [], 0.0
            cur.append(r)
            got += m
        if cur:
            days.append(cur)
        return days
    per = max(1, per or 1)
    return [refs[i:i + per] for i in range(0, len(refs), per)]


def _track_refs(name: str) -> list[list[Ref]]:
    if name == "horner":
        return [_chapters_of(lst) for lst in HORNER_LISTS]
    if name == "psalms":
        return [_chapters_of(["Ps"])]
    title_set = BOOK_SETS.get(name)
    return [_chapters_of(title_set[1])] if title_set else []


def _dated_refs(rule: str, on: date) -> list[Ref]:
    if rule == "proverbs":
        return [Ref("Prov", min(on.day, 31))]
    if rule == "psalms5":
        return [Ref("Ps", n) for n in (on.day, on.day + 30, on.day + 60,
                                       on.day + 90, on.day + 120) if n <= 150]
    return []


def build_items(kind: str, spec: dict, horizon: int = 400) -> list[list[Ref]]:
    """A plan's days, as lists of chapters. `horizon` bounds the endless ones."""
    if kind == "list":
        refs = ([Ref(*x) for x in spec["refs"]] if spec.get("refs") else
                _chapters_of(spec.get("books") or BOOK_SETS[spec.get("set", "nt")][1]))
        return _group_by_pace(refs, spec.get("pace") or {"per_day": 1})
    if kind == "tracks":
        tracks: list[list[Ref]] = []
        for t in spec.get("tracks", []):
            tracks += _track_refs(t)
        tracks = [t for t in tracks if t]
        if not tracks:
            return []
        n = min(horizon, max(len(t) for t in tracks))
        # a track shorter than the plan loops, which is the point of the ten lists
        return [[t[i % len(t)] for t in tracks] for i in range(n)]
    if kind == "custom":
        out: list[list[Ref]] = []
        for line in spec.get("lines", []):
            got = parse_ref(line)
            if got:
                out.append(got)
        return out
    return []                                     # "dated" and "api" resolve per day


def create_plan(kind: str, spec: dict, name: str = "", days_mask: str = "1111111") -> int:
    conn = db()
    label = name or spec.get("name") or kind
    conn.execute("UPDATE plan SET active = 0 WHERE active = 1")
    cur = conn.execute(
        "INSERT INTO plan(name, kind, spec, created_at, started_on, active, pace,"
        " days_mask) VALUES(?,?,?,?,?,1,?,?)",
        (label, kind, json.dumps(spec, separators=(",", ":")), now_str(), today_str(),
         json.dumps(spec.get("pace") or {}, separators=(",", ":")), days_mask))
    pid = int(cur.lastrowid or 0)
    conn.commit()
    materialize(pid)
    return pid


def materialize(plan_id: int, extend_to: int = 0) -> int:
    """Write (or extend) the day list. Days already done are never touched."""
    conn = db()
    p = conn.execute("SELECT * FROM plan WHERE id = ?", (plan_id,)).fetchone()
    if not p:
        return 0
    kind, spec = p["kind"], json.loads(p["spec"])
    if kind in ("dated", "api"):
        return 0
    have = conn.execute("SELECT COUNT(*) n FROM plan_item WHERE plan_id = ?",
                        (plan_id,)).fetchone()["n"]
    horizon = max(extend_to, have + 400) if kind == "tracks" else 100_000
    days = build_items(kind, spec, horizon)
    for i, refs in enumerate(days):
        if i < have:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO plan_item(plan_id, seq, refs, label, verses, words)"
            " VALUES(?,?,?,?,?,?)",
            (plan_id, i, refs_to_json(refs), refs_label(refs),
             sum(r.verse_count() for r in refs), sum(r.word_count() for r in refs)))
    conn.commit()
    return len(days)


def active_plan() -> sqlite3.Row | None:
    return db().execute("SELECT * FROM plan WHERE active = 1 ORDER BY id DESC"
                        " LIMIT 1").fetchone()


def _api_day_refs(api_plan: str, on: date) -> list[Ref]:
    """Ask the API what its own plan has for a day, and read the refs off the headers."""
    html = api_get("reading", {"plan": api_plan, "date": on.isoformat(),
                               "version": setting("version") or "NLT"},
                   setting("api_key"))
    refs: list[Ref] = []
    for m in re.finditer(r'<h2[^>]*class="[^"]*bk_ch_vs_header[^"]*"[^>]*>(.*?)</h2>',
                         html, re.S | re.I):
        head = _plain(m.group(1)).rsplit(",", 1)[0]
        refs += parse_ref(head)
    return refs


def plan_item_for_today(plan_id: int) -> sqlite3.Row | None:
    """The next thing to read. For a list plan that is the first day not done; for a
    dated plan it is what today's date says; for an API plan it is the next day of it."""
    conn = db()
    p = conn.execute("SELECT * FROM plan WHERE id = ?", (plan_id,)).fetchone()
    if not p:
        return None
    kind, spec = p["kind"], json.loads(p["spec"])
    if kind == "dated":
        seq = (date.today() - d(p["started_on"])).days
        row = conn.execute("SELECT * FROM plan_item WHERE plan_id=? AND seq=?",
                           (plan_id, seq)).fetchone()
        if row:
            return row
        refs = _dated_refs(spec.get("rule", ""), date.today())
        if not refs:
            return None
        conn.execute("INSERT OR IGNORE INTO plan_item(plan_id, seq, refs, label, verses,"
                     " words) VALUES(?,?,?,?,?,?)",
                     (plan_id, seq, refs_to_json(refs), refs_label(refs),
                      sum(r.verse_count() for r in refs),
                      sum(r.word_count() for r in refs)))
        conn.commit()
        return conn.execute("SELECT * FROM plan_item WHERE plan_id=? AND seq=?",
                            (plan_id, seq)).fetchone()
    if kind == "api":
        row = conn.execute("SELECT * FROM plan_item WHERE plan_id=? AND done_on IS NULL"
                           " ORDER BY seq LIMIT 1", (plan_id,)).fetchone()
        if row:
            return row
        seq = conn.execute("SELECT COALESCE(MAX(seq) + 1, 0) n FROM plan_item"
                           " WHERE plan_id = ?", (plan_id,)).fetchone()["n"]
        # day one of the plan is the day you started it, in the plan's own calendar
        on = d(spec.get("anchor") or p["started_on"]) + timedelta(days=seq)
        refs = _api_day_refs(spec.get("api_plan", "OYCB"), on)
        if not refs:
            return None
        conn.execute("INSERT INTO plan_item(plan_id, seq, refs, label, verses, words)"
                     " VALUES(?,?,?,?,?,?)",
                     (plan_id, seq, refs_to_json(refs), refs_label(refs),
                      sum(r.verse_count() for r in refs),
                      sum(r.word_count() for r in refs)))
        conn.commit()
        return conn.execute("SELECT * FROM plan_item WHERE plan_id=? AND seq=?",
                            (plan_id, seq)).fetchone()
    row = conn.execute("SELECT * FROM plan_item WHERE plan_id=? AND done_on IS NULL"
                       " AND skipped=0 ORDER BY seq LIMIT 1", (plan_id,)).fetchone()
    if row is None and p["kind"] == "tracks":
        materialize(plan_id, extend_to=0)
        row = conn.execute("SELECT * FROM plan_item WHERE plan_id=? AND done_on IS NULL"
                           " AND skipped=0 ORDER BY seq LIMIT 1", (plan_id,)).fetchone()
    return row


def upcoming_items(plan_id: int, n: int = 4) -> list[sqlite3.Row]:
    return db().execute(
        "SELECT * FROM plan_item WHERE plan_id=? AND done_on IS NULL AND skipped=0"
        " ORDER BY seq LIMIT ?", (plan_id, n)).fetchall()


def upcoming_refs(plan_id: int, n: int = 3) -> list[Ref]:
    out: list[Ref] = []
    for row in upcoming_items(plan_id, n):
        out += refs_from_json(row["refs"])
    return out


def plan_progress(plan_id: int) -> dict:
    conn = db()
    p = conn.execute("SELECT * FROM plan WHERE id = ?", (plan_id,)).fetchone()
    if not p:
        return {}
    tot = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(words),0) w FROM plan_item"
                       " WHERE plan_id=?", (plan_id,)).fetchone()
    done = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(words),0) w FROM plan_item"
                        " WHERE plan_id=? AND done_on IS NOT NULL", (plan_id,)).fetchone()
    spec = json.loads(p["spec"])
    endless = p["kind"] in ("tracks", "dated")
    total = 0 if endless else tot["n"]
    left = max(0, total - done["n"]) if total else 0
    # The finish date comes from the pace you actually keep, not the one you meant to.
    # Until there are two weeks of history to go on it uses your target instead, which
    # is the honest thing to say: this is what it looks like if you hit four days.
    target = int(setting("target_days") or TARGET_DAYS_PER_WEEK)
    all_days = engaged_days()
    since = (date.today() - timedelta(days=27)).isoformat()
    recent = len(engaged_days(since))
    observed = 0
    if all_days:
        span = (date.today() - d(all_days[0])).days + 1
        observed = min(28, span)
    if observed >= 14:
        per_week = recent / (observed / 7)
        basis = "the last four weeks"
    else:
        per_week = float(target)
        basis = f"your target of {target} days a week"
    per_day = max(0.15, per_week / 7)
    finish = None
    if left and per_day:
        finish = (date.today() + timedelta(days=math.ceil(left / per_day))).isoformat()
    return {
        "id": p["id"], "name": p["name"], "kind": p["kind"], "spec": spec,
        "started_on": p["started_on"], "days_mask": p["days_mask"],
        "total": total, "done": done["n"], "left": left, "endless": endless,
        "percent": round(100 * done["n"] / total, 1) if total else None,
        "finish_estimate": finish, "days_per_week": round(per_week, 1),
        "pace_basis": basis,
        "words_done": done["w"], "words_total": tot["w"],
    }


def rescue_ref() -> Ref:
    """Five minutes, chosen so it is not the same one you saw last time."""
    seen = {r["label"] for r in db().execute(
        "SELECT label FROM reading ORDER BY id DESC LIMIT 12")}
    for key in RESCUE:
        r = one_ref(key.replace(".", " ", 1))
        if r and r.label() not in seen:
            return r
    return Ref("Ps", 23)


# ============================================================= keeping it: FSRS-6
# The scheduler is FSRS-6, the algorithm Anki settled on, with its published default
# weights. Three numbers describe a card: how hard it is for you (difficulty), how
# long the memory currently lasts (stability), and the chance you would get it right
# right now (retrievability). A review is due when that chance falls to your target,
# 90% unless you change it. It beats the old SM-2 interval doubling because it fits
# the forgetting curve instead of guessing at it.
FSRS_W = (0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722,
          0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425,
          0.0912, 0.0658, 0.1542)
S_MIN, S_MAX = 0.01, 36500.0
D_MIN, D_MAX = 1.0, 10.0
AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4
RATING_NAMES = {AGAIN: "again", HARD: "hard", GOOD: "good", EASY: "easy"}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _decay() -> float:
    return FSRS_W[20]


def _factor() -> float:
    return 0.9 ** (-1.0 / _decay()) - 1.0


def retrievability(elapsed_days: float, stability: float) -> float:
    """The chance you would get it right today. R(S, S) = 0.9, by construction."""
    if stability <= 0:
        return 0.0
    return (1.0 + _factor() * max(0.0, elapsed_days) / stability) ** (-_decay())


def next_interval(stability: float, retention: float = 0.9) -> float:
    """How many days until the chance of recall falls to your target."""
    r = _clamp(retention, 0.70, 0.99)
    return (stability / _factor()) * (r ** (-1.0 / _decay()) - 1.0)


def init_state(rating: int) -> tuple[float, float]:
    s = _clamp(FSRS_W[rating - 1], S_MIN, S_MAX)
    d = _clamp(FSRS_W[4] - math.exp(FSRS_W[5] * (rating - 1)) + 1.0, D_MIN, D_MAX)
    return s, d


def next_difficulty(d0: float, rating: int) -> float:
    """Linear damping - a card near 10 stops getting harder - then mean reversion
    towards the difficulty an Easy first answer would have given it."""
    delta = -FSRS_W[6] * (rating - 3)
    dp = d0 + delta * (10.0 - d0) / 9.0
    target = _clamp(FSRS_W[4] - math.exp(FSRS_W[5] * 3) + 1.0, D_MIN, D_MAX)
    return _clamp(FSRS_W[7] * target + (1.0 - FSRS_W[7]) * dp, D_MIN, D_MAX)


def stability_success(dif: float, s: float, r: float, rating: int) -> float:
    hard = FSRS_W[15] if rating == HARD else 1.0
    easy = FSRS_W[16] if rating == EASY else 1.0
    gain = (math.exp(FSRS_W[8]) * (11.0 - dif) * (s ** -FSRS_W[9])
            * (math.exp(FSRS_W[10] * (1.0 - r)) - 1.0) * hard * easy)
    return _clamp(s * (1.0 + gain), S_MIN, S_MAX)


def stability_lapse(dif: float, s: float, r: float) -> float:
    forget = (FSRS_W[11] * (dif ** -FSRS_W[12]) * ((s + 1.0) ** FSRS_W[13] - 1.0)
              * math.exp(FSRS_W[14] * (1.0 - r)))
    return _clamp(min(forget, s), S_MIN, S_MAX)


def stability_same_day(s: float, rating: int) -> float:
    return _clamp(s * math.exp(FSRS_W[17] * (rating - 3 + FSRS_W[18])) * (s ** -FSRS_W[19]),
                  S_MIN, S_MAX)


def schedule(card: sqlite3.Row | dict, rating: int, retention: float = 0.9,
             on: date | None = None) -> dict:
    """One review, applied. Returns the new state and the day it comes back."""
    on = on or date.today()
    stab = (card["stability"] if card["stability"] else None)
    dif = (card["difficulty"] if card["difficulty"] else None)
    last = card["last_review"]
    elapsed = 0.0
    if last:
        try:
            elapsed = max(0.0, (on - d(last)).days)
        except Exception:
            elapsed = 0.0
    if stab is None or dif is None:                       # first time seen
        s, dd = init_state(rating)
        r = 1.0
    else:
        r = retrievability(elapsed, stab)
        dd = next_difficulty(dif, rating)
        if elapsed < 1:
            s = stability_same_day(stab, rating)
        elif rating == AGAIN:
            s = stability_lapse(dd, stab, r)
        else:
            s = stability_success(dd, stab, r, rating)
    if rating == AGAIN:
        interval = 1.0                                    # tomorrow, always
        state = 3
    else:
        interval = next_interval(s, retention)
        state = 2
    cap = 3650
    try:
        cap = int(_clamp(float(setting("max_interval") or 365), 7, 3650))
    except Exception:
        pass
    days = int(_clamp(round(interval), 1, cap))
    return {"stability": s, "difficulty": dd, "state": state,
            "due": (on + timedelta(days=days)).isoformat(),
            "interval": days, "elapsed": elapsed, "retrievability": r}


# ---------------------------------------------------------------------- the cards
CARD_KINDS = ("verse", "firstletter", "note", "fact")


def first_letters(text: str) -> str:
    """The verse as its own skeleton: "F___ G__ s_ l____ t__ w____". Cue reduction -
    enough of a prompt to start you off, not enough to read."""
    out = []
    for tok in re.findall(r"\S+|\s+", text):
        if tok.isspace():
            out.append(tok)
            continue
        head = tok[0]
        rest = "".join("_" if ch.isalnum() else ch for ch in tok[1:])
        out.append(head + rest)
    return "".join(out)


def make_card(kind: str, ref: Ref | None, front: str = "", back: str = "",
              note_id: int | None = None, project_id: int | None = None,
              tags: str = "") -> int:
    conn = db()
    if ref is not None and kind in ("verse", "firstletter") and not back:
        back = passage_text(ref, numbers=False)
    if ref is not None and not front:
        front = ref.label()
    cur = conn.execute(
        "INSERT INTO card(created_at, kind, ref, label, abbr, ch, v1, v2, front, back,"
        " due, note_id, project_id, tags) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (now_str(), kind, ref.key() if ref else None, ref.label() if ref else front[:80],
         ref.abbr if ref else None, ref.ch if ref else None,
         ref.v1 if ref else None, ref.v2 if ref else None,
         front, back, today_str(), note_id, project_id, tags))
    cid = int(cur.lastrowid or 0)
    if note_id:
        conn.execute("UPDATE note SET card_id = ? WHERE id = ?", (cid, note_id))
    conn.commit()
    return cid


def card_dict(row: sqlite3.Row) -> dict:
    stab = row["stability"] or 0
    elapsed = 0.0
    if row["last_review"]:
        try:
            elapsed = (date.today() - d(row["last_review"])).days
        except Exception:
            pass
    return {
        "id": row["id"], "kind": row["kind"], "ref": row["ref"], "label": row["label"],
        "front": row["front"], "back": row["back"], "state": row["state"],
        "stability": round(stab, 2), "difficulty": round(row["difficulty"] or 0, 2),
        "due": row["due"], "reps": row["reps"], "lapses": row["lapses"],
        "suspended": row["suspended"], "note_id": row["note_id"],
        "project_id": row["project_id"], "tags": row["tags"],
        "retrievability": round(retrievability(elapsed, stab), 3) if stab else None,
        "last_review": row["last_review"],
        "cue": first_letters(row["back"] or "") if row["kind"] == "firstletter" else "",
    }


def due_cards(limit: int = 0) -> list[dict]:
    limit = limit or int(setting("max_reviews_per_day") or 60)
    rows = db().execute(
        "SELECT * FROM card WHERE suspended = 0 AND due <= ? AND state > 0"
        " ORDER BY due, id LIMIT ?", (today_str(), limit)).fetchall()
    new_room = max(0, int(setting("new_cards_per_day") or 5))
    seen_new = db().execute(
        "SELECT COUNT(DISTINCT card_id) n FROM review WHERE day = ? AND state = 0",
        (today_str(),)).fetchone()["n"]
    fresh = db().execute(
        "SELECT * FROM card WHERE suspended = 0 AND state = 0 ORDER BY id LIMIT ?",
        (max(0, new_room - seen_new),)).fetchall()
    return [card_dict(r) for r in list(rows) + list(fresh)]


def review_card(card_id: int, rating: int, seconds: int = 0,
                accuracy: float | None = None) -> dict:
    conn = db()
    row = conn.execute("SELECT * FROM card WHERE id = ?", (card_id,)).fetchone()
    if not row:
        return {}
    rating = int(_clamp(rating, 1, 4))
    ret = float(setting("retention") or 0.9)
    before_state = row["state"]
    res = schedule(row, rating, ret)
    conn.execute(
        "UPDATE card SET stability=?, difficulty=?, state=?, due=?, last_review=?,"
        " reps=reps+1, lapses=lapses+? WHERE id=?",
        (res["stability"], res["difficulty"], res["state"], res["due"], today_str(),
         1 if rating == AGAIN else 0, card_id))
    conn.execute(
        "INSERT INTO review(card_id, at, day, rating, state, elapsed, scheduled,"
        " seconds, stability, difficulty, accuracy) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (card_id, now_str(), today_str(), rating, before_state, res["elapsed"],
         res["interval"], seconds, res["stability"], res["difficulty"], accuracy))
    conn.commit()
    res["card_id"] = card_id
    res["rating"] = rating
    res["due_in_words"] = _in_words(res["interval"])
    return res


def _in_words(days: int) -> str:
    if days <= 1:
        return "tomorrow"
    if days < 7:
        return f"in {days} days"
    if days < 14:
        return "in a week"
    if days < 60:
        return f"in {round(days / 7)} weeks"
    if days < 46:
        return "in a month"
    if days < 365:
        n = round(days / 30.4)
        return "in a month" if n <= 1 else f"in {n} months"
    y = days / 365.25
    return "in a year" if y < 1.5 else f"in {y:.1f} years"


# --------------------------------------------------------- typing a verse back out
_WORD_RE = re.compile(r"[a-z0-9']+")


def _norm_words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower().replace("’", "'"))


def compare_recital(typed: str, actual: str) -> dict:
    """Score a verse typed from memory against the text, word by word.

    A word-level longest common subsequence, so a missed word shifts nothing after
    it. Retrieval that produces the words is worth far more than recognising them,
    which is the whole reason this exists rather than a self-graded flip.
    """
    a, b = _norm_words(typed), _norm_words(actual)
    n, m = len(a), len(b)
    if not m:
        return {"accuracy": 0.0, "matched": 0, "total": 0, "suggest": AGAIN, "diff": []}
    prev = [0] * (m + 1)
    table: list[list[int]] = [prev]
    for i in range(n):
        cur = [0] * (m + 1)
        for j in range(m):
            cur[j + 1] = prev[j] + 1 if a[i] == b[j] else max(cur[j], prev[j + 1])
        table.append(cur)
        prev = cur
    # walk back for a word-by-word verdict against the real text
    i, j = n, m
    marks: list[tuple[str, str]] = []
    while j > 0:
        if i > 0 and a[i - 1] == b[j - 1]:
            marks.append(("ok", b[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and table[i - 1][j] >= table[i][j - 1]:
            i -= 1
        else:
            marks.append(("miss", b[j - 1]))
            j -= 1
    marks.reverse()
    matched = sum(1 for k, _ in marks if k == "ok")
    acc = matched / m
    extra = max(0, n - matched)
    acc = max(0.0, acc - 0.5 * extra / m)            # padding is not remembering
    suggest = EASY if acc >= 0.98 else GOOD if acc >= 0.90 else HARD if acc >= 0.70 else AGAIN
    return {"accuracy": round(acc, 3), "matched": matched, "total": m,
            "extra": extra, "suggest": suggest,
            "diff": [{"k": k, "w": w} for k, w in marks]}


# ================================================== the journal, and why it comes back
# The complaint people make about note-taking in a Bible app is that the notes go in
# and never come out: a reverse-chronological list nobody scrolls. Here a note is
# attached to a place in the text, is searchable by that place, and can be turned into
# a card - so the thing you saw in Romans 8 in March is put in front of you again in
# June, when you would otherwise have lost it.
NOTE_KINDS: dict[str, dict] = {
    # the default: a line against whichever verses you have something to say about,
    # saved as one entry. Not a field-per-method form - a margin.
    "verses": {"name": "Verse by verse", "per_verse": True, "fields": [
        ("summary", "On the passage as a whole", "Optional. One or two lines."),
    ]},
    "soap": {"name": "SOAP", "fields": [
        ("s", "Scripture", "The verse, written out. Copying it slows you down enough to see it."),
        ("o", "Observation", "What is actually happening here? Who is speaking, to whom?"),
        ("a", "Application", "What does this ask of me this week - concretely?"),
        ("p", "Prayer", "Say it back to God."),
    ]},
    "lectio": {"name": "Lectio divina", "fields": [
        ("lectio", "Read", "What does the text say? Read it twice, slowly."),
        ("meditatio", "Meditate", "Which word or phrase will not let you go?"),
        ("oratio", "Pray", "What do you want to say back?"),
        ("contemplatio", "Rest", "Sit with it without producing anything."),
    ]},
    "swedish": {"name": "The Swedish method", "fields": [
        ("arrow", "Arrow - what struck me", "The line that went in."),
        ("question", "Question mark - what I do not understand", "Ask it plainly."),
        ("candle", "Candle - what I should do or pass on", "One thing."),
    ]},
    "coma": {"name": "COMA", "fields": [
        ("context", "Context", "What comes before and after?"),
        ("observation", "Observation", "What does it say?"),
        ("meaning", "Meaning", "What did it mean to them?"),
        ("application", "Application", "What does it mean for me?"),
    ]},
    "plain": {"name": "Just write", "fields": [("text", "Note", "")]},
    "question": {"name": "A question", "fields": [("text", "Question", "")]},
    "prayer": {"name": "A prayer", "fields": [("text", "Prayer", "")]},
}


def note_body_text(kind: str, body: dict | str, items: list[dict] | None = None) -> str:
    if isinstance(body, str):
        return body
    if items:
        out = [f"{i['label']}  {i['text']}" for i in items if (i.get("text") or "").strip()]
        tail = ((body or {}).get("summary") or "").strip()
        if tail:
            out.append(tail)
        return "\n".join(out)
    fields = NOTE_KINDS.get(kind, NOTE_KINDS["plain"])["fields"]
    out = []
    for k, title, _ in fields:
        v = (body or {}).get(k, "").strip()
        if v:
            out.append(f"{title}: {v}" if kind not in ("plain", "question", "prayer") else v)
    return "\n".join(out)


def save_note(kind: str, ref: Ref | None, body: dict | str, note_id: int | None = None,
              reading_id: int | None = None, tags: str = "",
              items: list[dict] | None = None) -> int:
    """Save one entry. `items` is the verse-by-verse case: a list of
    {"ref": "Gen.1.27", "text": "..."} which is stored as one note with a row per verse.
    """
    conn = db()
    raw = json.dumps(body, separators=(",", ":")) if isinstance(body, dict) else \
        json.dumps({"text": body[:NOTE_CAP]}, separators=(",", ":"))
    rows: list[tuple[Ref, str]] = []
    for it in (items or []):
        text = (it.get("text") or "").strip()[:NOTE_CAP]
        r = one_ref(str(it.get("ref") or ""))
        if r is not None and text:
            rows.append((r, text))
    rows.sort(key=lambda rt: rt[0].sort_key())
    if rows:                                  # the note is filed at the first verse
        ref = rows[0][0]
        label = refs_label([r for r, _ in rows])
    else:
        label = ref.label() if ref else None
    if note_id:
        conn.execute("UPDATE note SET kind=?, body=?, updated_at=?, tags=?, label=?,"
                     " ref=?, abbr=?, ch=?, v1=?, v2=? WHERE id=?",
                     (kind, raw, now_str(), tags, label,
                      ref.key() if ref else None, ref.abbr if ref else None,
                      ref.ch if ref else None, ref.v1 if ref else None,
                      ref.v2 if ref else None, note_id))
        nid = note_id
    else:
        cur = conn.execute(
            "INSERT INTO note(created_at, updated_at, day, kind, ref, label, abbr, ch,"
            " v1, v2, body, tags, reading_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now_str(), now_str(), today_str(), kind,
             ref.key() if ref else None, label,
             ref.abbr if ref else None, ref.ch if ref else None,
             ref.v1 if ref else None, ref.v2 if ref else None, raw, tags, reading_id))
        nid = int(cur.lastrowid or 0)
        if reading_id:
            conn.execute("UPDATE reading SET note_count = note_count + 1 WHERE id = ?",
                         (reading_id,))
    if items is not None:
        keep = {r["ref"]: r["card_id"] for r in conn.execute(
            "SELECT ref, card_id FROM note_item WHERE note_id = ?", (nid,))}
        conn.execute("DELETE FROM note_item WHERE note_id = ?", (nid,))
        for i, (r, text) in enumerate(rows):
            conn.execute(
                "INSERT INTO note_item(note_id, seq, ref, label, abbr, ch, v1, v2, text,"
                " card_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (nid, i, r.key(), r.label(), r.abbr, r.ch, r.v1, r.v2, text,
                 keep.get(r.key())))
    conn.commit()
    return nid


def note_items(note_id: int) -> list[dict]:
    out = []
    for r in db().execute("SELECT * FROM note_item WHERE note_id = ? ORDER BY seq",
                          (note_id,)):
        try:
            body = json.loads(r["body"] or "{}")
        except Exception:
            body = {}
        out.append({"id": r["id"], "ref": r["ref"], "label": r["label"],
                    "abbr": r["abbr"], "ch": r["ch"], "v1": r["v1"], "v2": r["v2"],
                    "text": r["text"], "card_id": r["card_id"],
                    "kind": (r["kind"] or "verses"), "body": body})
    return out


def compose_comment(kind: str, body: dict) -> str:
    """A comment's fields as the one piece of text everything else reads: search, a
    card, the terminal. One box stays one line; SOAP keeps its labels."""
    spec = NOTE_KINDS.get(kind) or NOTE_KINDS["verses"]
    fields = [f for f in spec["fields"] if f[0] != "summary"] or [("text", "Note", "")]
    if len(fields) == 1:
        return str((body or {}).get(fields[0][0], "")).strip()[:NOTE_CAP]
    out = []
    for key, title, _ in fields:
        v = str((body or {}).get(key, "")).strip()
        if v:
            out.append(f"{title}: {v}")
    return "\n".join(out)[:NOTE_CAP]


def save_comment(ref: Ref, kind: str, body: dict, reading_id: int | None = None,
                 item_id: int | None = None) -> dict:
    """One comment against one verse, saved the moment it is written.

    Comments made in one sitting are gathered into a single entry - so the journal still
    reads as "what I wrote on Tuesday" - but each line keeps its own verse, its own
    method and its own place in the margin.
    """
    conn = db()
    text = compose_comment(kind, body)
    if not text:
        return {"error": "nothing written"}
    if item_id:
        row = conn.execute("SELECT * FROM note_item WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return {"error": "no such comment"}
        conn.execute("UPDATE note_item SET text=?, kind=?, body=?, ref=?, label=?,"
                     " abbr=?, ch=?, v1=?, v2=? WHERE id=?",
                     (text, kind, json.dumps(body, separators=(",", ":")), ref.key(),
                      ref.label(), ref.abbr, ref.ch, ref.v1, ref.v2, item_id))
        nid = int(row["note_id"])
    else:
        note = None
        if reading_id:
            note = conn.execute("SELECT * FROM note WHERE reading_id = ? AND kind = 'verses'"
                                " ORDER BY id DESC LIMIT 1", (reading_id,)).fetchone()
        if note is None:
            note = conn.execute(
                "SELECT * FROM note WHERE day = ? AND kind = 'verses' AND abbr = ?"
                " ORDER BY id DESC LIMIT 1", (today_str(), ref.abbr)).fetchone()
        if note is None:
            cur = conn.execute(
                "INSERT INTO note(created_at, updated_at, day, kind, ref, label, abbr,"
                " ch, v1, v2, body, reading_id) VALUES(?,?,?,'verses',?,?,?,?,?,?,'{}',?)",
                (now_str(), now_str(), today_str(), ref.key(), ref.label(), ref.abbr,
                 ref.ch, ref.v1, ref.v2, reading_id))
            nid = int(cur.lastrowid or 0)
            if reading_id:
                conn.execute("UPDATE reading SET note_count = note_count + 1"
                             " WHERE id = ?", (reading_id,))
        else:
            nid = int(note["id"])
        same = conn.execute("SELECT id FROM note_item WHERE note_id = ? AND ref = ?",
                            (nid, ref.key())).fetchone()
        if same:
            conn.execute("UPDATE note_item SET text=?, kind=?, body=? WHERE id=?",
                         (text, kind, json.dumps(body, separators=(",", ":")),
                          same["id"]))
            item_id = int(same["id"])
        else:
            seq = conn.execute("SELECT COALESCE(MAX(seq) + 1, 0) n FROM note_item"
                               " WHERE note_id = ?", (nid,)).fetchone()["n"]
            cur = conn.execute(
                "INSERT INTO note_item(note_id, seq, ref, label, abbr, ch, v1, v2, text,"
                " kind, body) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (nid, seq, ref.key(), ref.label(), ref.abbr, ref.ch, ref.v1, ref.v2,
                 text, kind, json.dumps(body, separators=(",", ":"))))
            item_id = int(cur.lastrowid or 0)
    items = note_items(nid)
    refs = sorted((r for r in (one_ref(i["ref"]) for i in items) if r),
                  key=lambda r: r.sort_key())
    conn.execute("UPDATE note SET label = ?, updated_at = ? WHERE id = ?",
                 (refs_label(refs), now_str(), nid))
    conn.commit()
    row = conn.execute("SELECT * FROM note WHERE id = ?", (nid,)).fetchone()
    return {"note": note_dict(row), "item_id": item_id}


def delete_comment(item_id: int) -> dict:
    conn = db()
    row = conn.execute("SELECT * FROM note_item WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return {"ok": True}
    nid = int(row["note_id"])
    rid = _reading_of_note(nid)
    conn.execute("DELETE FROM note_item WHERE id = ?", (item_id,))
    left = note_items(nid)
    if not left:
        note = conn.execute("SELECT * FROM note WHERE id = ?", (nid,)).fetchone()
        try:
            body = json.loads((note["body"] if note else "{}") or "{}")
        except Exception:
            body = {}
        if not (body.get("summary") or "").strip():
            conn.execute("DELETE FROM note WHERE id = ?", (nid,))
            conn.commit()
            out = {"ok": True, "note_gone": True}
            if rid:
                out["reading"] = recompute_reading(rid)
            return out
    refs = sorted((r for r in (one_ref(i["ref"]) for i in left) if r),
                  key=lambda r: r.sort_key())
    conn.execute("UPDATE note SET label = ? WHERE id = ?", (refs_label(refs), nid))
    conn.commit()
    return {"ok": True, "reading": recompute_reading(rid) if rid else None}


def _reading_of_note(nid: int) -> int:
    row = db().execute("SELECT reading_id FROM note WHERE id = ?", (nid,)).fetchone()
    return int(row["reading_id"]) if row and row["reading_id"] else 0


def note_dict(row: sqlite3.Row, here_abbr: str = "", here_ch: int | None = None) -> dict:
    try:
        body = json.loads(row["body"] or "{}")
    except Exception:
        body = {"text": row["body"] or ""}
    items = note_items(row["id"])
    # which verses of the chapter being looked at this note actually marks, so the
    # reader can underline those and not a whole range it never touched
    here: list[int] = []
    if here_abbr:
        for it in items:
            if it["abbr"] == here_abbr and it["ch"] == here_ch and it["v1"]:
                here += list(range(it["v1"], (it["v2"] or it["v1"]) + 1))
        if not items and row["abbr"] == here_abbr and row["ch"] == here_ch and row["v1"]:
            here = list(range(row["v1"], (row["v2"] or row["v1"]) + 1))
    return {
        "id": row["id"], "kind": row["kind"], "ref": row["ref"], "label": row["label"],
        "abbr": row["abbr"], "ch": row["ch"], "v1": row["v1"], "v2": row["v2"],
        "day": row["day"], "created_at": row["created_at"], "body": body,
        "items": items, "here": sorted(set(here)),
        "text": note_body_text(row["kind"], body, items), "tags": row["tags"] or "",
        "starred": row["starred"], "card_id": row["card_id"],
        "reading_id": row["reading_id"],
    }


def notes_for(abbr: str = "", ch: int | None = None, limit: int = 200,
              kind: str = "", q: str = "", starred: int = 0) -> list[dict]:
    """Notes, optionally narrowed to one place. A verse-by-verse note filed at Genesis 1
    still turns up on Genesis 3 if that is where one of its verses is."""
    sql = ("SELECT DISTINCT n.* FROM note n"
           " LEFT JOIN note_item i ON i.note_id = n.id WHERE 1=1")
    args: list = []
    if abbr and ch:
        sql += " AND ((n.abbr = ? AND n.ch = ?) OR (i.abbr = ? AND i.ch = ?))"
        args += [abbr, ch, abbr, ch]
    elif abbr:
        sql += " AND (n.abbr = ? OR i.abbr = ?)"
        args += [abbr, abbr]
    if kind:
        sql += " AND n.kind = ?"
        args.append(kind)
    if starred:
        sql += " AND n.starred = 1"
    if q:
        sql += " AND (n.body LIKE ? OR i.text LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY n.created_at DESC LIMIT ?"
    args.append(limit)
    return [note_dict(r, abbr, ch) for r in db().execute(sql, args)]


HIGHLIGHT_COLORS = ("yellow", "green", "blue", "pink", "orange", "violet")


def save_highlight(ref: Ref, color: str = "yellow", snippet: str = "",
                   note: str = "") -> int:
    conn = db()
    # the same verses in the same colour twice is a double-click, not two highlights
    same = conn.execute(
        "SELECT id FROM highlight WHERE abbr=? AND ch=? AND IFNULL(v1,0)=? AND"
        " IFNULL(v2,0)=? AND color=?",
        (ref.abbr, ref.ch, ref.v1 or 0, (ref.v2 or ref.v1) or 0, color)).fetchone()
    if same:
        if note:
            conn.execute("UPDATE highlight SET note=? WHERE id=?", (note[:2000], same["id"]))
            conn.commit()
        return int(same["id"])
    cur = conn.execute(
        "INSERT INTO highlight(created_at, abbr, ch, v1, v2, color, snippet, ref, label,"
        " note) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (now_str(), ref.abbr, ref.ch, ref.v1, ref.v2,
         color if color in HIGHLIGHT_COLORS else "yellow",
         snippet[:600], ref.key(), ref.label(), note[:2000]))
    conn.commit()
    return int(cur.lastrowid or 0)


def highlights_for(abbr: str = "", ch: int | None = None, color: str = "",
                   limit: int = 500) -> list[dict]:
    sql = "SELECT * FROM highlight WHERE 1=1"
    args: list = []
    if abbr:
        sql += " AND abbr = ?"
        args.append(abbr)
    if ch:
        sql += " AND ch = ?"
        args.append(ch)
    if color:
        sql += " AND color = ?"
        args.append(color)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    return [{"id": r["id"], "abbr": r["abbr"], "ch": r["ch"], "v1": r["v1"],
             "v2": r["v2"], "color": r["color"], "snippet": r["snippet"],
             "label": r["label"], "ref": r["ref"], "note": r["note"],
             "day": (r["created_at"] or "")[:10]} for r in db().execute(sql, args)]


# ============================================ the thirty seconds before you read
# Students who spent a session recalling a passage remembered 61% of it a week later;
# students who spent the same time reading it again remembered 40%. Retrieval is the
# cheapest thing in this app and the most valuable, so it goes first, it takes half a
# minute, and it is never compulsory.
def recall_prompt() -> dict:
    """What to ask about today: the last thing you read that has not been asked about."""
    conn = db()
    floor = (date.today() - timedelta(days=RECALL_LOOKBACK)).isoformat()
    row = conn.execute(
        "SELECT r.* FROM reading r LEFT JOIN recall c ON c.reading_id = r.id"
        " WHERE r.finished = 1 AND r.day < ? AND r.day >= ? AND c.id IS NULL"
        " ORDER BY r.day DESC, r.id DESC LIMIT 1",
        (today_str(), floor)).fetchone()
    if row is None:                      # nothing fresh; reach further back on purpose
        row = conn.execute(
            "SELECT r.* FROM reading r WHERE r.finished = 1 AND r.day < ?"
            " ORDER BY RANDOM() LIMIT 1", (today_str(),)).fetchone()
    if row is None:
        return {}
    age = (date.today() - d(row["day"])).days
    refs = refs_from_json(row["refs"])
    notes = [note_dict(n) for n in conn.execute(
        "SELECT * FROM note WHERE reading_id = ? ORDER BY id", (row["id"],))]
    return {
        "reading_id": row["id"], "label": row["label"], "day": row["day"],
        "age_days": age,
        "when": "yesterday" if age == 1 else f"{age} days ago",
        "prompt": f"What do you remember of {row['label']}?",
        "refs": [r.key() for r in refs],
        "notes": notes,
        # the opening words, kept back until you have answered - the reveal. Straight
        # from the cache: this is a passage you have read, and Today must render with
        # no network at all.
        "first_lines": (" ".join((passage_text(refs[0], numbers=False, fetch=False) or "")
                                 .split()[:45]) if refs else ""),
    }


def save_recall(reading_id: int, answer: str, grade: int, seconds: int = 0) -> int:
    conn = db()
    row = conn.execute("SELECT * FROM reading WHERE id = ?", (reading_id,)).fetchone()
    if not row:
        return 0
    age = (date.today() - d(row["day"])).days
    cur = conn.execute(
        "INSERT INTO recall(at, day, ref, label, reading_id, prompt, answer, grade,"
        " seconds, age_days) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (now_str(), today_str(), row["refs"], row["label"], reading_id,
         f"What do you remember of {row['label']}?", answer[:NOTE_CAP],
         int(_clamp(grade, 0, 2)), seconds, age))
    conn.execute("UPDATE reading SET recalled = 1 WHERE id = ?", (reading_id,))
    conn.commit()
    return int(cur.lastrowid or 0)


def recall_history(limit: int = 60) -> list[dict]:
    return [{"id": r["id"], "day": r["day"], "label": r["label"], "grade": r["grade"],
             "age_days": r["age_days"], "answer": r["answer"]}
            for r in db().execute("SELECT * FROM recall ORDER BY at DESC LIMIT ?",
                                  (limit,))]


# ============================================ memorising something long, the slow way
# Andrew Davis's method, which is the only one that reliably gets people through whole
# books: say the new verse ten times looking at it, ten times without, then add it to
# everything you already have and say the lot. When the book is done you stop adding
# and say the whole thing once a day for a hundred days. Fifteen minutes, every day,
# for months - so the app's job is to hold the count, not to hurry you.
def _verse_refs(refs: list[Ref]) -> list[Ref]:
    """A chapter becomes one Ref per verse, because that is the unit you add."""
    out: list[Ref] = []
    for r in refs:
        if r.v1 is None:
            n = verses_in(r.abbr, r.ch)
            out += [Ref(r.abbr, r.ch, v) for v in range(1, n + 1)]
        else:
            out += [Ref(r.abbr, r.ch, v) for v in range(r.v1, (r.v2 or r.v1) + 1)]
    return out


def create_project(name: str, refs: list[Ref], target_days: int = 100) -> int:
    verses = _verse_refs(refs)
    if not verses:
        return 0
    conn = db()
    cur = conn.execute(
        "INSERT INTO project(created_at, name, refs, abbr, ch1, ch2, phase,"
        " target_days) VALUES(?,?,?,?,?,?,'learning',?)",
        (now_str(), name or refs_label(refs), refs_to_json(verses),
         verses[0].abbr, verses[0].ch, verses[-1].ch, max(1, target_days)))
    conn.commit()
    return int(cur.lastrowid or 0)


def project_today(pid: int) -> dict:
    conn = db()
    p = conn.execute("SELECT * FROM project WHERE id = ?", (pid,)).fetchone()
    if not p:
        return {}
    verses = refs_from_json(p["refs"])
    total = len(verses)
    learned = min(int(p["learned"] or 0), total)
    done_today = conn.execute("SELECT 1 FROM project_log WHERE project_id=? AND day=?",
                              (pid, today_str())).fetchone() is not None
    have = verses[:learned]
    nxt = verses[learned] if learned < total else None
    words = sum(v.word_count() for v in have)
    return {
        "id": p["id"], "name": p["name"], "phase": p["phase"],
        "learned": learned, "total": total,
        "range": refs_label(verses) if total else "",
        "next": {"ref": nxt.key(), "label": nxt.label(),
                 "text": passage_text(nxt, numbers=False)} if nxt else None,
        "known": [{"ref": v.key(), "label": v.label(),
                   "text": passage_text(v, numbers=False)} for v in have],
        "recite_minutes": round(words / 130, 1),        # aloud is slower than silent
        "review_day": p["review_day"], "target_days": p["target_days"],
        "done_today": done_today, "last_on": p["last_on"], "active": p["active"],
        "days_logged": conn.execute("SELECT COUNT(*) n FROM project_log WHERE project_id=?",
                                    (pid,)).fetchone()["n"],
    }


def project_advance(pid: int, minutes: float = 0.0, added: int = 1,
                    note: str = "") -> dict:
    conn = db()
    p = conn.execute("SELECT * FROM project WHERE id = ?", (pid,)).fetchone()
    if not p:
        return {}
    total = len(json.loads(p["refs"] or "[]"))
    learned = int(p["learned"] or 0)
    phase = p["phase"]
    already = conn.execute("SELECT 1 FROM project_log WHERE project_id=? AND day=?",
                           (pid, today_str())).fetchone() is not None
    review_day = int(p["review_day"] or 0)
    if phase == "learning":
        learned = min(total, learned + max(0, int(added)))
        if learned >= total:
            phase, review_day = "review", 0
    elif not already:
        review_day += 1
        if review_day >= int(p["target_days"] or 100):
            phase = "kept"
    conn.execute("UPDATE project SET learned=?, phase=?, review_day=?, last_on=?"
                 " WHERE id=?", (learned, phase, review_day, today_str(), pid))
    conn.execute("INSERT INTO project_log(project_id, day, at, minutes, added, phase,"
                 " note) VALUES(?,?,?,?,?,?,?)",
                 (pid, today_str(), now_str(), minutes, added, phase, note[:2000]))
    conn.commit()
    return project_today(pid)


def projects(active_only: bool = True) -> list[dict]:
    sql = "SELECT id FROM project"
    if active_only:
        sql += " WHERE active = 1"
    return [project_today(r["id"]) for r in db().execute(sql + " ORDER BY id DESC")]


# =========================================================================== search
_SEARCH_ROW = re.compile(
    r"<tr>\s*<td>\s*<a[^>]*>(.*?)</a>\s*</td>\s*<td>(.*?)</td>", re.S | re.I)


def search_bible(q: str, limit: int = 60) -> list[dict]:
    """Tyndale's own search over the whole NLT, whether or not it is cached here."""
    q = (q or "").strip()
    if len(q) < 2:
        return []
    html = api_get("search", {"text": q, "version": setting("version") or "NLT"},
                   setting("api_key"))
    out: list[dict] = []
    for m in _SEARCH_ROW.finditer(html):
        raw = _plain(m.group(1))
        ref = one_ref(raw)
        snippet = re.sub(r'<span class="highlight">(.*?)</span>', r"<mark>\1</mark>",
                         m.group(2), flags=re.S | re.I)
        out.append({"ref": ref.key() if ref else raw,
                    "label": ref.label() if ref else raw,
                    "snippet": _clean_inline(snippet.replace("<mark>", "\x01")
                                             .replace("</mark>", "\x02"))
                    .replace("\x01", "<mark>").replace("\x02", "</mark>")})
        if len(out) >= limit:
            break
    total = 0
    tm = re.search(r'<span class="count">\s*([\d,]+)\s*result', html, re.I)
    if tm:
        total = int(tm.group(1).replace(",", ""))
    for o in out:
        o["total"] = total
    return out


def search_local(q: str, limit: int = 40) -> dict:
    """Everything of yours that mentions it: your notes, your highlights, your cards,
    and the verses already cached on this machine."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"verses": [], "notes": [], "highlights": [], "cards": []}
    like = f"%{q}%"
    conn = db()
    verses = [{"abbr": r["abbr"], "ch": r["ch"], "vn": r["vn"], "text": r["text"],
               "label": Ref(r["abbr"], r["ch"], r["vn"]).label(),
               "ref": Ref(r["abbr"], r["ch"], r["vn"]).key()}
              for r in conn.execute(
                  "SELECT * FROM verse WHERE version = ? AND text LIKE ? LIMIT ?",
                  (setting("version"), like, limit))]
    return {
        "verses": verses,
        "notes": notes_for(q=q, limit=limit),
        "highlights": [h for h in highlights_for(limit=400)
                       if q.lower() in (h["snippet"] or "").lower()
                       or q.lower() in (h["note"] or "").lower()][:limit],
        "cards": [card_dict(r) for r in conn.execute(
            "SELECT * FROM card WHERE front LIKE ? OR back LIKE ? LIMIT ?",
            (like, like, limit))],
    }


# ======================================================================== progress
# "Clearly know what I read and when" is the whole point of this section: a map of all
# 1,189 chapters, a year of days, the clock you actually read at, and the numbers that
# say whether the habit is holding.
def coverage() -> dict:
    conn = db()
    # only sittings that counted put a chapter on the map, which is the same rule the
    # week uses. A look is in the log; it is not somewhere you have been.
    rows = conn.execute(
        "SELECT rc.abbr abbr, rc.ch ch, COUNT(*) n, MAX(rc.day) last,"
        " SUM(CASE WHEN rc.v1 IS NULL THEN 1 ELSE 0 END) whole"
        " FROM reading_chapter rc JOIN reading r ON r.id = rc.reading_id"
        " WHERE r.engaged = 1 GROUP BY rc.abbr, rc.ch").fetchall()
    seen: dict[str, dict[int, dict]] = {}
    for r in rows:
        seen.setdefault(r["abbr"], {})[r["ch"]] = {
            "n": r["n"], "last": r["last"], "whole": bool(r["whole"])}
    books = []
    read_ch = 0
    for abbr, api, title, testament, genre, nch in BOOKS:
        got = seen.get(abbr, {})
        whole = sum(1 for c in got.values() if c["whole"])
        read_ch += whole
        books.append({
            "abbr": abbr, "title": title, "testament": testament, "genre": genre,
            "chapters": nch, "read": whole, "touched": len(got),
            "complete": whole >= nch,
            "last": max((c["last"] for c in got.values()), default=None),
            "times": sum(c["n"] for c in got.values()),
            "cells": [got.get(c, {}).get("n", 0) for c in range(1, nch + 1)],
            "partial": [1 if (c in got and not got[c]["whole"]) else 0
                        for c in range(1, nch + 1)],
        })
    return {"books": books, "chapters_read": read_ch, "chapters_total": TOTAL_CHAPTERS,
            "percent": round(100 * read_ch / TOTAL_CHAPTERS, 1),
            "books_complete": sum(1 for b in books if b["complete"])}


def chapter_days() -> dict[str, list[dict]]:
    """When each chapter was read, newest first. What the map's cells answer when you
    click one - "when did I read this?" is a better question than "open it again"."""
    out: dict[str, list[dict]] = {}
    for r in db().execute(
            "SELECT rc.abbr abbr, rc.ch ch, r.day day, r.seconds secs, r.id rid,"
            " r.started_at started FROM reading_chapter rc"
            " JOIN reading r ON r.id = rc.reading_id"
            " WHERE r.engaged = 1 ORDER BY r.day DESC, r.id DESC"):
        out.setdefault(f"{r['abbr']}.{r['ch']}", []).append(
            {"day": r["day"], "minutes": round((r["secs"] or 0) / 60),
             "at": (r["started"] or "")[11:16], "id": r["rid"]})
    return out


def calendar_year(year: int | None = None) -> dict:
    """One calendar year, day by day - the year you are in, not the last 365 days."""
    year = year or date.today().year
    first, last = date(year, 1, 1), date(year, 12, 31)
    rows = db().execute(
        "SELECT day, SUM(seconds) secs, COUNT(*) n, MAX(engaged) eng, SUM(verses) v"
        " FROM reading WHERE finished = 1 AND day >= ? AND day <= ? GROUP BY day",
        (first.isoformat(), last.isoformat())).fetchall()
    by = {r["day"]: r for r in rows}
    days, read, light, minutes, verses = [], 0, 0, 0, 0
    for i in range((last - first).days + 1):
        dd = first + timedelta(days=i)
        iso = dd.isoformat()
        r = by.get(iso)
        m = round((r["secs"] or 0) / 60) if r else 0
        eng = bool(r and r["eng"])
        if eng:
            read += 1
        elif r:
            light += 1
        minutes += m
        verses += (r["v"] or 0) if r else 0
        days.append({"day": iso, "n": dd.day, "month": dd.month, "wd": dd.weekday(),
                     "minutes": m, "read": eng, "light": bool(r) and not eng,
                     "future": dd > date.today(), "today": dd == date.today()})
    elapsed = sum(1 for d0 in days if not d0["future"])
    target = int(setting("target_days") or TARGET_DAYS_PER_WEEK)
    years = [r["y"] for r in db().execute(
        "SELECT DISTINCT substr(day, 1, 4) y FROM reading WHERE finished = 1"
        " ORDER BY y DESC")]
    return {"year": year, "days": days, "read": read, "light": light,
            "minutes": minutes, "verses": verses, "elapsed": elapsed,
            "per_week": round(read / elapsed * 7, 1) if elapsed else 0.0,
            "target": target, "on_target": read >= round(target * elapsed / 7),
            "years": [int(y) for y in years if y and y.isdigit()]}


def calendar(days: int = 371) -> list[dict]:
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = db().execute(
        "SELECT day, SUM(seconds) secs, COUNT(*) n, MAX(engaged) eng,"
        " SUM(verses) verses FROM reading WHERE finished = 1 AND day >= ?"
        " GROUP BY day", (since,)).fetchall()
    by_day = {r["day"]: r for r in rows}
    out = []
    for i in range(days):
        dd = (date.today() - timedelta(days=days - 1 - i))
        s = dd.isoformat()
        r = by_day.get(s)
        out.append({"day": s, "dow": dd.weekday(),
                    "minutes": round((r["secs"] or 0) / 60) if r else 0,
                    "readings": r["n"] if r else 0,
                    "engaged": bool(r["eng"]) if r else False,
                    "verses": r["verses"] if r else 0})
    return out


MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")


def _bucket_key(day: str, grain: str) -> tuple[str, str, str, str]:
    """(key, label, first day, last day) for the day/week/month a reading falls in."""
    dd = d(day)
    if grain == "week":
        start = dd - timedelta(days=dd.weekday())
        end = start + timedelta(days=6)
        same_month = start.month == end.month
        label = (f"{start.day}-{end.day} {MONTHS[end.month - 1]}" if same_month
                 else f"{start.day} {MONTHS[start.month - 1][:3]} - "
                      f"{end.day} {MONTHS[end.month - 1][:3]}")
        if end.year != date.today().year:
            label += f" {end.year}"
        return (start.isoformat(), label, start.isoformat(), end.isoformat())
    if grain == "month":
        start = dd.replace(day=1)
        nxt = (start + timedelta(days=31)).replace(day=1)
        end = nxt - timedelta(days=1)
        label = MONTHS[start.month - 1] + (
            f" {start.year}" if start.year != date.today().year else "")
        return (start.strftime("%Y-%m"), label, start.isoformat(), end.isoformat())
    return (day, day, day, day)


def history(grain: str = "day", limit: int = 24) -> dict:
    settle_readings()
    """What was read, gathered by day, by week or by month.

    A day is the sitting. A week is the unit the target is set in. A month is the one
    where you can see a book finish. Same rows, three altitudes.
    """
    grain = grain if grain in ("day", "week", "month") else "day"
    conn = db()
    readings = [reading_dict(r) for r in conn.execute(
        "SELECT * FROM reading WHERE finished = 1 ORDER BY day DESC, id DESC")]
    places: dict[int, list[sqlite3.Row]] = {}
    for c in conn.execute("SELECT * FROM reading_chapter"):
        places.setdefault(c["reading_id"], []).append(c)
    per_day_notes: dict[str, int] = {r["day"]: r["n"] for r in conn.execute(
        "SELECT day, COUNT(*) n FROM note GROUP BY day")}
    per_day_cards: dict[str, int] = {r["day"]: r["n"] for r in conn.execute(
        "SELECT substr(created_at,1,10) day, COUNT(*) n FROM card"
        " GROUP BY substr(created_at,1,10)")}
    per_day_recalls: dict[str, int] = {r["day"]: r["n"] for r in conn.execute(
        "SELECT day, COUNT(*) n FROM recall GROUP BY day")}
    per_day_reviews: dict[str, int] = {r["day"]: r["n"] for r in conn.execute(
        "SELECT day, COUNT(*) n FROM review GROUP BY day")}

    order: list[str] = []
    buckets: dict[str, dict] = {}
    for r in readings:
        key, label, first, last = _bucket_key(r["day"], grain)
        b = buckets.get(key)
        if b is None:
            if len(order) >= limit:
                continue
            order.append(key)
            b = buckets[key] = {
                "key": key, "label": label, "first": first, "last": last,
                "grain": grain, "readings": [], "minutes": 0, "verses": 0, "words": 0,
                "chapters": [], "books": [], "days_read": [], "days_light": [],
                "notes": 0, "cards": 0, "recalls": 0, "reviews": 0,
            }
        b["readings"].append(r)
        b["minutes"] += round((r["seconds"] or 0) / 60)
        b["verses"] += r["verses"] or 0
        b["words"] += r["words"] or 0
        for c in places.get(r["id"], []):
            tag = f"{c['abbr']}.{c['ch']}"
            if tag not in b["chapters"]:
                b["chapters"].append(tag)
            if c["abbr"] not in b["books"]:
                b["books"].append(c["abbr"])
        if r["engaged"]:
            if r["day"] not in b["days_read"]:
                b["days_read"].append(r["day"])
        elif r["day"] not in b["days_light"]:
            b["days_light"].append(r["day"])

    target = int(setting("target_days") or TARGET_DAYS_PER_WEEK)
    out: list[dict] = []
    for key in order:
        b = buckets[key]
        first, last = d(b["first"]), d(b["last"])
        span = (last - first).days + 1
        seen = set(b["days_read"])
        light = set(b["days_light"]) - seen
        days = []
        for i in range(span):
            dd = first + timedelta(days=i)
            iso = dd.isoformat()
            mins = round(sum(r["seconds"] for r in b["readings"] if r["day"] == iso) / 60)
            days.append({"day": iso, "dow": dd.strftime("%a")[0], "n": dd.day,
                         "read": iso in seen, "light": iso in light,
                         "minutes": mins, "future": dd > date.today()})
        b["days"] = days
        b["days_possible"] = span
        b["elapsed"] = sum(1 for x in days if not x["future"])
        b["read_count"] = len(seen)
        b["light_count"] = len(light)
        # a month that has not finished is judged on the days that have happened
        b["target"] = target if grain == "week" else (
            max(1, round(target * b["elapsed"] / 7)) if grain == "month" else 1)
        b["met"] = b["read_count"] >= b["target"]
        b["notes"] = sum(per_day_notes.get(x["day"], 0) for x in days)
        b["cards"] = sum(per_day_cards.get(x["day"], 0) for x in days)
        b["recalls"] = sum(per_day_recalls.get(x["day"], 0) for x in days)
        b["reviews"] = sum(per_day_reviews.get(x["day"], 0) for x in days)
        b["books"] = sorted(b["books"], key=lambda a: BOOK_BY_ABBR.get(a, 99))
        b["book_titles"] = [book_title(a) for a in b["books"]]
        b["chapter_count"] = len(b["chapters"])
        # what was read, said once: "Genesis 1-24; Psalm 23"
        refs = sorted((one_ref(t.replace(".", " ", 1)) for t in b["chapters"]),
                      key=lambda r: r.sort_key() if r else (99, 0, 0))
        b["covered"] = refs_label([r for r in refs if r])
        out.append(b)
    return {"grain": grain, "buckets": out, "target": target,
            "totals": {"readings": len(readings),
                       "minutes": round(sum(r["seconds"] for r in readings) / 60)}}


def stats() -> dict:
    settle_readings()
    conn = db()
    tot = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(seconds),0) secs, COALESCE(SUM(verses),0) v,"
        " COALESCE(SUM(words),0) w, MIN(day) first FROM reading WHERE finished=1"
    ).fetchone()
    cards = conn.execute(
        "SELECT COUNT(*) n, SUM(CASE WHEN state>0 THEN 1 ELSE 0 END) started,"
        " SUM(CASE WHEN due <= ? AND state>0 THEN 1 ELSE 0 END) due,"
        " COALESCE(AVG(CASE WHEN state>0 THEN stability END),0) avg_s"
        " FROM card WHERE suspended = 0", (today_str(),)).fetchone()
    revs = conn.execute("SELECT COUNT(*) n FROM review").fetchone()
    # the recall rate only counts cards you had seen before: getting a brand new verse
    # "wrong" is not forgetting
    seen = conn.execute(
        "SELECT COUNT(*) n, SUM(CASE WHEN rating>1 THEN 1 ELSE 0 END) ok"
        " FROM review WHERE state > 0").fetchone()
    rec = conn.execute("SELECT COUNT(*) n, COALESCE(AVG(grade),0) g FROM recall"
                       ).fetchone()
    cov = coverage()
    wk = week_view()
    st = streak()
    return {
        "readings": tot["n"], "minutes": round((tot["secs"] or 0) / 60),
        "verses": tot["v"], "words": tot["w"], "first_day": tot["first"],
        "days_read": st["days_total"],
        "chapters_read": cov["chapters_read"], "chapters_total": cov["chapters_total"],
        "percent_bible": cov["percent"], "books_complete": cov["books_complete"],
        "cards": cards["n"], "cards_started": cards["started"] or 0,
        "cards_due": cards["due"] or 0,
        "avg_stability_days": round(cards["avg_s"] or 0, 1),
        "reviews": revs["n"],
        "recall_rate": round(100 * (seen["ok"] or 0) / seen["n"]) if seen["n"] else None,
        "recalls": rec["n"], "recall_grade": round(rec["g"], 2) if rec["n"] else None,
        "notes": conn.execute("SELECT COUNT(*) n FROM note").fetchone()["n"],
        "highlights": conn.execute("SELECT COUNT(*) n FROM highlight").fetchone()["n"],
        "week": wk, "month": month_view(), "streak": st, "read_map": read_map(), "clock": clock_habit(),
        "weeks_on_target": weeks_on_target(),
        "cached_chapters": conn.execute(
            "SELECT COUNT(*) n FROM passage WHERE version = ?",
            (setting("version"),)).fetchone()["n"],
    }


def weeks_on_target() -> dict:
    """How many of the last twelve weeks hit four days. The number that matters most,
    because it is the one the research attached the difference to."""
    target = int(setting("target_days") or TARGET_DAYS_PER_WEEK)
    got = set(engaged_days((date.today() - timedelta(days=90)).isoformat()))
    weeks = []
    for w in range(12):
        end = date.today() - timedelta(days=7 * w)
        start = end - timedelta(days=6)
        n = sum(1 for i in range(7)
                if (start + timedelta(days=i)).isoformat() in got)
        weeks.append({"start": start.isoformat(), "days": n, "met": n >= target})
    weeks.reverse()
    return {"weeks": weeks, "met": sum(1 for w in weeks if w["met"]), "target": target}


# ========================================================================= today
PASSAGE_CAP = 25                 # one request never turns into fifty calls to Tyndale


def passages_payload(refs: list[Ref], with_marks: bool = True) -> list[dict]:
    """Each ref as text ready to render, with your own marks on it."""
    out: list[dict] = []
    for r in refs[:PASSAGE_CAP]:
        try:
            p = passage(r)
        except ApiError as e:
            out.append({"ref": r.key(), "label": r.label(), "error": str(e),
                        "blocks": [], "verses": {},
                        "cached": have_cached(r)})
            continue
        if not p:
            out.append({"ref": r.key(), "label": r.label(),
                        "error": "not here yet", "blocks": [], "verses": {}})
            continue
        if with_marks:
            p["highlights"] = highlights_for(r.abbr, r.ch)
            p["notes"] = notes_for(r.abbr, r.ch, limit=40)
            p["cards"] = [card_dict(x) for x in db().execute(
                "SELECT * FROM card WHERE abbr=? AND ch=?", (r.abbr, r.ch))]
        p["minutes"] = round(p["words"] / WORDS_PER_MINUTE, 1)
        out.append(p)
    return out


def today_payload() -> dict:
    settle_readings()
    conn = db()
    p = active_plan()
    plan = plan_progress(int(p["id"])) if p else {}
    item, item_error = None, ""
    if p:
        try:
            item = plan_item_for_today(int(p["id"]))
        except ApiError as e:      # only the chronological plan can get here
            item_error = str(e)
    today_rows = [reading_dict(r) for r in conn.execute(
        "SELECT * FROM reading WHERE day = ? ORDER BY id", (today_str(),))]
    st = streak()
    wk = week_view()
    due = due_cards()
    item_refs = refs_from_json(item["refs"]) if item else []
    ahead = []
    if p:
        for row in upcoming_items(int(p["id"]), 4)[1:]:
            ahead.append({"seq": row["seq"], "label": row["label"],
                          "minutes": round((row["words"] or 0) / WORDS_PER_MINUTE, 1)})
    est = estimated_seconds(item_refs) if item_refs else 0
    plan_done_today = conn.execute(
        "SELECT COUNT(*) n FROM plan_item WHERE plan_id = ? AND done_on = ?",
        (int(p["id"]), today_str())).fetchone()["n"] if p else 0
    rescue = None
    if st["warn"] or (not st["read_today"] and est > RESCUE_MINUTES * 90):
        rr = rescue_ref()
        rescue = {"ref": rr.key(), "label": rr.label(),
                  "minutes": round(rr.minutes(), 1)}
    return {
        "day": today_str(),
        "weekday": date.today().strftime("%A"),
        "date_long": date.today().strftime("%-d %B %Y") if sys.platform != "win32"
        else date.today().strftime("%d %B %Y"),
        "plan": plan,
        "item": ({"seq": item["seq"], "label": item["label"],
                  "refs": [r.key() for r in item_refs],
                  "verses": item["verses"], "words": item["words"],
                  "minutes": round(est / 60, 1),
                  "cached": all(have_cached(r) for r in item_refs)} if item else None),
        "ahead": ahead,
        "item_error": item_error,
        "readings": today_rows,
        "read_today": st["read_today"],
        "unconfirmed": unconfirmed_readings(),
        "plan_done_today": plan_done_today,
        "minutes_today": round(sum(r["seconds"] for r in today_rows) / 60),
        "week": wk, "month": month_view(), "streak": st, "read_map": read_map(),
        "recall": recall_prompt() if setting("recall_on") == "1" else {},
        "due_count": len(due),
        "projects": projects(True),
        "rescue": rescue,
        "target_days": int(setting("target_days") or 4),
    }


# ======================================================================== the API
def _int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _refs_arg(raw) -> list[Ref]:
    """A list of keys, or one string of them, or a written reference. All three."""
    items = raw if isinstance(raw, list) else re.split(r"[;,]", str(raw or ""))
    out: list[Ref] = []
    for x in items:
        x = str(x).strip()
        if x:
            out += refs_from_json(json.dumps([x]))
    return out


def api(method: str, path: str, q: dict, body: dict) -> dict:
    """Every route in one place. Returns something json.dumps can eat."""
    g = q.get
    b = body.get

    if path == "/api/boot":
        return {
            "settings": settings_all(),
            "books": [{"abbr": a, "title": t, "testament": tt, "genre": gg,
                       "chapters": n, "verses": list(VERSE_COUNTS.get(a, ())),
                       "minutes": [round(words_in(a, c) / WORDS_PER_MINUTE, 1)
                                   for c in range(1, n + 1)]}
                      for a, api_ref, t, tt, gg, n in BOOKS],
            "genres": GENRE_TITLES,
            "order": BOOK_BY_ABBR,
            "note_kinds": NOTE_KINDS,
            "colors": list(HIGHLIGHT_COLORS),
            "templates": PLAN_TEMPLATES,
            "book_sets": {k: {"title": v[0], "books": v[1], "chapters":
                              sum(chapters_in(x) for x in v[1])}
                          for k, v in BOOK_SETS.items()},
            "versions": list(VERSIONS),
            "totals": {"chapters": TOTAL_CHAPTERS, "verses": TOTAL_VERSES,
                       "words": TOTAL_WORDS},
            "has_key": bool(setting("api_key")),
            "port": DEFAULT_PORT,
            "started_at": datetime.fromtimestamp(STARTED_AT).isoformat(timespec="seconds"),
            "stale": _code_is_newer(),
        }

    if path == "/api/today":
        return today_payload()

    if path == "/api/parse":
        # the front of the app asks this before it searches: is what you typed a
        # reference? The alias table here knows "psalm 23", "ii cor 5" and "1 jn 4.8".
        got = parse_ref(str(g("ref") or ""))
        return {"refs": [r.key() for r in got[:60]], "label": refs_label(got),
                "first": got[0].key() if got else None,
                "abbr": got[0].abbr if got else None,
                "ch": got[0].ch if got else None,
                "v": got[0].v1 if got else None}

    if path == "/api/passages":
        refs = _refs_arg(g("refs") or g("ref") or "")
        return {"passages": passages_payload(refs),
                "label": refs_label(refs[:PASSAGE_CAP]),
                "verses": sum(r.verse_count() for r in refs[:PASSAGE_CAP]),
                "estimated_seconds": estimated_seconds(refs[:PASSAGE_CAP])}

    if path == "/api/chapter":
        abbr = str(g("abbr") or "Gen")
        ch = _int(g("ch"), 1)
        nch = chapters_in(abbr) or 1
        ch = max(1, min(ch, nch))
        return {"passages": passages_payload([Ref(abbr, ch)]),
                "prev": {"abbr": abbr, "ch": ch - 1} if ch > 1 else None,
                "next": {"abbr": abbr, "ch": ch + 1} if ch < nch else None}

    if path == "/api/reading/start" and method == "POST":
        refs = _refs_arg(b("refs") or "")
        if not refs:
            return {"error": "nothing to read"}
        rid = start_reading(refs, _int(b("plan_id")) or None,
                            b("plan_seq") if b("plan_seq") is not None else None,
                            str(b("mode") or "free"))
        prefetch(refs)
        return {"reading_id": rid, "passages": passages_payload(refs),
                "estimated_seconds": estimated_seconds(refs)}

    if path == "/api/reading/touch" and method == "POST":
        touch_reading(_int(b("id")), b("seconds"), b("scroll"))
        return {"ok": True}

    if path == "/api/reading/finish" and method == "POST":
        return finish_reading(_int(b("id")), b("seconds"), b("scroll")) or {"error": "gone"}

    if path == "/api/readings":
        return {"readings": recent_readings(_int(g("limit"), 60), str(g("day") or ""))}

    if path == "/api/reading/confirm" and method == "POST":
        # the record is yours to correct, either way, at any time
        rid = _int(b("id"))
        conn = db()
        if b("yes"):
            conn.execute("UPDATE reading SET confirmed = 1 WHERE id = ?", (rid,))
            conn.commit()
            row = conn.execute("SELECT * FROM reading WHERE id = ?", (rid,)).fetchone()
            if row and not row["finished"]:
                return finish_reading(rid, confirm=True) or {"error": "gone"}
            return {"ok": True, "reading": recompute_reading(rid)}
        conn.execute("UPDATE reading SET confirmed = -1, engaged = 0, finished = 1"
                     " WHERE id = ?", (rid,))
        conn.execute("UPDATE plan_item SET done_on = NULL, reading_id = NULL"
                     " WHERE reading_id = ?", (rid,))
        conn.commit()
        return {"ok": True, "reading": reading_dict(
            conn.execute("SELECT * FROM reading WHERE id = ?", (rid,)).fetchone())}

    if path == "/api/reading/delete" and method == "POST":
        conn = db()
        rid = _int(b("id"))
        conn.execute("DELETE FROM reading_chapter WHERE reading_id = ?", (rid,))
        conn.execute("UPDATE plan_item SET done_on = NULL, reading_id = NULL"
                     " WHERE reading_id = ?", (rid,))
        conn.execute("UPDATE note SET reading_id = NULL WHERE reading_id = ?", (rid,))
        conn.execute("DELETE FROM reading WHERE id = ?", (rid,))
        conn.commit()
        return {"ok": True}

    if path == "/api/recall" and method == "GET":
        return recall_prompt()

    if path == "/api/recall" and method == "POST":
        rid = save_recall(_int(b("reading_id")), str(b("answer") or ""),
                          _int(b("grade")), _int(b("seconds")))
        return {"id": rid, "history": recall_history(12)}

    if path == "/api/note" and method == "POST":
        ref = one_ref(str(b("ref") or "")) if b("ref") else None
        items = b("items") if isinstance(b("items"), list) else None
        nid = save_note(str(b("kind") or "plain"), ref, b("body") or {},
                        _int(b("note_id")) or None, _int(b("reading_id")) or None,
                        str(b("tags") or ""), items)
        row = db().execute("SELECT * FROM note WHERE id = ?", (nid,)).fetchone()
        return {"id": nid, "note": note_dict(row) if row else None}

    if path == "/api/comment" and method == "POST":
        ref = one_ref(str(b("ref") or ""))
        if ref is None:
            return {"error": "no reference"}
        return save_comment(ref, str(b("kind") or "verses"), dict(b("body") or {}),
                            _int(b("reading_id")) or None, _int(b("item_id")) or None)

    if path == "/api/comment/delete" and method == "POST":
        return delete_comment(_int(b("item_id")))

    if path == "/api/notes":
        return {"notes": notes_for(str(g("abbr") or ""), _int(g("ch")) or None,
                                   _int(g("limit"), 200), str(g("kind") or ""),
                                   str(g("q") or ""), _int(g("starred")))}

    if path == "/api/note/delete" and method == "POST":
        nid = _int(b("id"))
        rid = _reading_of_note(nid)
        db().execute("DELETE FROM note_item WHERE note_id = ?", (nid,))
        db().execute("DELETE FROM note WHERE id = ?", (nid,))
        db().commit()
        return {"ok": True, "reading": recompute_reading(rid) if rid else None}

    if path == "/api/note/star" and method == "POST":
        db().execute("UPDATE note SET starred = ? WHERE id = ?",
                     (1 if b("starred") else 0, _int(b("id"))))
        db().commit()
        return {"ok": True}

    if path == "/api/note/keep" and method == "POST":
        # a whole note, or one verse of a verse-by-verse note
        if b("item_id"):
            it = db().execute("SELECT * FROM note_item WHERE id = ?",
                              (_int(b("item_id")),)).fetchone()
            if not it:
                return {"error": "no such line"}
            ref = one_ref(it["ref"] or "")
            cid = make_card("note", ref,
                            (it["label"] or "A note") + " - what did you see here?",
                            it["text"], note_id=it["note_id"])
            db().execute("UPDATE note_item SET card_id = ? WHERE id = ?",
                         (cid, it["id"]))
            db().commit()
            return {"card_id": cid}
        row = db().execute("SELECT * FROM note WHERE id = ?", (_int(b("id")),)).fetchone()
        if not row:
            return {"error": "no such note"}
        n = note_dict(row)
        ref = one_ref(n["ref"] or "") if n["ref"] else None
        front = (n["label"] or "A note") + " - what did you see here?"
        cid = make_card("note", ref, front, n["text"], note_id=n["id"])
        return {"card_id": cid}

    if path == "/api/highlight" and method == "POST":
        ref = one_ref(str(b("ref") or ""))
        if not ref:
            return {"error": "no reference"}
        return {"id": save_highlight(ref, str(b("color") or "yellow"),
                                     str(b("snippet") or ""), str(b("note") or ""))}

    if path == "/api/highlight/delete" and method == "POST":
        db().execute("DELETE FROM highlight WHERE id = ?", (_int(b("id")),))
        db().commit()
        return {"ok": True}

    if path == "/api/highlights":
        return {"highlights": highlights_for(str(g("abbr") or ""), _int(g("ch")) or None,
                                             str(g("color") or ""), _int(g("limit"), 500))}

    if path == "/api/card" and method == "POST":
        ref = one_ref(str(b("ref") or "")) if b("ref") else None
        cid = make_card(str(b("kind") or "verse"), ref, str(b("front") or ""),
                        str(b("back") or ""), tags=str(b("tags") or ""))
        if b("reading_id"):
            db().execute("UPDATE reading SET card_count = card_count + 1 WHERE id = ?",
                         (_int(b("reading_id")),))
            db().commit()
        return {"id": cid, "card": card_dict(
            db().execute("SELECT * FROM card WHERE id = ?", (cid,)).fetchone())}

    if path == "/api/cards/due":
        return {"cards": due_cards(_int(g("limit"))), "retention":
                float(setting("retention") or 0.9)}

    if path == "/api/cards/review" and method == "POST":
        return review_card(_int(b("id")), _int(b("rating"), 3), _int(b("seconds")),
                           b("accuracy"))

    if path == "/api/cards/recite" and method == "POST":
        row = db().execute("SELECT * FROM card WHERE id = ?", (_int(b("id")),)).fetchone()
        if not row:
            return {"error": "no such card"}
        return compare_recital(str(b("typed") or ""), row["back"] or "")

    if path == "/api/cards":
        rows = db().execute("SELECT * FROM card ORDER BY due, id LIMIT ?",
                            (_int(g("limit"), 400),)).fetchall()
        return {"cards": [card_dict(r) for r in rows]}

    if path == "/api/card/delete" and method == "POST":
        cid = _int(b("id"))
        db().execute("UPDATE note SET card_id = NULL WHERE card_id = ?", (cid,))
        db().execute("DELETE FROM review WHERE card_id = ?", (cid,))
        db().execute("DELETE FROM card WHERE id = ?", (cid,))
        db().commit()
        return {"ok": True}

    if path == "/api/card/suspend" and method == "POST":
        db().execute("UPDATE card SET suspended = ? WHERE id = ?",
                     (1 if b("suspended") else 0, _int(b("id"))))
        db().commit()
        return {"ok": True}

    if path == "/api/plans":
        mine = [plan_progress(r["id"]) for r in db().execute(
            "SELECT id FROM plan ORDER BY active DESC, id DESC")]
        return {"mine": mine, "templates": PLAN_TEMPLATES,
                "book_sets": {k: {"title": v[0], "chapters":
                                  sum(chapters_in(x) for x in v[1])}
                              for k, v in BOOK_SETS.items()}}

    if path == "/api/plan/create" and method == "POST":
        kind = str(b("kind") or "list")
        spec = dict(b("spec") or {})
        pid = create_plan(kind, spec, str(b("name") or ""),
                          str(b("days_mask") or "1111111"))
        return {"id": pid, "plan": plan_progress(pid)}

    if path == "/api/plan/activate" and method == "POST":
        conn = db()
        conn.execute("UPDATE plan SET active = 0")
        conn.execute("UPDATE plan SET active = 1 WHERE id = ?", (_int(b("id")),))
        conn.commit()
        return {"ok": True}

    if path == "/api/plan/delete" and method == "POST":
        conn = db()
        pid = _int(b("id"))
        conn.execute("DELETE FROM plan_item WHERE plan_id = ?", (pid,))
        conn.execute("DELETE FROM plan WHERE id = ?", (pid,))
        conn.commit()
        return {"ok": True}

    if path == "/api/plan/skip" and method == "POST":
        db().execute("UPDATE plan_item SET skipped = 1 WHERE plan_id = ? AND seq = ?",
                     (_int(b("plan_id")), _int(b("seq"))))
        db().commit()
        return {"ok": True}

    if path == "/api/plan/pace" and method == "POST":
        conn = db()
        pid = _int(b("plan_id"))
        row = conn.execute("SELECT * FROM plan WHERE id = ?", (pid,)).fetchone()
        if not row:
            return {"error": "no such plan"}
        spec = json.loads(row["spec"])
        spec["pace"] = dict(b("pace") or {})
        # keep every day already read, rebuild the rest at the new pace
        done = conn.execute("SELECT COALESCE(MAX(seq), -1) s FROM plan_item"
                            " WHERE plan_id = ? AND done_on IS NOT NULL",
                            (pid,)).fetchone()["s"]
        keep = [refs_from_json(r["refs"]) for r in conn.execute(
            "SELECT refs FROM plan_item WHERE plan_id=? AND seq <= ? ORDER BY seq",
            (pid, done))]
        flat_done = {r.key() for day in keep for r in day}
        all_days = build_items(row["kind"], spec, 400)
        rest = [[r for r in day if r.key() not in flat_done] for day in all_days]
        rest = [dd for dd in rest if dd]
        conn.execute("DELETE FROM plan_item WHERE plan_id=? AND done_on IS NULL", (pid,))
        conn.execute("UPDATE plan SET spec=?, pace=? WHERE id=?",
                     (json.dumps(spec, separators=(",", ":")),
                      json.dumps(spec["pace"], separators=(",", ":")), pid))
        for i, refs in enumerate(rest):
            conn.execute(
                "INSERT OR IGNORE INTO plan_item(plan_id, seq, refs, label, verses,"
                " words) VALUES(?,?,?,?,?,?)",
                (pid, done + 1 + i, refs_to_json(refs), refs_label(refs),
                 sum(r.verse_count() for r in refs), sum(r.word_count() for r in refs)))
        conn.commit()
        return {"plan": plan_progress(pid)}

    if path == "/api/history":
        out = history(str(g("grain") or "day"), _int(g("limit"), 24))
        out["year"] = calendar_year(_int(g("year")) or None)
        return out

    if path == "/api/progress":
        return {"coverage": coverage(), "chapter_days": chapter_days(),
                "stats": stats(), "readings": recent_readings(60),
                "recalls": recall_history(30)}

    if path == "/api/search":
        out: dict = {"q": g("q") or ""}
        where = str(g("where") or "both")
        if where in ("both", "mine"):
            out["mine"] = search_local(str(g("q") or ""))
        if where in ("both", "bible"):
            try:
                out["bible"] = search_bible(str(g("q") or ""))
            except ApiError as e:
                out["bible_error"] = str(e)
        return out

    if path == "/api/projects":
        return {"projects": projects(_int(g("active"), 1) == 1)}

    if path == "/api/project/create" and method == "POST":
        refs = parse_ref(str(b("ref") or ""))
        if not refs:
            return {"error": "no reference"}
        pid = create_project(str(b("name") or ""), refs, _int(b("target_days"), 100))
        return {"id": pid, "project": project_today(pid)}

    if path == "/api/project/advance" and method == "POST":
        return project_advance(_int(b("id")), float(b("minutes") or 0),
                               _int(b("added"), 1), str(b("note") or ""))

    if path == "/api/project/archive" and method == "POST":
        db().execute("UPDATE project SET active = ? WHERE id = ?",
                     (0 if b("archive") else 1, _int(b("id"))))
        db().commit()
        return {"ok": True}

    if path == "/api/settings" and method == "POST":
        for k, v in (body or {}).items():
            if k in DEFAULT_SETTINGS:
                set_setting(k, str(v))
        return {"settings": settings_all()}

    if path == "/api/prefetch" and method == "POST":
        prefetch(_refs_arg(b("refs") or ""))
        return {"ok": True}

    if path == "/api/export":
        return export_all()

    return {"error": f"no route for {method} {path}"}


def export_all() -> dict:
    conn = db()
    out: dict = {"exported_at": now_str(), "schema": SCHEMA_VERSION,
                 "settings": settings_all()}
    for table in ("reading", "reading_chapter", "note", "note_item", "highlight",
                  "card", "review",
                  "plan", "plan_item", "project", "project_log", "recall"):
        out[table] = [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
    return out


# ===================================================================== the server
APP_HTML = HERE / "app.html"


class Handler(BaseHTTPRequestHandler):
    server_version = "abide"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args) -> None:            # quiet unless it matters
        if "code" in fmt and args and str(args[0]).startswith(("4", "5")):
            sys.stderr.write("abide: %s\n" % (fmt % args))

    # -- helpers --------------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode(), "application/json")

    def _local_only(self) -> bool:
        """Refuse anything a page on another site could have sent. The server is on
        127.0.0.1, but a browser will happily post here from anywhere, so the Origin
        has to look like this machine."""
        origin = self.headers.get("Origin") or ""
        if not origin:
            return True
        host = urllib.parse.urlparse(origin).hostname or ""
        return host in ("127.0.0.1", "localhost", "::1")

    # -- routes ---------------------------------------------------------------
    def do_GET(self) -> None:
        u = urllib.parse.urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if path in ("/", "/app.html", "/index.html"):
            if not APP_HTML.exists():
                return self._send(500, b"app.html is missing from the abide folder",
                                  "text/plain; charset=utf-8")
            return self._send(200, APP_HTML.read_bytes(), "text/html; charset=utf-8")
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if path.startswith("/api/"):
            if not self._local_only():
                return self._json({"error": "not from here"}, 403)
            try:
                return self._json(api("GET", path, q, {}))
            except ApiError as e:
                return self._json({"error": str(e), "kind": "api"}, 502)
            except Exception as e:
                sys.stderr.write("abide: GET %s failed: %r\n" % (path, e))
                return self._json({"error": repr(e)}, 500)
        self._send(404, b"not here", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        u = urllib.parse.urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if not self._local_only():
            return self._json({"error": "not from here"}, 403)
        n = _int(self.headers.get("Content-Length"), 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw.decode() or "{}")
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {"value": body}
        if not path.startswith("/api/"):
            return self._send(404, b"not here", "text/plain; charset=utf-8")
        try:
            return self._json(api("POST", path, q, body))
        except ApiError as e:
            return self._json({"error": str(e), "kind": "api"}, 502)
        except Exception as e:
            sys.stderr.write("abide: POST %s failed: %r\n" % (path, e))
            return self._json({"error": repr(e)}, 500)


def serve(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    migrate()
    url = f"http://127.0.0.1:{port}/"
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    p = active_plan()
    print(f"abide - {url}")
    if p:
        prog = plan_progress(int(p["id"]))
        left = f"{prog['left']} days left" if not prog["endless"] else "running"
        print(f"  plan: {p['name']} ({left})")
    wk = week_view()
    print(f"  this week: {wk['count']} of 7 days, target {wk['target']}")
    if not setting("api_key"):
        print("  text: anonymous access to api.nlt.to (50 verses a request, 500 a day)."
              "\n        a free key from api.nlt.to lifts that: python3 abide.py key <KEY>")
    if open_browser:
        threading.Thread(target=lambda: (time.sleep(0.4), webbrowser.open(url)),
                         daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nabide: stopped")


# ================================================================== the terminal
def _c(s: str, code: str) -> str:
    return f"\033[{code}m{s}\033[0m" if sys.stdout.isatty() else s


def n_of(n: int, one: str, many: str = "") -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def bold(s: str) -> str:
    return _c(s, "1")


def dim(s: str) -> str:
    return _c(s, "2")


def cmd_today(args) -> None:
    t = today_payload()
    wk, st = t["week"], t["streak"]
    ring = "".join("●" if x["read"] else "◐" if x["light"] else
                   "·" if not x["future"] else " " for x in wk["days"])
    print()
    print(bold(f"  {t['weekday']}, {t['date_long']}"))
    print(f"  {ring}   {wk['count']} of 7 days this week"
          + (dim("  (target " + str(wk["target"]) + ")") if not wk["met"]
             else _c("  target met", "32")))
    if st["current"]:
        print(dim(f"  {n_of(st['current'], 'day')} running, longest {st['longest']}"))
    if st["warn"]:
        print(_c("  two days missed. Not a lecture - just start tonight.", "33"))
        if t["rescue"]:
            print(f"  five minutes: {bold(t['rescue']['label'])}")
    print()
    if t["item"]:
        i = t["item"]
        print(f"  {bold(i['label'])}   "
              f"{dim(str(i['minutes']) + ' min, ' + n_of(i['verses'], 'verse'))}")
        if t["plan"]:
            pl = t["plan"]
            tail = (f"{pl['done']}/{pl['total']} days"
                    + (f", finishes about {pl['finish_estimate']}"
                       if pl.get("finish_estimate") else "")) if not pl["endless"] \
                else f"{pl['done']} days in"
            print(dim(f"  {pl['name']} - {tail}"))
        if getattr(args, "text", False):
            print()
            for p in passages_payload([r for r in refs_from_json(
                    json.dumps(i["refs"]))], with_marks=False):
                if p.get("error"):
                    print(f"  ({p['label']}: {p['error']})")
                    continue
                print(bold("  " + p["label"]))
                print(re.sub(r"^", "  ", render_text(p["blocks"], 74), flags=re.M))
                print()
    else:
        print("  no plan running. python3 abide.py plan start storyline")
    if t["due_count"]:
        print(dim(f"  {n_of(t['due_count'], 'verse')} due - python3 abide.py review"))
    if t["recall"]:
        print(dim(f"  recall: {t['recall']['prompt']}"))
    print()


def cmd_read(args) -> None:
    refs = parse_ref(" ".join(args.ref))
    if not refs:
        print("abide: could not read that reference")
        return
    for p in passages_payload(refs[:12], with_marks=False):
        print()
        if p.get("error"):
            print(f"{p['label']}: {p['error']}")
            continue
        print(bold(p["label"]) + dim(f"   {n_of(p['verse_count'], 'verse')}, "
                                     f"{round(p['words'] / WORDS_PER_MINUTE, 1)} min"))
        print()
        print(render_text(p["blocks"], 78))
    print()
    if getattr(args, "log", False):
        rid = start_reading(refs)
        touch_reading(rid, estimated_seconds(refs))
        finish_reading(rid)
        print(dim(f"logged: {refs_label(refs)}"))


def cmd_review(args) -> None:
    cards = due_cards()
    if not cards:
        print("nothing due. That is the system working.")
        return
    print(f"{n_of(len(cards), 'card')} due. Enter shows the answer, then "
          f"1 again / 2 hard / 3 good / 4 easy. q to stop.")
    for c in cards:
        print()
        print(bold(c["label"] or c["front"]))
        if c["kind"] == "firstletter":
            print(dim(c["cue"]))
        elif c["kind"] == "note":
            print(dim(c["front"]))
        try:
            input(dim("  [enter] "))
        except EOFError:
            return
        print()
        print("  " + "\n  ".join(re.findall(r".{1,74}(?:\s|$)", c["back"] or "")))
        try:
            r = input("  1/2/3/4 > ").strip().lower()
        except EOFError:
            return
        if r.startswith("q"):
            return
        rating = {"1": 1, "2": 2, "3": 3, "4": 4}.get(r, 3)
        res = review_card(c["id"], rating)
        print(dim(f"  back {res['due_in_words']}"))
    print("\ndone.")


def cmd_log(args) -> None:
    rows = recent_readings(args.n)
    if not rows:
        print("nothing logged yet.")
        return
    day = ""
    for r in rows:
        if r["day"] != day:
            day = r["day"]
            print()
            print(bold(datetime.fromisoformat(day).strftime("%a %-d %b %Y")))
        mark = "●" if r["engaged"] else "◐"
        mins = round((r["seconds"] or 0) / 60)
        print(f"  {mark} {r['clock']}  {r['label']:<34} {dim(str(mins) + ' min')}"
              + (dim("  read") if r["engaged"] else dim("  only opened"))
          + (dim("  note") if r["notes"] else "")
              + (dim("  kept") if r["cards"] else "")
              + (dim("  recalled") if r["recalled"] else ""))
    print()


def cmd_stats(args) -> None:
    s = stats()
    wk, st, ck = s["week"], s["streak"], s["clock"]
    print()
    print(bold("  the habit"))
    print(f"    this week           {wk['count']} of 7 (target {wk['target']})")
    print(f"    weeks on target     {s['weeks_on_target']['met']} of the last 12")
    print(f"    days running        {st['current']}   (longest {st['longest']})")
    print(f"    days ever           {st['days_total']}")
    if ck.get("n"):
        print(f"    usual time          {ck['median']}  ±{ck['spread_minutes']} min"
              f"   (aiming at {ck['aim']})")
    print()
    print(bold("  the reading"))
    print(f"    readings            {s['readings']}")
    print(f"    time                {s['minutes']} min")
    print(f"    of the Bible        {s['chapters_read']} of {s['chapters_total']}"
          f" chapters, {s['percent_bible']}%")
    print(f"    books finished      {s['books_complete']} of 66")
    print(f"    cached here         {s['cached_chapters']} chapters")
    print()
    print(bold("  what stuck"))
    print(f"    verses kept         {s['cards']}  ({s['cards_due']} due today)")
    print(f"    reviews             {s['reviews']}"
          + (f", {s['recall_rate']}% recalled" if s["recall_rate"] is not None else ""))
    print(f"    average hold        {s['avg_stability_days']} days")
    print(f"    notes / highlights  {s['notes']} / {s['highlights']}")
    print(f"    recall questions    {s['recalls']}")
    print()


def cmd_plan(args) -> None:
    if args.what == "list":
        print()
        for t in PLAN_TEMPLATES:
            print(f"  {bold(t['id']):<28} {t['name']}")
            print(dim("      " + re.sub(r"\s+", " ", t["why"])[:96]))
        print()
        mine = [plan_progress(r["id"]) for r in db().execute(
            "SELECT id FROM plan ORDER BY active DESC, id DESC")]
        if mine:
            print(bold("  yours"))
            for p in mine:
                tail = f"{p['done']}/{p['total']}" if not p["endless"] else n_of(p["done"], "day")
                print(f"    {p['name']:<34} {tail}")
            print()
        return
    if args.what == "start":
        tid = (args.id or "").strip()
        tpl = next((t for t in PLAN_TEMPLATES if t["id"] == tid), None)
        if not tpl:
            print(f"abide: no template called {tid!r}. Try: abide.py plan list")
            return
        spec: dict = {"pace": dict(tpl["pace"]), "name": tpl["name"]}
        kind = tpl["kind"]
        if kind == "list":
            if tpl.get("set"):
                spec["set"] = tpl["set"]
            elif args.book:
                got = parse_ref(args.book)
                if not got:
                    print("abide: which book?")
                    return
                spec["books"] = [got[0].abbr]
            else:
                print("abide: this one needs a book: --book John")
                return
        elif kind == "tracks":
            spec["tracks"] = tpl["tracks"]
        elif kind == "dated":
            spec["rule"] = tpl["rule"]
        elif kind == "api":
            spec["api_plan"] = tpl["api_plan"]
        if args.per_day:
            spec["pace"] = {"per_day": args.per_day}
        if args.minutes:
            spec["pace"] = {"minutes": args.minutes}
        pid = create_plan(kind, spec, tpl["name"])
        p = plan_progress(pid)
        print(f"started: {p['name']}"
              + (f" - {p['total']} days" if not p["endless"] else ""))
        item = plan_item_for_today(pid)
        if item:
            print(f"today: {item['label']}")
        return
    print("abide: plan list | plan start <id> [--book John] [--per-day 2] [--minutes 10]")


def cmd_key(args) -> None:
    k = (args.value or "").strip()
    set_setting("api_key", k)
    if k:
        print("saved. 500 verses a request, 5,000 requests a day.")
    else:
        print("cleared. Anonymous access: 50 verses a request, 500 a day.")


def cmd_prefetch(args) -> None:
    p = active_plan()
    if not p:
        print("no plan running.")
        return
    refs = upcoming_refs(int(p["id"]), args.n)
    todo = [r for r in refs if not have_cached(r)]
    if not todo:
        print(f"the next {args.n} days are already here.")
        return
    print(f"fetching {len(todo)} chapters...")
    for r in todo:
        try:
            chapter(r.abbr, r.ch)
            print(f"  {r.label()}")
        except ApiError as e:
            print(f"  {r.label()}: {e}")
            return


def cmd_export(args) -> None:
    json.dump(export_all(), sys.stdout, indent=1, default=str)
    sys.stdout.write("\n")


def cmd_init(args) -> None:
    init_db()
    migrate()
    print(f"abide: {DB_PATH}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="abide", description="read the Bible today, and still know it in a year")
    sub = ap.add_subparsers(dest="cmd")

    ps = sub.add_parser("serve", help="the app in a browser")
    ps.add_argument("--port", type=int, default=DEFAULT_PORT)
    ps.add_argument("--no-open", action="store_true")

    pt = sub.add_parser("today", help="today's reading")
    pt.add_argument("--text", action="store_true", help="print the passage too")

    pr = sub.add_parser("read", help="any passage")
    pr.add_argument("ref", nargs="+")
    pr.add_argument("--log", action="store_true", help="record it as read")

    sub.add_parser("review", help="the verses that are due")

    pl = sub.add_parser("log", help="what you read, and when")
    pl.add_argument("-n", type=int, default=40)

    sub.add_parser("stats", help="the week, the streak, the coverage")

    pp = sub.add_parser("plan", help="plans")
    pp.add_argument("what", nargs="?", default="list", choices=["list", "start"])
    pp.add_argument("id", nargs="?", default="")
    pp.add_argument("--book", default="")
    pp.add_argument("--per-day", type=int, dest="per_day", default=0)
    pp.add_argument("--minutes", type=int, default=0)

    pk = sub.add_parser("key", help="your api.nlt.to key")
    pk.add_argument("value", nargs="?", default="")

    pf = sub.add_parser("prefetch", help="cache the days ahead")
    pf.add_argument("-n", type=int, default=7)

    sub.add_parser("export", help="everything, as JSON")
    sub.add_parser("init", help="make the database")

    args = ap.parse_args(argv)
    if args.cmd in (None, "serve"):
        migrate()
        return serve(getattr(args, "port", DEFAULT_PORT),
                     not getattr(args, "no_open", False)) or 0
    migrate()
    {"today": cmd_today, "read": cmd_read, "review": cmd_review, "log": cmd_log,
     "stats": cmd_stats, "plan": cmd_plan, "key": cmd_key, "prefetch": cmd_prefetch,
     "export": cmd_export, "init": cmd_init}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
