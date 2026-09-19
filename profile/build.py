#!/usr/bin/env python3
"""Render profile/terminal-{dark,light}.svg from live GitHub data.

Uses only the standard library. Reads GITHUB_TOKEN when present.
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
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("data")


def fetch():
    user = get(f"/users/{LOGIN}")
    repos = [
        r for r in get(f"/users/{LOGIN}/repos?type=owner&per_page=100&sort=pushed")
        if not r["fork"] and not r["archived"] and not r["private"] and r["name"] != ".github"
    ]
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    commits = []
    for r in repos[:8]:
        for c in get(f"/repos/{LOGIN}/{r['name']}/commits?since={since}&per_page=5", []) or []:
            commits.append((c["commit"]["committer"]["date"], r["name"], c["commit"]["message"].split("\n")[0]))
    commits.sort(reverse=True)
    releases = []
    for r in repos:
        rel = get(f"/repos/{LOGIN}/{r['name']}/releases/latest")
        if rel:
            releases.append((rel["published_at"], r["name"], rel["tag_name"]))
    releases.sort(reverse=True)
    sponsors = None
    try:
        data = graphql('{ user(login:"%s"){ sponsors{ totalCount } } }' % LOGIN)
        sponsors = data["user"]["sponsors"]["totalCount"] if data else None
    except Exception:
        pass
    return user, repos, commits, releases, sponsors


def lines(user, repos, commits, releases, sponsors):
    """Return a list of (kind, text). kind is 'cmd' or 'out'."""
    out = []
    who = [user.get("name") or LOGIN]
    for key in ("location", "company"):
        if user.get(key):
            who.append(user[key])
    if user.get("blog"):
        who.append(user["blog"].replace("https://", ""))
    out += [("cmd", "whoami"), ("out", " · ".join(who))]

    out.append(("cmd", "ls ~/projects --sort=stars"))
    top = sorted(repos, key=lambda r: -r["stargazers_count"])[:4]
    w = max(len(r["name"]) for r in top)
    for r in top:
        lang = (r.get("language") or "-")[:6]
        desc = (r.get("description") or "").split(". ")[0].split(" that ")[0]
        desc = desc[:44] + ("…" if len(desc) > 44 else "")
        out.append(("out", f"{r['name']:<{w}}  ★{r['stargazers_count']:<3} {lang:<6} {desc}"))

    out.append(("cmd", "git log --all --since=7.days --oneline | head -5"))
    if commits:
        for date, repo, msg in commits[:5]:
            msg = msg[:58] + ("…" if len(msg) > 58 else "")
            out.append(("out", f"{date[:10]}  {repo:<{w}}  {msg}"))
    else:
        out.append(("out", "(quiet week)"))

    if releases:
        out.append(("cmd", "gh release list --latest"))
        for date, repo, tag in releases[:3]:
            out.append(("out", f"{repo:<{w}}  {tag:<9} {date[:10]}"))

    out.append(("cmd", "gh sponsors"))
    n = "?" if sponsors is None else sponsors
    out.append(("out", f"{n} sponsor{'' if sponsors == 1 else 's'} · github.com/sponsors/{LOGIN}"))

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out += [("cmd", "date -u"), ("out", f"{now} · this file rebuilds itself every 6 hours")]
    return out


THEMES = {
    "dark": dict(bg="#0d1117", frame="#161b22", border="#30363d", text="#c9d1d9", cmd="#e6edf3",
                 prompt="#7ee787", dim="#8b949e", accent="#79c0ff"),
    "light": dict(bg="#ffffff", frame="#f6f8fa", border="#d0d7de", text="#1f2328", cmd="#1f2328",
                  prompt="#1a7f37", dim="#656d76", accent="#0969da"),
}

FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
SIZE = 13.5
LINE = 22
PAD = 20
CHAR = 8.15          # approximate advance width at SIZE, used for typing speed
TYPE_SPEED = 0.045   # seconds per character
PAUSE = 0.35         # seconds after a command before its output


def render(rows, theme):
    t = THEMES[theme]
    width = 820
    header = 36
    height = header + PAD + LINE * (len(rows) + 1) + PAD
    css = []
    body = []
    clock = 0.4
    for i, (kind, text) in enumerate(rows):
        y = header + PAD + LINE * (i + 1) - 6
        safe = html.escape(text)
        if kind == "cmd":
            dur = max(0.3, len(text) * TYPE_SPEED)
            css.append(f".l{i}{{animation:show 0s {clock:.2f}s forwards}}")
            css.append(f".t{i}{{animation:type {dur:.2f}s steps({len(text)},end) {clock:.2f}s forwards}}")
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
    y = header + PAD + LINE * (len(rows) + 1) - 6
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
    print("\n".join(("~ $ " if k == "cmd" else "    ") + t for k, t in rows), file=sys.stderr)


if __name__ == "__main__":
    main()
