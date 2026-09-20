#!/usr/bin/env python3
"""Render profile/terminal-{dark,light}.svg from live GitHub data.

Uses only the standard library. Reads GITHUB_TOKEN. Private contributions
appear when the token belongs to the profile owner, or when the profile
setting "Include private contributions on my profile" is on.
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.error
import urllib.request

LOGIN = "nateships"
API = "https://api.github.com"
OUT = os.path.join(os.path.dirname(__file__), "terminal-{}.svg")
WEEKS = 52

TOKEN = os.environ.get("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": LOGIN}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def get(path, default=None):
    req = urllib.request.Request(API + path, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return default
        raise


def graphql(query):
    if not TOKEN:
        return None
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(API + "/graphql", data=body, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if out.get("errors"):
        print(out["errors"], file=sys.stderr)
    return out.get("data")


def streaks(days):
    """days: list of (date, count) oldest first. Returns (current, longest)."""
    longest = run = 0
    for _, n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    current = 0
    tail = days[:-1] if days and days[-1][1] == 0 else days  # today may still be empty
    for _, n in reversed(tail):
        if not n:
            break
        current += 1
    return current, longest


def contributions():
    to = dt.datetime.now(dt.timezone.utc)
    frm = to - dt.timedelta(days=WEEKS * 7 - 1)
    span = 'from:"%s", to:"%s"' % (frm.strftime("%Y-%m-%dT00:00:00Z"), to.strftime("%Y-%m-%dT%H:%M:%SZ"))
    data = graphql("""{ user(login:"%s"){ contributionsCollection(%s){
        totalCommitContributions totalPullRequestContributions
        totalIssueContributions totalPullRequestReviewContributions
        restrictedContributionsCount
        contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } } } } }"""
                   % (LOGIN, span))
    if not data:
        return None
    c = data["user"]["contributionsCollection"]
    weeks = c["contributionCalendar"]["weeks"][-WEEKS:]
    days = [(d["date"], d["contributionCount"]) for w in weeks for d in w["contributionDays"]]

    # Aliased queries give the private share of every week. GraphQL caps the
    # work per request, so ask for 13 weeks at a time.
    per = {}
    for start in range(0, len(weeks), 13):
        fields = []
        for i, w in enumerate(weeks[start:start + 13], start):
            a, b = w["contributionDays"][0]["date"], w["contributionDays"][-1]["date"]
            fields.append('w%d: contributionsCollection(from:"%sT00:00:00Z", to:"%sT23:59:59Z"){ restrictedContributionsCount }'
                          % (i, a, b))
        data = graphql('{ user(login:"%s"){ %s } }' % (LOGIN, " ".join(fields)))
        per.update((data or {}).get("user") or {})

    series = []
    for i, w in enumerate(weeks):
        total = sum(d["contributionCount"] for d in w["contributionDays"])
        private = min(total, (per.get(f"w{i}") or {}).get("restrictedContributionsCount", 0))
        series.append((w["contributionDays"][0]["date"], total - private, private))

    return dict(
        weeks=series,
        total=c["contributionCalendar"]["totalContributions"],
        private=c["restrictedContributionsCount"],
        commits=c["totalCommitContributions"],
        prs=c["totalPullRequestContributions"],
        issues=c["totalIssueContributions"],
        reviews=c["totalPullRequestReviewContributions"],
        streak=streaks(days),
    )


def fetch():
    user = get(f"/users/{LOGIN}")
    releases = []
    for r in get(f"/users/{LOGIN}/repos?type=owner&per_page=100&sort=pushed"):
        if r["fork"] or r["archived"] or r["private"]:
            continue
        rel = get(f"/repos/{LOGIN}/{r['name']}/releases/latest")
        if rel:
            releases.append((rel["published_at"], r["name"], rel["tag_name"]))
    releases.sort(reverse=True)
    return user, contributions(), releases


def lines(user, contrib, releases):
    """Rows of (kind, payload). kind: cmd, out, chart, rich."""
    out = []
    since = dt.datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
    up = dt.datetime.now(dt.timezone.utc) - since
    years, days = divmod(up.days, 365)
    info = [
        ("title", f"{LOGIN}@github"),
        ("rule", ""),
        ("Name", user.get("name") or LOGIN),
        ("Location", user.get("location") or ""),
        ("Company", user.get("company") or ""),
        ("Site", (user.get("blog") or "").replace("https://", "")),
        ("Uptime", f"{years} years, {days} days"),
    ]
    info = [(k, v) for k, v in info if v or k == "rule"]
    info += [("", "")] * (len(SHIP) - len(info))
    out += [("cmd", "whoami"), ("fetch", list(zip(SHIP, info)))]

    if contrib:
        out.append(("cmd", f"git contributions --last={WEEKS}w --graph"))
        out.append(("chart", contrib))
        public = contrib["total"] - contrib["private"]
        out.append(("rich", [("public", f"public {public:,}"), ("private", f"private {contrib['private']:,}"),
                             (None, f"{contrib['total']:,} total")]))
        cur, longest = contrib["streak"]
        out.append(("out", f"streak {cur} days · longest {longest} days"))

    if releases:
        out.append(("cmd", "gh release list --latest"))
        w = max(len(name) for _, name, _ in releases[:3])
        for date, repo, tag in releases[:3]:
            out.append(("out", f"{repo:<{w}}  {tag:<9} {date[:10]}"))

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out += [("cmd", "date -u"), ("out", f"{now} · this file rebuilds itself every 6 hours")]
    return out


SHIP = [
    r"        |    |    |         ",
    r"       )_)  )_)  )_)        ",
    r"      )___))___))___)\      ",
    r"     )____)____)_____)\\    ",
    r"   _____|____|____|____\\\__ ",
    r"   \                   /    ",
    r" ~~~~~~~~~~~~~~~~~~~~~~~~~~ ",
]

THEMES = {
    "dark": dict(bg="#0d1117", frame="#161b22", border="#30363d", text="#c9d1d9", cmd="#e6edf3",
                 prompt="#7ee787", dim="#8b949e", public="#2ea043", private="#1f6feb"),
    "light": dict(bg="#ffffff", frame="#f6f8fa", border="#d0d7de", text="#1f2328", cmd="#1f2328",
                  prompt="#1a7f37", dim="#656d76", public="#1a7f37", private="#0969da"),
}

FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
SIZE = 13.5
LINE = 22
PAD = 20
CHAR = 8.15          # approximate advance width at SIZE
TYPE_SPEED = 0.045   # seconds per character
PAUSE = 0.35         # seconds after a command before its output
CHART_LINES = 6      # vertical space a chart takes, in text lines


def chart(c, i, x, y, w, h, clock, t, css):
    """Stacked weekly bars: public from the baseline, private on top."""
    weeks = c["weeks"]
    n = len(weeks)
    gap = 2
    bw = (w - gap * (n - 1)) / n
    top = max(a + b for _, a, b in weeks) or 1
    label_h = 14
    plot_h = h - label_h
    base = y + plot_h
    scale = plot_h / top
    parts = [f'<g class="l{i}" opacity="0">',
             f'<line x1="{x}" y1="{base + 0.5}" x2="{x + w}" y2="{base + 0.5}" stroke="{t["border"]}"/>']
    css.append(f".l{i}{{animation:show 0s {clock:.2f}s forwards}}")
    css.append(f".b{i}{{transform-box:fill-box;transform-origin:bottom;transform:scaleY(0);"
               f"animation:grow .5s cubic-bezier(.2,.7,.2,1) forwards}}")
    last_month = None
    for k, (date, pub, prv) in enumerate(weeks):
        bx = x + k * (bw + gap)
        ph = pub * scale
        vh = prv * scale
        rects = []
        if ph >= 1:
            rects.append(f'<rect x="{bx:.1f}" y="{base - ph:.1f}" width="{bw:.1f}" height="{ph:.1f}" rx="2" fill="{t["public"]}"/>')
        if vh >= 1:
            top_y = base - ph - (gap if ph >= 1 else 0) - vh
            rects.append(f'<rect x="{bx:.1f}" y="{top_y:.1f}" width="{bw:.1f}" height="{vh:.1f}" rx="2" fill="{t["private"]}"/>')
        if rects:
            parts.append(f'<g class="b{i}" style="animation-delay:{clock + k * 0.015:.3f}s">{"".join(rects)}</g>')
        month = date[:7]
        if month != last_month and k > 0:
            parts.append(f'<text x="{bx:.1f}" y="{base + label_h - 1}" fill="{t["dim"]}" font-size="10">'
                         f'{dt.date.fromisoformat(date).strftime("%b")}</text>')
        last_month = month
    parts.append("</g>")
    return "".join(parts)


def fetch_block(rows, i, x, y, clock, t, css):
    """Art on the left, label/value pairs on the right, one line at a time."""
    parts = []
    col = x + (len(SHIP[0]) + 2) * CHAR
    for k, (art, (label, value)) in enumerate(rows):
        cls = f"l{i}_{k}"
        css.append(f".{cls}{{animation:show 0s {clock + k * 0.06:.2f}s forwards}}")
        ly = y + k * LINE
        water = art.strip().startswith("~")
        line = f'<text x="{x}" y="{ly}" fill="{t["private" if water else "prompt"]}">{html.escape(art)}</text>'
        if label == "title":
            line += f'<text x="{col:.1f}" y="{ly}" fill="{t["cmd"]}" font-weight="bold">{html.escape(value)}</text>'
        elif label == "rule":
            line += f'<text x="{col:.1f}" y="{ly}" fill="{t["dim"]}">{"─" * 16}</text>'
        elif label:
            line += (f'<text x="{col:.1f}" y="{ly}" fill="{t["prompt"]}">{html.escape(label)}</text>'
                     f'<text x="{col + 10 * CHAR:.1f}" y="{ly}" fill="{t["text"]}">{html.escape(value)}</text>')
        parts.append(f'<g class="{cls}" opacity="0">{line}</g>')
    return "".join(parts)


def rich(segments, i, x, y, t):
    """Text with small color swatches: [(theme_color_key or None, text), ...]."""
    parts = [f'<g class="l{i}" opacity="0">']
    for j, (key, text) in enumerate(segments):
        if j:
            parts.append(f'<text x="{x:.1f}" y="{y}" fill="{t["dim"]}">·</text>')
            x += 2 * CHAR
        if key:
            parts.append(f'<rect x="{x:.1f}" y="{y - 10}" width="9" height="9" rx="2" fill="{t[key]}"/>')
            x += 2 * CHAR
        parts.append(f'<text x="{x:.1f}" y="{y}" fill="{t["text"]}">{html.escape(text)}</text>')
        x += (len(text) + 1) * CHAR
    parts.append("</g>")
    return "".join(parts)


def render(rows, theme):
    t = THEMES[theme]
    width = 820
    header = 36
    n = sum(CHART_LINES if k == "chart" else len(SHIP) if k == "fetch" else 1 for k, _ in rows) + 1
    height = header + PAD + LINE * n + PAD
    css = []
    body = []
    clock = 0.4
    row = 0
    for i, (kind, payload) in enumerate(rows):
        row += 1
        y = header + PAD + LINE * row - 6
        if kind == "chart":
            row += CHART_LINES - 1
            body.append(chart(payload, i, PAD, y - LINE + 8, width - 2 * PAD, LINE * CHART_LINES - 14, clock, t, css))
            clock += 0.9
            continue
        if kind == "fetch":
            row += len(SHIP) - 1
            body.append(fetch_block(payload, i, PAD, y, clock, t, css))
            clock += 0.06 * len(payload) + 0.2
            continue
        if kind == "rich":
            css.append(f".l{i}{{animation:show 0s {clock:.2f}s forwards}}")
            body.append(rich(payload, i, PAD, y, t))
            clock += 0.08
            continue
        safe = html.escape(payload)
        if kind == "cmd":
            dur = max(0.3, len(payload) * TYPE_SPEED)
            css.append(f".l{i}{{animation:show 0s {clock:.2f}s forwards}}")
            css.append(f".t{i}{{animation:type {dur:.2f}s steps({len(payload)},end) {clock:.2f}s forwards}}")
            body.append(
                f'<g class="l{i}" opacity="0"><text x="{PAD}" y="{y}" fill="{t["prompt"]}">~ $</text>'
                f'<text class="t{i}" x="{PAD + 4 * CHAR}" y="{y}" fill="{t["cmd"]}" '
                f'style="clip-path:inset(0 100% 0 0)">{safe}</text></g>'
            )
            clock += dur + PAUSE
        else:
            css.append(f".l{i}{{animation:show 0s {clock:.2f}s forwards}}")
            body.append(f'<text class="l{i}" opacity="0" x="{PAD}" y="{y}" fill="{t["text"]}">{safe}</text>')
            clock += 0.08
    row += 1
    y = header + PAD + LINE * row - 6
    css.append(f".l{len(rows)}{{animation:show 0s {clock:.2f}s forwards}}")
    body.append(
        f'<g class="l{len(rows)}" opacity="0"><text x="{PAD}" y="{y}" fill="{t["prompt"]}">~ $</text>'
        f'<rect class="cursor" x="{PAD + 4 * CHAR}" y="{y - 13}" width="8" height="16" fill="{t["cmd"]}"/></g>'
    )
    style = "".join(css)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="{FONT}" font-size="{SIZE}">
<title>{LOGIN} terminal</title>
<style>
@keyframes show{{to{{opacity:1}}}}
@keyframes type{{to{{clip-path:inset(0 0 0 0)}}}}
@keyframes blink{{50%{{opacity:0}}}}
@keyframes grow{{to{{transform:scaleY(1)}}}}
.cursor{{animation:blink 1s step-end infinite}}
text{{white-space:pre}}
{style}
</style>
<rect width="{width}" height="{height}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>
<path d="M0 10a10 10 0 0 1 10-10h{width - 20}a10 10 0 0 1 10 10v{header - 10}H0z" fill="{t["frame"]}"/>
<circle cx="20" cy="18" r="6" fill="#ff5f57"/><circle cx="40" cy="18" r="6" fill="#febc2e"/><circle cx="60" cy="18" r="6" fill="#28c840"/>
<text x="{width / 2}" y="23" text-anchor="middle" fill="{t["dim"]}" font-size="12">{LOGIN} — zsh — {width}×{height}</text>
{"".join(body)}
</svg>
'''


def main():
    rows = lines(*fetch())
    for theme in THEMES:
        with open(OUT.format(theme), "w") as f:
            f.write(render(rows, theme))
    for kind, payload in rows:
        if kind == "cmd":
            print("~ $ " + payload, file=sys.stderr)
        elif kind == "out":
            print("    " + payload, file=sys.stderr)
        elif kind == "rich":
            print("    " + " · ".join(s for _, s in payload), file=sys.stderr)
        elif kind == "fetch":
            for art, (label, value) in payload:
                print(f"    {art}  {label:<9} {value}".rstrip(), file=sys.stderr)
        else:
            print(f"    [chart: {len(payload['weeks'])} weeks, total {payload['total']}, private {payload['private']}]",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
