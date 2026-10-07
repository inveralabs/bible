# abide — read the Bible today, and still know it in a year

```sh
cd ~/code/abide
python3 abide.py serve          # opens http://127.0.0.1:7847
```

One Python file, one HTML file, one SQLite database, a server on `127.0.0.1`. Stdlib
only — nothing to install and nothing to build. No account, no sync, no telemetry. The
only thing that ever leaves this machine is a request to **api.nlt.to** for a chapter you
have not read yet, and once it has been read it is never asked for again.

The NLT text comes from Tyndale's own API. abide is not affiliated with Tyndale House;
the New Living Translation is theirs, and everything you write about it is yours.

---

## Why it is shaped like this

Most Bible apps are a reading plan with a checkmark. The checkmark is the easy part. The
hard parts are being regular without being crushed by a broken streak, and remembering
in June what you saw in March. So four things sit in one app, because doing the first
without the other three is what makes a year of reading evaporate:

| | |
|---|---|
| **read** | today's passage in the NLT, fetched once and cached here for good |
| **recall** | thirty seconds on the last thing you read, *before* you read today's |
| **keep** | verses and your own notes on a spaced schedule, so they come back |
| **know** | every reading logged with its date, its clock time and how long you stayed |

Everything below is the reasoning, and where it came from.

### Four days a week, not seven

The Center for Bible Engagement surveyed 40,000 people aged 8 to 80 and found something
odd: reading the Bible once, twice or three times a week looked statistically like not
reading it at all. At **four days a week** the numbers moved sharply — self-reported
loneliness down 30%, anger down 32%, feeling spiritually stuck down 60%.

Whatever you make of survey self-reports, the shape of the finding is the useful part:
there is a threshold, and it is not seven. So the headline number in abide is
**days this week out of seven, with a target of four**. The streak is there, smaller,
below it. You can move the target in Settings.

### One missed day is nothing. Two in a row is the thing to watch

Lally and colleagues followed 96 people forming a daily habit over 12 weeks. Automaticity
took a median of 66 days — not 21 — and ranged from 18 to 254. The detail that matters
here: **a single missed opportunity barely moved the curve.** What stalled people was
missing repeatedly, two or more times a week.

So abide says nothing after one missed day. On the second consecutive miss it says one
quiet sentence and offers a five-minute passage — Psalm 121, Lamentations 3:19-26,
Philippians 4:4-9 — instead of a lecture and a broken chain.

### No plan here can put you behind

Reported completion rates for one-year plans sit around **one in ten**. (YouVersion does
not publish official figures, so treat the exact number as folklore.) The reason people
give for quitting is not usually the reading — it is the feeling of being behind, and
Lifeway Research finds that "I already ruined it" is a top reason readers abandon
structured plans altogether. Most of them stall in the legal chapters of Leviticus, which
canonical one-year plans reach in about week three.

So a plan in abide is **an ordered list and your place in it**. There are no dates on the
items. You cannot be twelve days behind, because there is nothing to be behind. What
moves instead is the projected finish date, calculated from the pace you actually keep:

> *The storyline, in 14 books — 10 of 144 days · finishes about 12 March 2027, at 4.7
> days a week*

If you read four days a week, a one-year plan takes about eighteen months. That is a
finished Bible, not a failed year.

### Opening a chapter is not reading it

Duolingo's own retention team has said the streak freeze cut churn by 21% for users about
to break a chain — and also that streaks push people to speed-run a lesson to protect the
number, which keeps the metric and loses the learning.

So there are exactly two ways a sitting counts toward your week:

1. **You said so** — you pressed *I have read this*. That settles it, and nothing
   overrules you.
2. **You left something behind** — a note that is still there, a verse kept, a recall
   answered. That is evidence, and it needs no button.

**Time on screen is not one of them.** Leaving a chapter open for eight minutes proves you
had a tab open. If a sitting has real time on it and you never said either way, Today asks
you afterwards — *"You spent 4 minutes in Genesis 1 on Sunday. Did you finish it?
[Yes, I read it] [No, I only opened it]"* — and your answer decides. A glance with nothing
to show for it is thrown away rather than logged, and a chapter you only opened never
advances the plan, because a mis-click should not spend one of its days.

**And the record is yours to correct, at any time.** Every sitting — on Today, in the Log,
in Progress — carries a single chip saying **read** or **only opened**. Click it and it
flips: marking it read advances the plan day and puts the chapter on the map; marking it
only-opened takes both back. Next to it, an `×` removes the sitting from the log
altogether. Your word is final in both directions — press *I have read this* on a chapter
you read on paper this morning and it counts, however few seconds the tab was open.

The same applies backwards. If a note is what counted a passage as read and you later
delete that note, the claim goes with it: the sitting stops counting, the plan day is
handed back and the chapter comes off the map. Evidence is counted from what is actually
there, never from a tally that only goes up.

This app is a record of what you have read. A record that flatters you is worthless.

### Recall before you read

Roediger and Karpicke's students who spent a session recalling a passage remembered 61% of
it a week later. The ones who spent the same time reading it again remembered 40%.
Retrieval is the cheapest intervention in this entire app and the most valuable one.

So before today's reading, abide asks one question about the last thing you read —
*"What do you remember of Genesis 29-30?"* — takes whatever you type, then shows you what
you wrote at the time and how the passage opens. Nothing is marked wrong. It takes half a
minute, it is skippable, and it is the single feature most likely to make this year of
reading different from the last one.

### A note is a comment, and it is attached to a verse

The standing complaint about note-taking in Bible apps is that notes go in and never come
out: a reverse-chronological list nobody scrolls, no way to sort highlights by anything
but time. Two things here answer that.

First, the unit is **the verse, not the passage**. You write against Genesis 1:27, and
that line stays attached to Genesis 1:27 — underlined in the text, findable from that
chapter, keepable on its own — while still being part of the one entry you saved that
morning. A note filed on one blob of "Genesis 1-3" is a note you will never find again.
And it is written *where it belongs*: in the margin, next to the line, saved on enter.

Second, a note is one click from becoming a card. What you saw in Romans 8 in March is
then put in front of you in June, on a schedule, instead of dying in a list.

---

## Today — one page

Today and Read are the same page, because they were always the same act. The page opens
on the plan's reading for today, and the same page browses all 1,189 chapters: `←` and
`→` turn the chapter, the picker underneath opens any book, and a reference typed into
the box goes straight there. You never switch tabs to look something up in the middle of
a sitting.

In order:

1. **The month, across the top.** Every day of it in a strip — the date in each cell,
   the minutes inside, filled for a day you read, pale for one where a chapter was only
   opened, dashed for a day that has not happened. Weekends sit a shade back so the rhythm of your week is
   visible. On the left, `August 2026 · 17 of 23 days · 5.2 a week`; on the right, `5 of 7
   this week · target met`, because the week is the unit the target lives in. Click any
   day to open the Log. Seven dots was too short a window to see whether a month was
   going well.
2. **Thirty seconds of recall.** One question about the last reading. Type, then reveal.
   Grade it *Nothing / Some of it / Most of it* — that grade is kept, so Progress can show
   whether things are actually sticking.
3. **The reading.** The passage in the NLT, set as a page: a serif column at about 34em,
   verse numbers small and out of the way, poetry indented the way the NLT indents it,
   the words of Christ in red, translator's footnotes on hover. A chip says whether this
   is *today's reading* or something *you chose*; `←` `→` move a chapter either way, and
   **Back to today's reading** returns you to the plan.
4. **A timer, bottom right.** Counts only while the tab is in front of you. It shows
   progress against the chapter's real word count at 200 words a minute, so *11 min* is
   an estimate from the text rather than a guess.
5. **Select any verse.** A small toolbar appears: six highlight colours, **Keep** (makes a
   card), **Note** (attaches your writing to those verses), **Copy** (with the reference).
6. **Every note is a comment on a verse.** Click a verse number and a box opens in the
   gutter beside that line — the way a comment sits beside a paragraph in a document.
   Write it and press **enter**: it is saved, then and there. No panel at the bottom of
   the page, no separate save step, nothing to remember to press.

   The method only changes the shape of the box, and whichever you pick it still opens
   **beside the verse**:

   | Method | The box |
   |---|---|
   | **Verse by verse** | one field. `enter` saves, `shift-enter` for a new line — *the default* |
   | **SOAP** | Scripture · Observation · Application · Prayer. `⌘↵` saves |
   | **Lectio divina** | Read · Meditate · Pray · Rest |
   | **The Swedish method** | Arrow (what struck me) · Question mark · Candle (what to do) |
   | **COMA** | Context · Observation · Meaning · Application |
   | **Just write**, **A question**, **A prayer** | one field each |

   The dropdown for that sits inside each box, so one comment can be a line and the next
   can be a full SOAP without changing any setting. `esc` throws away a box you have
   changed your mind about. **A note on the whole passage** in the footer opens a comment
   anchored to the chapter rather than to a verse.

   Comments written in one sitting are **gathered into a single entry**, so the Journal
   still reads as "what I wrote on Tuesday" — but each line keeps its own verse, its own
   method and its own place in the margin. Any single line can become a memory card on
   its own, or be edited in place, or removed.

   **Nothing asks you to confirm, and nothing waits on the network.** *remove* takes it
   off the page at once and the toast carries an **undo** for as long as it is on screen;
   the same for saving — the card appears the instant you press enter, and the server is
   reconciled behind it. A reconcile that is already in flight can never undo a change
   made after it was asked for. A dialogue box in the middle of reading is worse than the
   mistake it prevents.

   Three things keep the gutter readable rather than a tall column of half-empty boxes:

   - **It is measured, not guessed.** Anchors are read off the laid-out text, so a comment
     sits *on* its line, not near it. Anything that changes a height re-runs the layout —
     the window resizing, a webfont arriving late, a box dragged taller, a comment
     opening. A resize reads your half-written text back first, so nothing in progress is
     lost.
   - **Comments within a few lines of each other share one card.** Giving each its own row
     is what wasted the space. A box you are writing never shares with one already saved.
   - **A card is two lines tall until you open it.** Click it to expand; *collapse all* is
     in the gutter heading.

   The text keeps its measure and the gutter takes the slack, so a wider window gets wider
   comments rather than a wider empty strip. Under 1000px there is nowhere to put a gutter,
   so the same comments — saved ones and boxes you are writing — stack under the passage
   instead.

7. **"I have read this."** Logged with the clock time, the seconds, how far you scrolled,
   and whether it counted. The next three chapters are fetched in the background, so
   tomorrow works on a plane.

**Or read something else.** The plan has an opinion about today; you do not have to take
it. Underneath the reading, Today carries a picker: type a reference in one box
(`rom 8`, `psalm 23`, `1 sam 17`, `jn 3:16`) and press Open, or choose any of the 66 books
and click a chapter. Chapters you have already read are outlined so you can see where you
have been. Anything read this way is logged exactly like the plan's reading — it counts
toward the week, it takes notes, it lands in the Log — it just does not advance the plan.

**Switching chapter.** The button in the passage header — `Numbers 2 ▾`, or press `b` —
opens a panel the width of the card. Sixty-six books do not belong in a dropdown, so
instead the ten categories run down the left and their books flow horizontally across:

```
OLD TESTAMENT
           Law   Genesis ✓  Exodus ✓  Leviticus  Numbers 1/36  Deuteronomy
       History   Joshua  Judges  Ruth  1 Samuel  2 Samuel  1 Kings  …
        Wisdom   Job  Psalms  Proverbs  Ecclesiastes  Song of Songs
Major prophets   Isaiah  Jeremiah  Lamentations  Ezekiel  Daniel
Minor prophets   Hosea  Joel  Amos  Obadiah  Jonah  Micah  …
NEW TESTAMENT
       Gospels   Matthew  Mark  Luke  John
       History   Acts
          Paul   Romans  1 Corinthians  2 Corinthians  Galatians  …
       Letters   Hebrews  James  1 Peter  2 Peter  1 John  …
      Prophecy   Revelation
───────────────────────────────────────────────────────────────────
       Numbers   1  2  3  4  5  6  7  8  9  10  11  12  …  36
     1 of 36 read
```

A book you have finished is filled in with a tick; one you are partway through says how
far (`1/36`); the chapter you are in is solid. Point at any book and its chapters appear
along the bottom, chapters you have read outlined. Click a chapter and it opens.

There is a filter box at the top of the panel: type `psal` and only Psalms is left, or
type a whole reference — `rom 8`, `ii cor 5`, `jn 3:16` — and `enter` goes straight there.
`←` and `→` move a chapter either way without opening anything, running past the end of a
book into the next one. The search box in the top bar takes references too.

**A row only appears when there is something to record.** Anything you actually do —
a comment, a verse kept, pressing *I have read this* — records the sitting at once.
Failing that it takes **ninety seconds** on the passage before a row is made at all, so
opening a chapter to check something leaves nothing behind. Whatever is left open is
tidied up half an hour later and filed as **only opened**, not read, unless you say
otherwise — and every sitting has an `×` on it if you would rather it were not there.

---

## Plans

Twelve to start from. Every one of them is reflowable, and every one can be re-paced later
without losing the days you have read.

| Plan | What it is |
|---|---|
| **The storyline, in 14 books** | Genesis, Exodus, Numbers, Joshua, Judges, 1-2 Samuel, 1-2 Kings, Ezra, Nehemiah, Daniel, Luke, Acts. The plot of the Bible end to end, skipping nothing inside those books but ordering them so the narrative carries you. About 15 minutes. **The recommended start.** |
| **The New Testament, one year** | One chapter a day, 260 chapters — finishes inside a year even at five days a week. |
| **The Gospels in 90 days** | 89 chapters, one a day. The best place to start if you are starting. |
| **The whole Bible, one year** | 1,189 chapters at four a day, about 14 minutes. |
| **The whole Bible, two years** | Ten minutes a day, whatever that comes to in chapters. Slower, and far likelier to be the one you finish. |
| **Old and New together** | One OT and one NT chapter a day, each track moving at its own speed. |
| **Old, New, and a psalm** | Three chapters, about 12 minutes. |
| **Horner's ten lists** | Professor Grant Horner's system: ten chapters a day from ten lists at once — a Gospel, the Law, a letter, a psalm, a proverb — each list looping independently, so no two days line up the same way twice. About 35 minutes. |
| **The Psalms every month** | Five a day by the date: the 8th means Psalms 8, 38, 68, 98 and 128. All 150 every month. |
| **A proverb a day** | Chapter matches the date. |
| **One Year Chronological Bible** | Tyndale's own chronological plan, in the order things happened, read a day at a time straight from the API. |
| **One book, slowly** | Any book, a chapter a day. The way to actually know one letter rather than half-know all of them. |

**Or build your own.** One line at the top of the Plans tab:

> Read **[ Philippians ]** in **[ a number of days ]** **[ 10 ]**  → *Start it*

Pick any single book or any of eleven groups (the whole Bible, the Old Testament, the
Gospels, the Law, wisdom and poetry, the prophets, Paul's letters…), then say what you
want to hold fixed — **a number of days**, **a number of chapters a day**, or **a number
of minutes a day**. The other two are worked out from the real word count and shown before
you commit:

> *John is 21 chapters, about 89 minutes of reading in all. At this pace that is 10 days
> of 2.1 chapters (about 9 min) each — and reading 4 days a week, it finishes about
> 10 September.*

**Pace** on any plan is set the same three ways, plus a date to finish by. **Change the
pace** whenever you like — everything you have read stays exactly as it is, and only the
days after today are rebuilt.

---

## The text

Tyndale runs a free API for the NLT at **api.nlt.to**, and abide talks to it directly.

| | Anonymous | With a free key |
|---|---|---|
| verses per request | 50 | 500 |
| requests per day | 500 | 5,000 |

abide fetches **one chapter at a time and never the same chapter twice**. A whole Bible
costs 1,189 requests across a lifetime of reading, so anonymous access is genuinely
enough. Chapters over the anonymous 50-verse cap — Psalm 119 is 176 verses — are fetched
in pieces and stitched back together.

Your key is already saved, so this install is on the higher limits — Psalm 119 comes down
in one request. To change or clear it:

```sh
python3 abide.py key YOUR-KEY-HERE     # or with no argument, clear it
```

Also available through the same API and the same setting: **NLTUK** (British), **NTV**
(Spanish) and **KJV**.

**What is cached and what is not.** Chapters you have read are stored in the local
database as structured blocks plus one row per verse — so highlights, verse cards,
searching your own text and typing a verse from memory all work offline. `abide.py export`
deliberately leaves the scripture out: your readings, notes, highlights, cards, reviews
and plans are yours to take, and the text is Tyndale's.

**What the reader is doing with the API's HTML.** The API answers with a page, not JSON:
`<verse_export>` elements carrying book, chapter and verse attributes, paragraph classes
for prose and poetry, small caps for the divine name, footnotes as a nested span. abide
takes that apart into its own blocks and verses, keeps only the inline marks it recognises
and strips every tag, attribute and handler it does not — so nothing arriving over the
network is ever handed to the browser as markup. The shape of all 1,189 chapters was
checked against this parser: 31,104 verses and 745,547 words, which is the NLT's own
count.

---

## Keep — one tab for everything you wrote and everything you are holding

**Keep** is the review queue at the top, and under it a switch between three things:

- **Comments** — everything you have written, filed under the verse it came from, with
  filters by book, by method and by words in the text. This is where the old Journal tab
  went; there was never a good reason for what you wrote and what you are trying to
  remember to live on separate pages.
- **Verses kept** — the collection, with how long each one currently holds, how many times
  you have seen it, and when it comes back.
- **Memorising** — the long projects (see below).

### The scheduler: FSRS-6

The scheduler is **FSRS-6** — the algorithm Anki adopted in 2024 — with its published
default weights, implemented here in about a hundred lines of Python. It models three
things per card:

- **difficulty** — how hard this particular thing is for you
- **stability** — how many days the memory currently lasts
- **retrievability** — the chance you would get it right at this moment

A card comes back when retrievability falls to your target (0.90 by default). That beats
the old SM-2 interval doubling because it is fitted to the forgetting curve rather than
guessing at it. Answer *Good* four times and the gaps go roughly 2 days → 11 → 46 → 163.

**One deliberate change.** Left alone, FSRS will happily push a well-known verse out nine
years. A verse you are *keeping* should come back at least once a year, so the interval is
capped at 365 days. Change it in Settings.

### Four kinds of card

| Kind | Front | Back |
|---|---|---|
| **verse** | the reference | the words |
| **first letters** | `“F__ t___ i_ h__ G__ l____ t__ w____…`  | the words |
| **note** | the reference and a prompt | what you wrote |
| **fact** | anything | anything |

### Type it out

Tick **type it out** and you get a textarea instead of a flip. What you type is compared
against the text word by word — a longest-common-subsequence match, so one missed word does
not throw off everything after it. You get the accuracy, the missing words underlined in
the real text, and a suggested grade you can override.

This is not pedantry about exact wording. Producing the words is retrieval; recognising
them is not, and the difference is the entire reason spaced repetition works.

## Memorising something long

Andrew Davis's method, which is the one that reliably gets people through whole books:

> Say the new verse ten times reading it, then ten times without looking. Add it to
> everything you already have and say the lot. One verse a day. When the passage is
> finished, stop adding and say the whole thing once a day for **a hundred days**.

Fifteen minutes a day, for months. abide's job is to hold the count, not to hurry you: it
tracks which verse is next, shows you everything you have so far as one continuous text to
recite, counts the hundred days, and tells you plainly whether you have done it today.
Start one with any reference — `Rom 8`, `Ps 23`, `Phil 2:1-11`, `James`.

## The Log — day, week, month

A tab of its own. Across the top, **the year you are in** as a contribution graph —
weekday labels down the side, month labels along it, a square a day shaded by minutes,
today ringed, and the totals beside the heading: days read, days a week, hours, and how
many days a chapter was only opened. If you have read in more than one year there is a
picker. It is context for the rows underneath, not a page of its own.

Then three altitudes with a switch between them. Same readings, three questions.

**Day** — *what did I read, and when?* Days are grouped under a month heading carrying
that month's totals. Each day is a calendar chit (weekday and date, filled if the day
counted), then what was covered set in the reading serif, then the books it touched, then
every sitting as a small pill with **the clock time it started** and how long it ran. On
the right, the minutes as a number and as a bar against your best day, with the chapter
and verse counts underneath.

**Week** — *is the habit holding?* One row per week: the dates, `5 of 7 days · target
met`, and the books. In the middle, seven cells across the full width of the row — day
letter on top, minutes inside, filled for a day you read, pale for one where a chapter was
only opened, dashed for a day that has not happened yet. Then what the week covered, and the totals on the right.
The target lives at this altitude, so this is the view to look at on a Sunday.

**Month** — *is a book finishing?* An actual calendar: seven columns, the real weekday
alignment, each square shaded by how long you read that day with the minutes printed in
it. Beside it a stat column — days read out of the days that have actually happened, what
that works out to per week, time, chapters, verses, notes written, verses kept, reviews —
and under the calendar, every book the month touched.

Every sitting carries two controls: the chip saying **read** or **only opened**, which
flips when you click it, and an `×` that takes the sitting out of the log for good.

**The Log shows what you read.** Days where a chapter was only opened sit behind the
*also show chapters I only opened* switch, with the count next to it — so a chapter you
opened for two minutes and closed is not sitting in the middle of your week pretending to
be a reading.

Everything is drawn from the readings themselves. Nothing is entered twice, and a chapter
you only opened is never quietly promoted to one you read.

## Progress

Read top to bottom. Only chapters you have said you read appear here — the Log has
everything.

**Where you are.** A ring showing the percentage of the Bible you have read, and beside it
six numbers with the useful half said underneath each: chapters (and how many are left),
books finished (and how many are still open), days read (and the date you started), time
(and the average sitting), your longest run (and the current one), weeks on target (and
what the target is). Under that, every book you have finished, as a row of chips you can
click into.

**All 1,189 chapters**, in two columns — Old Testament and New — each broken into its
categories with a progress bar and a count on every one, so *Law 91/187* and *Minor
prophets 0/67* are visible without arithmetic. Then a row per book: the name, and one cell
per chapter. A chapter read once is already bright — the map does not use the bottom of the
colour ramp at all, because a chapter you have read should be obvious across the room —
and twice or more is brighter still. A ring means you read part of it.

**Click any chapter and it tells you when you read it**, not the other way round: how
many times, then the date, the clock time and the minutes for each sitting, with *Open it*
there if that is what you wanted. A finished book turns its own name the accent colour.

**Weeks that hit the target** — twelve bars with a dashed line drawn at the target itself,
so a week either clears it or does not, at a glance.

**When you read** — a 24-hour histogram with your median start time and how far a normal
day drifts from it, against the hour you said you were aiming at. A fixed hour does more
for a habit than a long session.

**What stuck** — verses and notes kept, how many are started, how many are due, reviews
done, the share you actually recalled, the average hold in days, comments written,
highlights, and chapters cached on this machine.

**What you remembered** — your recall answers, each with how many days had passed and how
much came back.

## The terminal

`bible` is the whole thing. It starts the server if it is not up, opens the browser if it
is, and — because `abide.py` only changes when the process restarts — quietly restarts
itself first if the script has been edited since the server started.

```sh
bible                    # start it, or open it if it is already up
bible today              # the week, the streak, today's reading
bible today --text       # ...and print the passage
bible read rom 8         # any passage: "bible read 1 sam 17", "bible read ps119:105"
bible read ps 121 --log  # ...and record it as read
bible review             # the verses that are due, one at a time
bible log -n 20          # what you read, and when
bible stats              # the habit, the reading, what stuck
bible plan list          # the twelve, and yours
bible plan start storyline
bible plan start one-book --book Philippians --per-day 1
bible plan start whole-two-year --minutes 10
bible prefetch -n 14     # cache the next fortnight for a flight
bible key YOUR-KEY       # or with no argument, clear it
bible export > backup.json
bible restart            # stop and start again
bible stop               # stop the server
bible tail               # watch the server's output
```

`abide` and `ab` are the same command. Subcommands run straight against the database, so
they work whether or not a server happens to be up. The server's output goes to
`data/serve.log`.

`abide.py read` accepts references the way you would write them: `john 3:16-18`,
`1 sam 17`, `ps 23`, `psalm 119:105`, `ii cor 5`, `song of solomon 2`, `jude 3`,
`gen 1-3`, `1cor13`. One-chapter books are cited without the chapter, so `jude 3` is the
third verse, which is what you meant.

The alias is already in your `~/.zshrc`:

```sh
[ -f "$HOME/code/abide/shell-init.zsh" ] && source "$HOME/code/abide/shell-init.zsh"
```

Delete that line to remove it. `ABIDE_HOME`, `ABIDE_PORT` and `ABIDE_LOG` override the
defaults.

## Keyboard

| | |
|---|---|
| `t` `l` `k` `p` `s` | today, log, keep, progress, settings |
| `b` | the book picker |
| `←` `→` | the chapter before, the chapter after |
| `/` | the search box |
| `space` | in Keep: reveal the answer |
| `1` `2` `3` `4` | again, hard, good, easy |
| `⌘↵` | save the note or the dialogue you are in |
| `esc` | close, or leave the box you are typing in |

The search box does two jobs. Type a reference and it opens it — `psalm 23`, `1 jn 4:8`,
`rev 22`. Type anything else and it searches the whole NLT through Tyndale's search
endpoint *and* your own notes, highlights and cards at the same time.

## The look

Pitch black by default: `--bg` is `#000000`, and nothing is lifted by a fill — every edge
in the app is a thin border rather than a change of grey. The neutrals stay strictly
neutral and only the accent is tinted, which is what stops a black theme reading as
mauve. The accent is violet — `#a78bfa` on black, `#6d4aff` on white — and the heatmap
ramp climbs to it, so the map of the Bible, the year, the week strip and the progress ring
are all the same colour saying the same thing. The one
exception is anything that floats: a shadow is invisible on black, so a popover, a modal,
a comment card and the toast lift by a hair and brighten their border to separate from the
page underneath.

Scripture is set a shade below pure white (`#ededf0`) because 100% white on 100% black is
a hard read at length. A light theme is in Settings if you want it, along with the type
size, the column width and whether scripture is set in a serif.

## One thing to know about restarting

`app.html` is read from disk on every request, so **the interface updates the moment you
reload the browser**. `abide.py` is the running process, so **the server only updates when
you restart it**. If the two get out of step — a new page asking an old server for
something it has never heard of — you get a confidently wrong answer rather than an error.

So the server records when it started and says so, and the page puts a banner across the
top when `abide.py` is newer than the running process, with the command to fix it:

```sh
pkill -f "abide.py serve" && cd ~/code/abide && python3 abide.py serve
```

## Where things are

```
~/code/abide/
  abide.py         the whole app
  app.html         the whole interface
  abide.db         your database — readings, notes, highlights, cards, plans, cache
  shell-init.zsh   the `bible` command, sourced from ~/.zshrc
  data/serve.log   what the server printed, when started by `bible`
  data/            a cached copy of the system CA roots, if python needed them
```

Move or back up `abide.db` and you have moved everything. `ABIDE_DB` and `ABIDE_PORT`
override the defaults.

The server binds to `127.0.0.1` only, and rejects any request arriving with an `Origin`
header that is not this machine — so a page on another site cannot post to it while your
browser is open.

## What it does not do

- No sync, no account, no phone app. One machine.
- No commentary, no cross-references, no original languages, no maps. The NLT text, your
  notes, and the schedule.
- No audio. The NLT API does not serve it.
- No sharing, no plans-with-friends, no badges, no notifications. The only nudge is the
  app being open when you sit down.

## Sources

The research this app is built on, so you can check whether I read it right:

- Cole, A. & Ovwigho, P., **"Understanding the Bible Engagement Challenge: Scientific
  Evidence for the Power of 4"**, Center for Bible Engagement —
  [bttbfiles.com](https://bttbfiles.com/web/docs/cbe/Scientific_Evidence_for_the_Power_of_4.pdf),
  summarised at [centerforbibleengagement.org](https://www.centerforbibleengagement.org/post/bible-engagement-a-key-to-spiritual-growth)
- Lally, P., van Jaarsveld, C., Potts, H. & Wardle, J. (2010), **"How are habits formed:
  Modelling habit formation in the real world"**, *European Journal of Social Psychology*
  40(6) — the 66-day median, the 18-254 day range, and the finding that one missed
  opportunity did not materially affect the process
- Roediger, H. & Karpicke, J. (2006), **"The Power of Testing Memory"** and
  *"Test-enhanced learning"*, *Psychological Science* — 61% recalled after retrieval
  practice against 40% after rereading
  ([wustl.edu, PDF](http://psychnet.wustl.edu/memory/wp-content/uploads/2018/04/Roediger-Karpicke-2006_PPS.pdf))
- **FSRS** — the DSR memory model and the FSRS-6 formulas and default weights, from the
  Open Spaced Repetition project
  ([awesome-fsrs wiki](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm))
- Davis, A., **"An Approach to Extended Memorization of Scripture"**
  ([PDF](https://scripturememory.com/downloadables/andrewdavis.pdf))
- **Professor Grant Horner's Bible Reading System** — the ten lists, as published
- **Lifeway Research** on why readers abandon plans
  ([research.lifeway.com](https://research.lifeway.com/2021/04/30/the-key-to-life-changing-biblical-engagement/))
- On the Leviticus wall: [exegeticaltools.com](https://exegeticaltools.com/2015/12/20/dont-get-stuck-at-leviticus-on-your-new-bible-reading-plan/),
  and Christianity Today on [planning for endurance rather than speed](https://www.christianitytoday.com/2025/12/bible-in-a-year-slow-reading/)
- **Tyndale's NLT API** — endpoints and limits ([api.nlt.to/documentation](https://api.nlt.to/documentation))

Two caveats I would rather state than bury. The Power-of-4 figures are self-reported
survey correlations, not a controlled trial — the threshold shape is what the design leans
on, not the exact percentages. And the "one in ten finish a one-year plan" figure is
widely repeated but not published by anyone who would know; treat it as folklore that
happens to point the right way.

> *"I have hidden your word in my heart, that I might not sin against you."* — Psalm 119:11
