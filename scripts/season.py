"""Draws the last 12 months of contributions as a race calendar.

    python scripts/season.py --user Sackedball --out dist

Every day with contributions is a "round": a spike on the season timeline.
The biggest day is marked purple (fastest lap). Runs daily in GitHub Actions
with GITHUB_TOKEN; without a token it reads the public contributions page.
Standard library only.
"""

import argparse
import datetime as dt
import json
import math
import os
import re
import urllib.request

from kit import THEMES, f, sector_header, svg, text

QUERY = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{
totalContributions weeks{contributionDays{date contributionCount}}}}}}"""


def fetch_graphql(user, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-season-chart"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [(d["date"], d["contributionCount"]) for w in weeks for d in w["contributionDays"]]


def parse_page(html):
    by_id = {cid: d for d, cid in re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"\s+id="([^"]+)"', html)}
    counts = {}
    for cid, label in re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', html):
        if cid in by_id:
            m = re.match(r"(\d+) contribution", label)
            counts[cid] = int(m.group(1)) if m else 0
    return sorted((d, counts.get(cid, 0)) for cid, d in by_id.items())


def fetch_page(user):
    req = urllib.request.Request(f"https://github.com/users/{user}/contributions",
                                 headers={"User-Agent": "profile-season-chart"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return parse_page(r.read().decode("utf-8"))


def render(t, days):
    W = 1200
    days = [(dt.date.fromisoformat(d), c) for d, c in days]
    first, last = days[0][0], days[-1][0]
    span = max((last - first).days, 1)
    total = sum(c for _, c in days)
    active = [(d, c) for d, c in days if c > 0]
    best = max(active, key=lambda x: x[1]) if active else None

    kicker = f"{total} CONTRIBUTIONS  /  {len(active)} ACTIVE DAYS  /  LAST 12 MONTHS"
    css, b = sector_header(t, 3, "THE SEASON SO FAR", kicker, "yellow")
    css += """
.sp{transform-box:fill-box;transform-origin:50% 100%;animation:sp 9s cubic-bezier(.2,.9,.2,1) infinite both}
@keyframes sp{0%{transform:scaleY(0)}6%{transform:scaleY(1)}92%{transform:scaleY(1);opacity:1}100%{transform:scaleY(1);opacity:0}}
.lb{animation:lb 9s linear infinite both}
@keyframes lb{0%{opacity:0}5%{opacity:1}92%{opacity:1}100%{opacity:0}}
.cur{animation:cur 9s linear infinite}
@keyframes cur{from{transform:translateX(0)}to{transform:translateX(1080px)}}
.base{transform-box:fill-box;transform-origin:0 50%;animation:base 1.4s cubic-bezier(.6,0,.2,1) both}
@keyframes base{from{transform:scaleX(0)}}
"""
    x0, x1, base_y, top_y = 60, 1140, 262, 132
    H = 360

    def X(d):
        return x0 + (x1 - x0) * (d - first).days / span

    # baseline, week ticks, month labels
    b.append(f'<rect class="base" x="{x0}" y="{base_y}" width="{x1 - x0}" height="1" fill="{t["hair"]}"/>')
    d = first
    while d <= last:
        x = X(d)
        b.append(f'<rect x="{f(x)}" y="{base_y + 4}" width="1" height="4" fill="{t["faint"]}"/>')
        d += dt.timedelta(days=7)
    d = dt.date(first.year, first.month, 1)
    while d <= last:
        if d >= first:
            x = X(d)
            b.append(f'<rect x="{f(x)}" y="{base_y + 2}" width="1" height="10" fill="{t["hair"]}"/>')
            b.append(text(x + 5, base_y + 24, d.strftime("%b").upper(), 11, t["mute"], spacing=2))
        d = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)

    if not active:
        b.append(text(W / 2, 210, "QUIET SEASON SO FAR. THE GARAGE IS OPEN.", 16, t["dim"], "middle", spacing=3))
    else:
        peak = math.sqrt(best[1])
        placed = []
        for day, c in active:
            x = X(day)
            h = 14 + (base_y - top_y - 14) * math.sqrt(c) / peak
            is_best = (day, c) == best
            col = t["purple"] if is_best else t["accent"]
            delay = 9 * (x - x0) / (x1 - x0)
            b.append(f'<g class="sp" style="animation-delay:{delay:.2f}s">'
                     f'<rect x="{f(x - 2)}" y="{f(base_y - h)}" width="4" height="{f(h)}" fill="{col}"/>'
                     f'<circle cx="{f(x)}" cy="{f(base_y - h)}" r="5" fill="{col}"/></g>')
            label_w = 8 * len(str(c)) + 6
            if all(abs(x - px) > (label_w + pw) / 2 + 4 for px, pw in placed):
                placed.append((x, label_w))
                b.append(text(x, base_y - h - 14, c, 13, col, "middle", 700,
                              extra=f' class="lb" style="animation-delay:{delay:.2f}s"'))

        # rounds legend: biggest days, in date order
        top = sorted(sorted(active, key=lambda x: -x[1])[:6])
        b.append(text(40, 326, "ROUNDS", 12, t["dim"], weight=700, spacing=3))
        lx = 150
        for i, (day, c) in enumerate(top):
            col = t["purple"] if (day, c) == best else t["accent"]
            b.append(f'<rect x="{lx}" y="316" width="8" height="8" fill="{col}"/>')
            b.append(text(lx + 16, 325, f"R{i + 1:02d}  {day.strftime('%b %d').upper()}", 12, t["ink"], spacing=1))
            b.append(text(lx + 16, 343, f"{c} contribution{'s' * (c != 1)}", 11, t["mute"]))
            lx += 168

    b.append(f'<g class="cur"><rect x="{x0}" y="{top_y - 14}" width="1" height="{base_y - top_y + 14}" '
             f'fill="{t["dim"]}" opacity=".5"/></g>')

    desc = f"{total} contributions in the last 12 months across {len(active)} active days."
    if best:
        desc += f" Biggest day: {best[0].strftime('%B %d, %Y')} with {best[1]}."
    return svg(W, H, "The season so far", desc, css, b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--out", default="dist")
    ap.add_argument("--html", help="read a saved contributions page instead of fetching")
    a = ap.parse_args()

    if a.html:
        with open(a.html, encoding="utf-8") as fh:
            days = parse_page(fh.read())
    else:
        days = []
        if os.environ.get("GITHUB_TOKEN"):
            try:
                days = fetch_graphql(a.user, os.environ["GITHUB_TOKEN"])
            except Exception as e:  # fall back to the public page
                print("GraphQL failed, reading the public page instead:", e)
        if not days:
            days = fetch_page(a.user)
    if not days:
        raise SystemExit("no contribution data found")

    os.makedirs(a.out, exist_ok=True)
    for name, t in THEMES.items():
        path = os.path.join(a.out, f"season-{name}.svg")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render(t, days))
        print("wrote", path)
    print(f"{len(days)} days, {sum(c for _, c in days)} contributions")


if __name__ == "__main__":
    main()
