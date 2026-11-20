"""Shared design tokens and SVG helpers for the profile graphics.

Every graphic is a plain SVG that GitHub shows through an <img> tag, so:
no scripts, no web fonts, no external images. Motion is CSS keyframes and SMIL.
"""

from html import escape

MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

# Timing-screen colours: purple = fastest overall, green = personal best,
# yellow = slower, red = the signal colour (start lights, braking, the car).
THEMES = {
    "dark": dict(
        bg="#0D1117", ink="#E6EDF3", dim="#8B949E", mute="#6E7681", hair="#30363D", faint="#1C2128",
        accent="#FF4A2B", purple="#B98CFF", green="#3FB950", yellow="#D29922",
        pod="#0A0D11", pod_edge="#30363D", lamp_off="#20262E", lamp_on="#FF2A17",
    ),
    "light": dict(
        bg="#FFFFFF", ink="#1F2328", dim="#59636E", mute="#818B98", hair="#D1D9E0", faint="#EEF1F4",
        accent="#E0321A", purple="#8250DF", green="#1A7F37", yellow="#9A6700",
        pod="#1F2328", pod_edge="#1F2328", lamp_off="#353C44", lamp_on="#FF2A17",
    ),
}

BASE_CSS = """
text{font-family:%(mono)s}
@media (prefers-reduced-motion: reduce){*{animation:none!important}}
""" % {"mono": MONO}


def esc(s):
    return escape(str(s), quote=True)


def f(x):
    """Short number formatting for path data."""
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


def svg(w, h, title, desc, css, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">'
        f"<title id=\"t\">{esc(title)}</title><desc id=\"d\">{esc(desc)}</desc>"
        f"<style>{BASE_CSS}{css}</style>{''.join(body)}</svg>\n"
    )


def text(x, y, s, size=14, fill="#000", anchor="start", weight=400, spacing=0, extra=""):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return (
        f'<text x="{f(x)}" y="{f(y)}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}"{ls}{extra}>{esc(s)}</text>'
    )


SECTOR_CSS = """
.sh-fill{transform-box:fill-box;transform-origin:0 50%%;animation:sh-run 7s cubic-bezier(.7,0,.2,1) infinite}
@keyframes sh-run{0%%{transform:scaleX(0);fill:%(accent)s}45%%{transform:scaleX(1);fill:%(accent)s}
55%%{fill:%(color)s}88%%{transform:scaleX(1);opacity:1;fill:%(color)s}100%%{transform:scaleX(1);opacity:0;fill:%(color)s}}
.sh-in{animation:sh-in .8s cubic-bezier(.2,.7,.2,1) both}
@keyframes sh-in{from{opacity:0;transform:translateX(-14px)}}
"""


def sector_header(t, n, title, kicker, color_key="purple", y=0, w=1200):
    """The 'S1 / S2 / S3' strip used to open each section.

    Returns (css, body) so it can be dropped into a larger SVG.
    """
    css = SECTOR_CSS % {"accent": t["accent"], "color": t[color_key]}
    body = [
        f'<g transform="translate(0 {y})">',
        f'<g class="sh-in">',
        f'<rect x="40.5" y="22.5" width="52" height="34" rx="3" fill="none" stroke="{t["hair"]}"/>',
        text(66.5, 45.5, f"S{n}", 16, t[color_key], "middle", 700, 1),
        text(114, 47, title, 26, t["ink"], "start", 600, 5),
        "</g>",
        text(w - 40, 46, kicker, 13, t["dim"], "end", 400, 2, ' class="sh-in" style="animation-delay:.15s"'),
        f'<rect x="40" y="76" width="{w - 80}" height="2" fill="{t["faint"]}"/>',
        f'<rect class="sh-fill" x="40" y="76" width="{w - 80}" height="2" fill="{t["accent"]}"/>',
        "</g>",
    ]
    return css, body
