"""Draws the README graphics: docs/hero.svg, privacy.svg, proof.svg, handoff.svg.

    python docs/src/make_visuals.py            # writes the four SVGs into docs/
    python docs/src/make_visuals.py --freeze 6 --out /tmp/x   # still frames at t = 6 s, for checking

Needs fonttools and uharfbuzz (any Python; not part of the app's .venv). The two typefaces
(Instrument Sans and JetBrains Mono, both SIL Open Font License) are downloaded into
docs/src/fonts/ on first run.

Why text is drawn as outlines: GitHub shows README images with a policy that blocks fonts
inside SVGs, and system fonts differ per device, so live text would look different (or
overflow) for every visitor. Outlines look the same everywhere. Each SVG keeps a <title>
and aria-label, and the README gives every image alt text.

One look for all four: near-black cards, warm white text, and a single accent, the orange
of the macOS "microphone in use" dot.
"""
import argparse
import urllib.request
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
FONTS = {
    "S": ("InstrumentSans.ttf", "https://github.com/google/fonts/raw/main/ofl/instrumentsans/InstrumentSans%5Bwdth%2Cwght%5D.ttf"),
    "M": ("JetBrainsMono.ttf", "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"),
}

# Palette
BG, PANEL, RAISED = "#0C0C0E", "#131315", "#1D1D20"
LINE = "#2A2A2E"          # hairlines and outlines
INK, SOFT, FAINT = "#F4F1EC", "#A7A29A", "#5E5B56"   # text, secondary text, decoration only
MIC = "#FF9F0A"           # the one accent
MIC_INK = "#1F1300"       # text on the accent

EASE = "cubic-bezier(0.16, 1, 0.3, 1)"  # exponential ease-out


class Doc:
    """One SVG. Glyph outlines are stored once in <defs> and reused."""

    def __init__(self, w, h, title, label, css):
        self.w, self.h, self.title, self.label, self.css = w, h, title, label, css
        self.defs, self.ids, self.body, self._fonts = [], {}, [], {}

    def _font(self, key, weight):
        if (key, weight) not in self._fonts:
            name, url = FONTS[key]
            path = HERE / "fonts" / name
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(url, path)
            face = hb.Face(hb.Blob.from_file_path(str(path)))
            font = hb.Font(face)
            font.set_variations({"wght": weight})
            self._fonts[(key, weight)] = (font, face.upem)
        return self._fonts[(key, weight)]

    def text(self, x, y, s, size=15, weight=400, fill=INK, font="S", anchor="start", track=0.0, cls=None):
        """Text as outlines. Returns the width in px. track is letter-spacing in em."""
        f, upem = self._font(font, weight)
        buf = hb.Buffer()
        buf.add_str(s)
        buf.guess_segment_properties()
        hb.shape(f, buf, {"liga": font != "M", "calt": font != "M"})
        uses, pen_x = [], 0.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            key = (font, weight, info.codepoint)
            if key not in self.ids:
                pen = SVGPathPen(None, ntos=lambda v: str(int(round(v))))
                f.draw_glyph_with_pen(info.codepoint, pen)
                d = pen.getCommands()
                self.ids[key] = None
                if d:
                    self.ids[key] = f"g{len(self.defs)}"
                    self.defs.append(f'<path id="{self.ids[key]}" d="{d}"/>')
            if self.ids[key]:
                uses.append(f'<use href="#{self.ids[key]}" x="{round(pen_x + pos.x_offset)}"/>')
            pen_x += pos.x_advance + track * upem
        scale = size / upem
        width = (pen_x - track * upem) * scale
        x0 = x - {"start": 0, "middle": width / 2, "end": width}[anchor]
        c = f' class="{cls}"' if cls else ""
        self.body.append(
            f'<g{c} fill="{fill}" transform="translate({x0:.1f} {y}) scale({scale:.5f} {-scale:.5f})">{"".join(uses)}</g>'
        )
        return width

    def add(self, s):
        self.body.append(s)

    def open(self, cls=None, extra=""):
        self.body.append(f'<g{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}{" " + extra if extra else ""}>')

    def close(self):
        self.body.append("</g>")

    def render(self, freeze=None):
        css = self.css
        if freeze is not None:
            css += f" * {{ animation-play-state: paused !important; animation-delay: -{freeze}s !important; }}"
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
            f'role="img" aria-label="{self.label}">\n<title>{self.title}</title>\n'
            f'<defs>{"".join(self.defs)}</defs>\n<style>{css}</style>\n'
            f'<rect width="{self.w}" height="{self.h}" rx="24" fill="{BG}"/>\n'
            f'<rect x="0.5" y="0.5" width="{self.w - 1}" height="{self.h - 1}" rx="23.5" fill="none" stroke="{LINE}"/>\n'
            + "\n".join(self.body) + "\n</svg>\n"
        )


def on(name, start, end, total, fade=0.25, rest=0):
    """Keyframes: opacity `rest` outside [start, end] seconds of a `total`-second loop, 1 inside."""
    p = lambda t: f"{max(0, min(100, t / total * 100)):.2f}%"
    return (f"@keyframes {name} {{ 0%, {p(start)} {{ opacity: {rest}; }} {p(start + fade)}, {p(end)} {{ opacity: 1; }} "
            f"{p(end + fade)}, 100% {{ opacity: {rest}; }} }}")


def off(name, start, end, total, fade=0.25):
    """Keyframes: visible except between start and end."""
    p = lambda t: f"{max(0, min(100, t / total * 100)):.2f}%"
    return (f"@keyframes {name} {{ 0%, {p(start)} {{ opacity: 1; }} {p(start + fade)}, {p(end)} {{ opacity: 0; }} "
            f"{p(end + fade)}, 100% {{ opacity: 1; }} }}")


def reduced(hide, show):
    return (f"@media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} "
            f"{', '.join(hide)} {{ opacity: 0; }} {', '.join(show)} {{ opacity: 1; }} }}")


# ---- drawn icons (1.75 px strokes on a 24 px grid, origin = top-left) -----------------
def mic_icon(x, y, color=INK, s=1.0):
    return (f'<g transform="translate({x} {y}) scale({s})" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round">'
            f'<rect x="8.5" y="2" width="7" height="12" rx="3.5"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4"/></g>')


def chip_icon(x, y, color=INK):
    return (f'<g transform="translate({x} {y})" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round">'
            f'<rect x="5" y="5" width="14" height="14" rx="3"/><rect x="9.5" y="9.5" width="5" height="5" rx="1" fill="{color}" stroke="none"/>'
            f'<path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/></g>')


def caret_icon(x, y, color=INK):
    return (f'<g transform="translate({x} {y})" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round">'
            f'<path d="M8 3h1.5A2.5 2.5 0 0 1 12 5.500A2.500 2.500 0 0 1 14.500 3H16M12 5.500v13M8 21h1.500A2.500 2.500 0 0 0 12 18.500A2.500 2.500 0 0 0 14.500 21H16"/></g>')


def option_glyph(x, y, color=INK, s=1.0):
    """The Option key symbol, drawn (28 x 20 at s=1)."""
    return (f'<g transform="translate({x} {y}) scale({s})" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M0 0h8l10 20h10M17 0h11"/></g>')


def window_dots(x, y):
    return "".join(f'<circle cx="{x + i * 16}" cy="{y}" r="4.5" fill="{LINE}"/>' for i in range(3))


# ======================================================================= hero
def hero():
    T = 9.0  # 0-1.2 idle, 1.2-4.6 holding the key, 4.6-5.6 transcribing, 5.6-8.6 pasted
    css = " ".join([
        on("hold", 1.2, 4.6, T, 0.12), off("idle", 1.2, 8.6, T, 0.12), on("work", 4.72, 5.5, T, 0.12),
        on("done", 5.62, 8.6, T, 0.2), off("micoff", 1.2, 4.6, T, 0.12),
        "@keyframes press { 0%, 13.2% { transform: translateY(0); } 14%, 51% { transform: translateY(5px); } 52.2%, 100% { transform: translateY(0); } }",
        "@keyframes land { 0%, 62.4% { transform: translateY(8px); } 66%, 100% { transform: translateY(0); } }",
        "@keyframes wave { from { transform: scaleY(0.18); } to { transform: scaleY(1); } }",
        "@keyframes blink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }",
        "@keyframes dots { 0%, 100% { opacity: 0.25; } 50% { opacity: 1; } }",
        f".hold {{ animation: hold {T}s infinite; }} .idle {{ animation: idle {T}s infinite; }} .work {{ animation: work {T}s infinite; }}",
        f".done {{ animation: done {T}s infinite; }} .micoff {{ animation: micoff {T}s infinite; }}",
        f".press {{ animation: press {T}s {EASE} infinite; }} .land {{ animation: land {T}s {EASE} infinite; }}",
        ".bar { animation: wave 0.62s ease-in-out infinite alternate; transform-box: fill-box; transform-origin: center; }",
        ".blink { animation: blink 1.1s infinite; } .dot { animation: dots 0.9s ease-in-out infinite; }",
        reduced([".hold", ".idle", ".work", ".micoff"], [".done"]),
    ])
    d = Doc(1000, 560, "VoiceFlow: private dictation you can verify",
            "VoiceFlow. Private dictation you can verify. Hold right Option and speak: the microphone is on only while "
            "the key is down, Whisper transcribes on your Mac, and the sentence is pasted at your cursor in about 1.3 seconds.", css)

    d.add(f'<circle cx="70" cy="70" r="5.5" fill="{MIC}"/>')
    d.text(86, 76, "VoiceFlow", 18, 600)
    d.text(64, 156, "Private dictation", 52, 600, track=-0.025)
    d.text(64, 214, "you can verify.", 52, 600, track=-0.025)
    d.text(64, 258, "Hold right Option, speak, let go. Whisper runs on your Mac’s GPU and the text", 17.5, 400, SOFT)
    d.text(64, 284, "lands at your cursor. No cloud, no account, no history.", 17.5, 400, SOFT)

    # the key
    d.open("press")
    d.add(f'<rect x="64" y="336" width="124" height="112" rx="20" fill="#08080A"/>')
    d.add(f'<rect x="64" y="330" width="124" height="112" rx="20" fill="{RAISED}" stroke="{LINE}"/>')
    d.add(f'<rect class="hold" x="65" y="331" width="122" height="110" rx="19" fill="none" stroke="{MIC}" stroke-width="2"/>')
    d.add(option_glyph(140, 352, INK, 1.0))
    d.text(84, 420, "option", 15, 500, SOFT)
    d.close()

    # the text field of whatever app has focus
    d.add(f'<rect x="212" y="330" width="724" height="118" rx="20" fill="{PANEL}" stroke="{LINE}"/>')
    # microphone indicator, top right: the privacy story in one dot
    d.open("micoff")
    w = d.text(912, 363, "microphone off", 13.5, 500, SOFT, anchor="end")
    d.add(f'<circle cx="{912 - w - 13:.1f}" cy="358.5" r="4.5" fill="none" stroke="{SOFT}" stroke-width="1.5"/>')
    d.close()
    d.open("hold")
    w = d.text(912, 363, "microphone on", 13.5, 500, MIC, anchor="end")
    d.add(f'<circle cx="{912 - w - 13:.1f}" cy="358.5" r="5" fill="{MIC}"/>')
    d.close()

    d.text(238, 408, "›", 21, 400, MIC, font="M")
    # idle: a caret waiting
    d.add(f'<g class="idle"><rect class="blink" x="264" y="389" width="10" height="24" rx="1.5" fill="{INK}"/></g>')
    # holding: your voice
    heights = [14, 26, 40, 30, 52, 44, 64, 50, 70, 58, 74, 60, 68, 48, 62, 44, 56, 36, 48, 30, 40, 24, 32, 18, 24, 14, 18, 10]
    d.open("hold", f'fill="{MIC}"')
    for i, hgt in enumerate(heights):
        d.add(f'<rect class="bar" x="{264 + i * 13}" y="{400 - hgt / 2:.0f}" width="5" height="{hgt}" rx="2.5" style="animation-delay:-{(i * 0.37) % 0.62:.2f}s"/>')
    d.close()
    # transcribing
    d.open("work", f'fill="{INK}"')
    for i in range(3):
        d.add(f'<circle class="dot" cx="{270 + i * 16}" cy="401" r="4" style="animation-delay:-{0.6 - i * 0.18:.2f}s"/>')
    d.close()
    # pasted
    d.open("done")
    d.open("land")
    w = d.text(264, 408, "Refactor the login flow and add tests for the edge cases.", 18, 400, INK, font="M")
    d.add(f'<rect class="blink" x="{264 + w + 4:.0f}" y="389" width="10" height="24" rx="1.5" fill="{INK}"/>')
    d.close()
    d.close()

    # state line under the field
    d.text(64, 480, "hold right Option", 13.5, 500, SOFT)
    for cls, s in (("idle", "Ready in any app"), ("hold", "Listening while the key is down"),
                   ("work", "Transcribing on this Mac"), ("done", "Pasted in 1.3 s. You press Enter yourself.")):
        d.text(212, 480, s, 13.5, 500, SOFT if cls != "hold" else MIC, cls=cls)

    d.add(f'<line x1="64" y1="508" x2="936" y2="508" stroke="{LINE}"/>')
    x = 64
    for i, s in enumerate(("Works with Wi-Fi off", "Nothing is saved", "Free and open source")):
        if i:
            d.add(f'<circle cx="{x + 14}" cy="528" r="1.8" fill="{FAINT}"/>')
            x += 28
        x += d.text(x, 533, s, 13.5, 500, SOFT)
    return d


# ==================================================================== privacy
def privacy():
    css = " ".join([
        "@keyframes travel { 0% { transform: translateX(0); opacity: 0; } 8% { opacity: 1; } 46% { transform: translateX(222px); } "
        "54% { transform: translateX(222px); } 92% { opacity: 1; } 100% { transform: translateX(444px); opacity: 0; } }",
        f".travel {{ animation: travel 4.2s {EASE} infinite; }}",
        "@media (prefers-reduced-motion: reduce) { .travel { animation: none; opacity: 0; } }",
    ])
    d = Doc(1000, 470, "Everything stays on your Mac",
            "Privacy diagram. Inside your Mac: the microphone, Whisper on the GPU and your cursor. Audio stays in memory and is "
            "gone after use, text is never written to a history file, the clipboard goes to your own devices only. "
            "The line to the internet is cut: zero connections while it runs.", css)

    d.add(f'<rect x="40" y="40" width="664" height="390" rx="22" fill="{PANEL}" stroke="#3A3A3F"/>')
    d.text(72, 86, "Your Mac", 17, 600)
    d.text(672, 86, "everything happens here", 13.5, 500, SOFT, anchor="end")

    y = 176
    d.add(f'<line x1="150" y1="{y}" x2="594" y2="{y}" stroke="#3A3A3F" stroke-width="1.5"/>')
    d.add(f'<circle class="travel" cx="150" cy="{y}" r="5" fill="{MIC}"/>')
    stations = [
        (150, mic_icon, "Microphone", "only while you hold the key"),
        (372, chip_icon, "Whisper on the GPU", "open model, runs offline"),
        (594, caret_icon, "Your cursor", "pasted; you press Enter"),
    ]
    for x, icon, name, sub in stations:
        d.add(f'<circle cx="{x}" cy="{y}" r="27" fill="{RAISED}" stroke="#3A3A3F"/>')
        d.add(icon(x - 12, y - 12))
        d.text(x, y + 62, name, 16, 600, anchor="middle")
        d.text(x, y + 84, sub, 13.5, 400, SOFT, anchor="middle")

    d.add(f'<line x1="72" y1="312" x2="672" y2="312" stroke="{LINE}"/>')
    for x, name, sub in ((72, "Audio", "in memory, gone after use"), (290, "Text", "no history file, ever"),
                         (490, "Clipboard", "your own devices only")):
        d.text(x, 352, name, 15, 600)
        d.text(x, 376, sub, 13.5, 400, SOFT)
    d.text(72, 406, "The log keeps timings and length. Never a word you said.", 13.5, 400, SOFT)

    # the internet: a line that never connects
    d.add(f'<line x1="704" y1="{y}" x2="748" y2="{y}" stroke="{FAINT}" stroke-width="1.5" stroke-dasharray="3 7" stroke-linecap="round"/>')
    d.add(f'<line x1="760" y1="{y - 11}" x2="760" y2="{y + 11}" stroke="{MIC}" stroke-width="2.5" stroke-linecap="round"/>')
    d.add(f'<path transform="translate(800 {y - 44})" d="M30 80h84a24 24 0 0 0 4-47.700a34 34 0 0 0-65-9.300a26 26 0 0 0-23 57z" '
          f'fill="none" stroke="{FAINT}" stroke-width="1.5" stroke-dasharray="4 6"/>')
    d.text(874, y + 62, "The internet", 16, 600, SOFT, anchor="middle")
    d.text(874, y + 96, "0", 30, 600, MIC, anchor="middle")
    d.text(874, y + 120, "connections while it runs", 13.5, 400, SOFT, anchor="middle")
    return d


# ====================================================================== proof
def proof():
    T = 10.0
    css = " ".join([
        on("c1", 0.5, 9.4, T, 0.3), on("o1", 1.9, 9.4, T, 0.4), on("c2", 4.0, 9.4, T, 0.3), on("o2", 5.2, 9.4, T, 0.4),
        "@keyframes blink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }",
        " ".join(f".{c} {{ animation: {c} {T}s infinite; }}" for c in ("c1", "o1", "c2", "o2")),
        ".blink { animation: blink 1.1s infinite; }",
        reduced([], [".c1", ".o1", ".c2", ".o2"]),
    ])
    d = Doc(1000, 400, "Check it yourself",
            "A terminal. The command lsof, listing VoiceFlow's network connections, prints nothing: zero open connections. "
            "The last line of the log reads 4.3s audio, 1.3s, 54 characters: timings and length, never your words.", css)
    d.add(f'<rect x="40" y="40" width="920" height="320" rx="18" fill="{PANEL}" stroke="{LINE}"/>')
    d.add(window_dots(68, 68))
    d.text(500, 73, "Terminal", 13.5, 500, SOFT, anchor="middle")
    d.add(f'<line x1="40" y1="96" x2="960" y2="96" stroke="{LINE}"/>')

    def cmd(y, s, cls):
        d.open(cls)
        d.text(72, y, "$", 15.5, 400, MIC, font="M")
        d.text(96, y, s, 15.5, 400, INK, font="M")
        d.close()

    cmd(142, 'lsof -nP -a -i -p "$(pgrep -f VoiceFlow/voiceflow.py)"', "c1")
    d.open("o1")
    d.text(96, 174, "Prints nothing. VoiceFlow has no open network connections.", 14.5, 500, MIC)
    d.close()

    cmd(238, "tail -1 voiceflow.log", "c2")
    d.open("o2")
    d.text(96, 268, "[VoiceFlow] 4.3s audio -> 1.3s, 54 characters", 15.5, 400, SOFT, font="M")
    d.text(96, 300, "That is the whole entry: timings and length. Never your words.", 14.5, 500, MIC)
    d.close()

    d.text(72, 336, "$", 15.5, 400, MIC, font="M")
    d.add(f'<rect class="blink" x="96" y="322" width="9" height="19" rx="1.5" fill="{INK}"/>')
    return d


# ==================================================================== handoff
def handoff():
    T = 9.0  # 0.8-3.2 speaking, 3.2-3.9 transcribing, 3.9 typed + copied, 4.6-6 travels, 6-7 paste menu, 7+ pasted
    css = " ".join([
        on("listen", 0.8, 3.2, T, 0.15), on("typed", 3.9, 8.6, T, 0.25), off("before", 3.9, 8.6, T, 0.15),
        on("trail", 4.4, 8.6, T, 0.3, rest=0.35), on("menu", 6.0, 6.9, T, 0.18), on("pasted", 7.0, 8.6, T, 0.25),
        "@keyframes fly { 0%, 50% { opacity: 0; transform: translate(0, 0); } 52% { opacity: 1; transform: translate(0, 0); } "
        "58% { transform: translate(52px, -42px); } 62% { transform: translate(100px, -56px); } 66% { transform: translate(148px, -42px); } "
        "69% { opacity: 1; transform: translate(200px, 0); } 71%, 100% { opacity: 0; transform: translate(200px, 0); } }",
        "@keyframes pop { 0%, 77% { transform: translateY(8px); } 81%, 100% { transform: translateY(0); } }",
        "@keyframes wave { from { transform: scaleY(0.2); } to { transform: scaleY(1); } }",
        "@keyframes blink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }",
        " ".join(f".{c} {{ animation: {c} {T}s infinite; }}" for c in ("listen", "typed", "before", "trail", "menu", "pasted")),
        f".fly {{ animation: fly {T}s ease-in-out infinite; }} .pop {{ animation: pop {T}s {EASE} infinite; }}",
        ".bar { animation: wave 0.6s ease-in-out infinite alternate; transform-box: fill-box; transform-origin: center; }",
        ".blink { animation: blink 1.1s infinite; }",
        reduced([".listen", ".before", ".fly", ".menu"], [".typed", ".trail", ".pasted"]),
    ])
    d = Doc(1000, 480, "Speak on your Mac, paste on your iPhone",
            "Speak on your Mac: the sentence is typed there and copied. Apple's Universal Clipboard carries it, encrypted, "
            "to your own iPhone, where you paste the same sentence into a message.", css)

    # Mac window
    d.add(f'<rect x="40" y="56" width="520" height="310" rx="18" fill="{PANEL}" stroke="{LINE}"/>')
    d.add(window_dots(68, 84))
    d.text(300, 89, "Notes", 13.5, 500, SOFT, anchor="middle")
    d.add(f'<line x1="40" y1="112" x2="560" y2="112" stroke="{LINE}"/>')
    d.text(72, 166, "Plans tonight", 24, 600)
    d.add(f'<g class="before"><rect class="blink" x="72" y="194" width="2.5" height="24" rx="1" fill="{MIC}"/></g>')
    d.open("typed")
    w = d.text(72, 213, "On my way, see you at 7.", 19, 400)
    d.add(f'<rect class="blink" x="{72 + w + 3:.0f}" y="194" width="2.5" height="24" rx="1" fill="{MIC}"/>')
    d.close()
    # status at the bottom of the window
    d.open("listen")
    d.add(f'<circle cx="78" cy="330" r="5" fill="{MIC}"/>')
    d.text(94, 335, "Holding right Option", 14, 500, MIC)
    d.open(None, f'fill="{MIC}"')
    for i, hgt in enumerate([8, 16, 24, 14, 28, 20, 30, 18, 26, 12, 20, 10, 14, 8]):
        d.add(f'<rect class="bar" x="{250 + i * 9}" y="{330 - hgt / 2:.0f}" width="4" height="{hgt}" rx="2" style="animation-delay:-{(i * 0.23) % 0.6:.2f}s"/>')
    d.close()
    d.close()
    d.open("typed")
    d.add(f'<path d="M73 330l4 4 8-9" fill="none" stroke="{INK}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>')
    d.text(94, 335, "Typed here, and copied to your clipboard", 14, 500, SOFT)
    d.close()

    # the handoff
    d.add(f'<path class="trail" d="M572 212C620 138 712 138 760 212" fill="none" stroke="{FAINT}" stroke-width="1.5" stroke-dasharray="3 7" stroke-linecap="round"/>')
    d.add(f'<g class="fly"><circle cx="566" cy="212" r="7" fill="{MIC}"/></g>')
    d.text(666, 112, "Universal Clipboard", 14, 600, anchor="middle")
    d.text(666, 132, "Apple-encrypted,", 13, 400, SOFT, anchor="middle")
    d.text(666, 150, "your devices only", 13, 400, SOFT, anchor="middle")

    # iPhone
    d.add(f'<rect x="772" y="40" width="188" height="368" rx="34" fill="{PANEL}" stroke="#3A3A3F" stroke-width="1.5"/>')
    d.add(f'<rect x="838" y="54" width="56" height="16" rx="8" fill="{BG}"/>')
    d.add(f'<circle cx="866" cy="104" r="15" fill="{RAISED}" stroke="{LINE}"/>')
    d.text(866, 109, "A", 13.5, 600, anchor="middle")
    d.text(866, 138, "Alex", 12, 500, SOFT, anchor="middle")
    d.add(f'<line x1="773" y1="152" x2="959" y2="152" stroke="{LINE}"/>')
    d.add(f'<rect x="786" y="168" width="118" height="32" rx="16" fill="{RAISED}"/>')
    d.text(800, 189, "Where are you?", 12.5, 400)
    # the pasted message
    d.open("pasted")
    d.open("pop")
    d.add(f'<rect x="792" y="214" width="156" height="32" rx="16" fill="{MIC}"/>')
    d.text(870, 235, "On my way, see you at 7.", 12, 500, MIC_INK, anchor="middle")
    d.text(948, 262, "Delivered", 10.5, 400, SOFT, anchor="end")
    d.close()
    d.close()
    # message field + Paste bubble
    d.add(f'<rect x="786" y="358" width="160" height="32" rx="16" fill="none" stroke="#3A3A3F"/>')
    d.text(802, 379, "iMessage", 12.5, 400, SOFT)
    d.open("menu")
    d.add(f'<rect x="800" y="316" width="64" height="30" rx="9" fill="{INK}"/>')
    d.add(f'<path d="M824 345l8 8 8-8z" fill="{INK}"/>')
    d.text(832, 336, "Paste", 13, 600, BG, anchor="middle")
    d.close()

    d.text(300, 432, "Speak on your Mac", 15, 600, anchor="middle")
    d.text(300, 454, "typed at your cursor, as always", 13.5, 400, SOFT, anchor="middle")
    d.text(866, 432, "Paste on your iPhone", 15, 600, anchor="middle")
    d.text(866, 454, "or iPad, a moment later", 13.5, 400, SOFT, anchor="middle")
    return d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", type=float, help="write still frames at this time (seconds)")
    ap.add_argument("--out", default=str(DOCS))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, scene in (("hero", hero), ("privacy", privacy), ("proof", proof), ("handoff", handoff)):
        svg = scene().render(args.freeze)
        suffix = f"_{args.freeze:g}" if args.freeze is not None else ""
        (out / f"{name}{suffix}.svg").write_text(svg)
        print(f"{name}{suffix}.svg  {len(svg) / 1024:.0f} KB")
