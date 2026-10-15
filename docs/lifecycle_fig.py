"""Draws docs/lifecycle.svg (Figure 1 of the submission draft: the dispute lifecycle).

Run: python docs/lifecycle_fig.py, then render to PNG with headless Chrome (see the bottom of this file).
"""
from pathlib import Path

W = 760
CX = 230            # centre of the main column
BW, BH = 340, 60    # step box size
DW, DH = 300, 92    # gate diamond size
GAP = 26            # vertical gap between shapes
BUS_X = 640         # vertical line that carries every "to a person" exit
HUMAN = (520, 240)  # human box width, height

STEPS = [
    ("box", "Dispute filed", "by the rider or the driver, in the app"),
    ("box", "Collect evidence", "trip, GPS, chat, app events, photos; checked in code"),
    ("box", "Classify and triage", "dispute type, urgency P0 to P3"),
    ("gate", "Safety or legal (P0)?", "", "yes"),
    ("box", "Case brief and risk check", "v2.1 sections for this dispute; fraud report to Judge only"),
    ("box", "Advocates argue both sides", "rider vs driver, each from the records and the policy"),
    ("box", "Judge rules", "verdict, amount, confidence, cited v2.1 sections"),
    ("gate", "Code Judge: facts on the", "records, amount adds up?", "no (after one redraft)"),
    ("gate", "Policy v2.1 gate:", "may an AI decide this?", "no"),
    ("box", "Fairness audit", "both sides heard? citations real? consistent?"),
    ("gate", "Fairness clears it?", "", "no"),
    ("end", "Resolved automatically", "refund or fee applied, both parties notified"),
]

out = []
add = out.append
y = 90
exits = []
prev_bottom = None
for s in STEPS:
    kind = s[0]
    h = DH if kind == "gate" else BH
    if prev_bottom is not None:
        add(f'<line x1="{CX}" y1="{prev_bottom}" x2="{CX}" y2="{y - 2}" class="ln" marker-end="url(#a)"/>')
    if kind == "gate":
        top, mid, bot = y, y + h / 2, y + h
        add(f'<polygon points="{CX},{top} {CX + DW / 2},{mid} {CX},{bot} {CX - DW / 2},{mid}" class="gate"/>')
        if s[2]:
            add(f'<text x="{CX}" y="{mid - 5}" class="g">{s[1]}</text>')
            add(f'<text x="{CX}" y="{mid + 15}" class="g">{s[2]}</text>')
        else:
            add(f'<text x="{CX}" y="{mid + 5}" class="g">{s[1]}</text>')
        exits.append((mid, s[3]))
        add(f'<text x="{CX + 14}" y="{bot + 18}" class="lbl" text-anchor="start">{"no" if s[3] == "yes" else "yes"}</text>')
    else:
        cls = "end" if kind == "end" else "box"
        add(f'<rect x="{CX - BW / 2}" y="{y}" width="{BW}" height="{h}" rx="9" class="{cls}"/>')
        add(f'<text x="{CX}" y="{y + 25}" class="t">{s[1]}</text>')
        add(f'<text x="{CX}" y="{y + 45}" class="s">{s[2]}</text>')
    prev_bottom = y + h
    y += h + GAP

# Human review box: bottom right, level with the end box.
end_top = prev_bottom - BH
hw, hh = HUMAN
hx = BUS_X - 110
hy = exits[-1][0] + 40
add(f'<rect x="{hx}" y="{hy}" width="220" height="130" rx="9" class="box"/>')
add(f'<text x="{hx + 110}" y="{hy + 28}" class="t">A person decides</text>')
for i, line in enumerate(["review desk: evidence, both", "arguments, the draft ruling", "and why it was stopped;", "Tencent ADP answers policy Qs"]):
    add(f'<text x="{hx + 110}" y="{hy + 54 + i * 20}" class="s">{line}</text>')

# Exits run right to the bus, the bus runs down into the human box.
first = exits[0][0]
for mid, label in exits:
    add(f'<line x1="{CX + DW / 2}" y1="{mid}" x2="{BUS_X}" y2="{mid}" class="ln"/>')
    add(f'<text x="{CX + DW / 2 + 10}" y="{mid - 7}" class="lbl" text-anchor="start">{label}</text>')
add(f'<line x1="{BUS_X}" y1="{first}" x2="{BUS_X}" y2="{hy - 2}" class="ln" marker-end="url(#a)"/>')

H = max(prev_bottom, hy + 130) + 30
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Segoe UI, Helvetica, Arial, sans-serif">
  <defs>
    <marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#9ca3af"/>
    </marker>
    <style>
      .box {{ fill: #fff; stroke: #b8b8b0; stroke-width: 1.3; }}
      .end {{ fill: #e6edf9; stroke: #2f6fd6; stroke-width: 2.2; }}
      .gate {{ fill: #fff; stroke: #b8b8b0; stroke-width: 1.3; }}
      .ln {{ stroke: #b0b0a8; stroke-width: 1.3; fill: none; }}
      .t {{ font-size: 15px; font-weight: 600; fill: #1f2328; text-anchor: middle; }}
      .s {{ font-size: 12px; fill: #5b6068; text-anchor: middle; }}
      .g {{ font-size: 13.5px; fill: #1f2328; text-anchor: middle; }}
      .lbl {{ font-size: 12.5px; fill: #5b6068; }}
      .h {{ font-size: 16px; font-weight: 600; fill: #1f2328; }}
    </style>
  </defs>
  <rect width="{W}" height="{H}" fill="#fff"/>
  <text x="24" y="40" class="h">Money moves only when the Judge, code checks, the policy gate and fairness all agree</text>
  {chr(10).join("  " + l for l in out)}
</svg>
'''
Path(__file__).with_name("lifecycle.svg").write_text(svg, encoding="utf-8")
print("wrote docs/lifecycle.svg", W, H)

# Render: chrome --headless --screenshot=docs/lifecycle.png --window-size=760,<H>
#         --force-device-scale-factor=2 --hide-scrollbars file:///.../docs/lifecycle.svg
