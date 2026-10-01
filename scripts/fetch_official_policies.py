"""
Fetch Ryde's official policy text, word for word, into data/policies/official/.

Two public sources:
  - the Ryde Help Centre (Zendesk). Its public Help Center API returns every article
    with its official last-updated time. Only dispute-related articles are kept.
  - rydesharing.com pages: Terms of Use, Code of Conduct, Privacy Policy and the two
    driver safety guides.

Each output file groups one Help Centre section; every article is one "## " section,
so the indexer's markdown chunking keeps one article per chunk. The body text is the
official wording with the HTML removed. Nothing is paraphrased.

Usage:
    python scripts/fetch_official_policies.py            # writes data/policies/official/
    python scripts/fetch_official_policies.py --out DIR
"""
import argparse
import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELP_API = "https://help.rydesharing.com/api/v2/help_center/en-us"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"}

# Article titles that matter for ride disputes (fees, fares, routes, mess, ratings,
# safety, accidents, conduct, account actions, RydeSEND claims)
DISPUTE_TITLE = re.compile(
    r"cancel|wait|waiver|appeal|dispute|refund|mess|clean|fare|surge|route|detour|erp|toll|"
    r"overcharg|rating|review|safety|harass|accident|lost|complain|no.?show|late|conduct|"
    r"suspend|disabled|evasion|damage|report|insurance|feedback|violate",
    re.I,
)
# Matches the title filter but is about earnings or payouts, not disputes
NOT_DISPUTE = re.compile(r"CPF|income loss|cashout|Carpool Driver|operating hours|Base Fare Support", re.I)

# The Terms of Use and Privacy Policy mark their clause titles as list items, not
# headings. These exact official titles become "## " sections so each clause is
# retrieved and cited on its own.
CLAUSE_TITLES = {
    "terms_of_use": [
        "Section A – General Terms", "Introduction", "Definitions", "Compatibility",
        "License Grant and Restrictions", "Payment Terms for Partners", "Cancellation Terms for Partners",
        "Cancellation Terms for Users", "Ryde Rewards and Promotions for Users", "Ratings", "Complaints",
        "Repair and Cleaning Fees for Users", "Intellectual Property Ownership", "Taxes", "Confidentiality",
        "Data Privacy and Personal Data Protection Policy", "Third Party Interactions", "Indemnification",
        "Disclaimer of Warranties", "Internet Delays", "Limitation of Liability", "Notice", "Assignment",
        "Dispute Resolution", "Relationship", "Severability", "No Waiver", "Entire Agreement",
        "No Third Party Rights", "Section B – Additional Terms", "For RydePOOL Partners", "RydeCoins – Singapore Only",
    ],
    "privacy_policy": [
        "COLLECTION OF PERSONAL DATA", "USE OF PERSONAL DATA", "DISCLOSURE OF PERSONAL DATA",
        "RETENTION OF PERSONAL DATA", "COOKIES AND ADVERTISING ON THIRD PARTY PLATFORMS",
        "PROTECTION OF PERSONAL DATA", "AMENDMENTS AND UPDATES", "CONTACT US", "INTERPRETATION",
        "How Ryde for Business Works",
    ],
}


def promote_clause_titles(text: str, titles: list[str]) -> str:
    """Turn the first line that is exactly one of `titles` (bullet or not) into a "## " heading."""
    wanted = {t.lower(): t for t in titles}
    out = []
    for line in text.splitlines():
        bare = line.removeprefix("- ").strip().strip("*").strip()
        if bare.lower() in wanted:
            out += ["", f"## {wanted.pop(bare.lower())}", ""]
        else:
            out.append(line)
    return "\n".join(out)


SITE_PAGES = {
    "terms_of_use": "https://rydesharing.com/terms-of-use/",
    "code_of_conduct": "https://rydesharing.com/code-of-conduct/",
    "privacy_policy": "https://rydesharing.com/privacy-policy/",
    "safe_driving_tips": "https://rydesharing.com/4-safe-driving-tips-for-ryde-driver-partners/",
    "platform_work_safe_and_fair": "https://rydesharing.com/keeping-platform-work-safe-and-fair-a-guide-for-drivers/",
}


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()


def fetch_all(url: str) -> list[dict]:
    """Follow Zendesk pagination and return the listed records."""
    items = []
    while url:
        page = json.loads(fetch(url))
        key = next(k for k, v in page.items() if isinstance(v, list))
        items += page[key]
        url = page.get("next_page")
    return items


HEADING = "\x00H\x00"  # marks an official heading until the text is cleaned


def html_to_markdown(markup: str, section_headings: bool = False) -> str:
    """Official HTML to plain markdown-ish text: keep list bullets and line breaks, drop tags.

    section_headings=True turns the page's own headings into "## " sections, so a long
    page (the Terms of Use) is indexed as one chunk per heading instead of one huge chunk.
    """
    markup = re.sub(r"(?is)<(script|style|noscript|svg|form)[^>]*>.*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<h[1-6][^>]*>", f"\n{HEADING}" if section_headings else "\n**", markup)
    markup = re.sub(r"(?i)</h[1-6]>", "\n" if section_headings else "**\n", markup)
    markup = re.sub(r"(?i)<li[^>]*>", "\n- ", markup)
    markup = re.sub(r"(?i)<(br|/p|/li|/div|/tr|/table|/ul|/ol)[^>]*>", "\n", markup)
    markup = re.sub(r"(?i)</t[dh]>", " | ", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    # "## " would start a new chunk inside an article; official text never needs it
    lines = [re.sub(r"^#+\s*", "", line) for line in lines]
    lines = [f"\n## {line[len(HEADING):].strip()}\n" if line.startswith(HEADING) else line for line in lines]
    lines = [line for line in lines if line and line not in ("**", "** **", "\n## \n")]
    text = "\n".join(lines)
    return re.sub(r"\*\*\s*\*\*", "", text).strip()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")



def build_help_centre(out: Path, fetched: str) -> list[str]:
    sections = {s["id"]: s for s in fetch_all(f"{HELP_API}/sections.json?per_page=100")}
    categories = {c["id"]: c["name"] for c in fetch_all(f"{HELP_API}/categories.json?per_page=100")}
    articles = fetch_all(f"{HELP_API}/articles.json?per_page=100")

    groups: dict[tuple[str, str], list[dict]] = {}
    seen_bodies = set()
    for a in sorted(articles, key=lambda a: a["updated_at"], reverse=True):
        if a.get("draft") or not DISPUTE_TITLE.search(a["title"]) or NOT_DISPUTE.search(a["title"]):
            continue
        body = html_to_markdown(a["body"])
        # The Help Centre repeats some articles in two sections: keep the newest copy
        fingerprint = (a["title"].strip().lower(), re.sub(r"\W+", "", body.lower()))
        if fingerprint in seen_bodies:
            continue
        seen_bodies.add(fingerprint)
        section = sections.get(a["section_id"], {})
        key = (categories.get(section.get("category_id"), "General"), section.get("name", "General"))
        groups.setdefault(key, []).append({**a, "text": body})

    written = []
    for (category, section), items in sorted(groups.items()):
        name = f"ryde_help_{slug(category)}_{slug(section)}.md"
        parts = [
            f"# Ryde Help Centre: {category} / {section}",
            "",
            f"Official text from help.rydesharing.com, copied word for word (HTML removed). Fetched {fetched}.",
            "",
        ]
        for a in sorted(items, key=lambda a: a["title"].lower()):
            parts += [
                f"## {a['title'].strip()}",
                "",
                f"Source: {a['html_url']} (last updated {a['updated_at'][:10]})",
                "",
                a["text"],
                "",
            ]
        (out / name).write_text("\n".join(parts), encoding="utf-8")
        written.append(f"{name}  ({len(items)} articles)")
    return written


def main_content(page: str) -> str:
    """The page's main text block: WordPress/Elementor content, or <main>, or <body>."""
    for pattern in (r"(?is)<main[^>]*>(.*)</main>", r"(?is)<article[^>]*>(.*)</article>", r"(?is)<body[^>]*>(.*)</body>"):
        m = re.search(pattern, page)
        if m:
            page = m.group(1)
            break
    page = re.sub(r"(?is)<(header|footer|nav)[^>]*>.*?</\1>", " ", page)
    return page


def build_site_pages(out: Path, fetched: str) -> list[str]:
    written = []
    for name, url in SITE_PAGES.items():
        page = fetch(url).decode("utf-8", "replace")
        text = html_to_markdown(main_content(page), section_headings=True)
        text = text.split("©")[0].rstrip()  # site footer links follow the copyright line
        if name in CLAUSE_TITLES:
            text = promote_clause_titles(text, CLAUSE_TITLES[name])
        title = re.search(r"(?is)<title>(.*?)</title>", page)
        title = html.unescape(title.group(1)).split("–")[0].strip() if title else name
        body = [
            f"# Ryde website: {title}",
            "",
            f"Source: {url}. Official text copied word for word (HTML removed). Fetched {fetched}.",
            "",
            text if text.startswith("## ") else f"## {title}\n\n{text}",
            "",
        ]
        (out / f"ryde_site_{name}.md").write_text("\n".join(body), encoding="utf-8")
        written.append(f"ryde_site_{name}.md  ({len(text)} chars)")
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default=str(ROOT / "data" / "policies" / "official"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for line in build_help_centre(out, fetched) + build_site_pages(out, fetched):
        print(line)


if __name__ == "__main__":
    main()
