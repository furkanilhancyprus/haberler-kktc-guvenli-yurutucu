import html
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .news import CATEGORIES

# The Python build includes these existing public HTML files for server-side rendering.
BASE = Path(__file__).resolve().parents[1] / "public"
TEMPLATE = "haber-1558366206310607.html"


def template(path):
    return (BASE / path).read_text(encoding="utf-8")


def fields(row):
    href = f"/haber/{row['external_id']}"
    title = html.escape(row["title"])
    date = datetime.fromisoformat(row["at"]).astimezone(ZoneInfo("Europe/Bucharest"))
    iso = date.isoformat(timespec="seconds")
    time = f'<time datetime="{iso}">{date:%d.%m.%Y · %H:%M}</time>'
    return href, title, html.escape(row["media_url"]), CATEGORIES[row["category"]], time


def card(row):
    href, title, image, label, time = fields(row)
    return (f'<article class="story-card"><a href="{href}"><div class="card-photo">'
            f'<img src="{image}" alt="{title}" loading="lazy" decoding="async"></div>'
            f'<div class="card-body"><span class="kicker">{label}</span><h3>{title}</h3>{time}</div></a></article>')


def sidebar(row):
    href, title, image, label, time = fields(row)
    return (f'<a class="latest-item" href="{href}">{time}<span><small>{label}</small><strong>{title}</strong></span>'
            f'<img class="latest-photo" src="{image}" alt="" width="52" height="60" loading="lazy"></a>')


def replace(page, pattern, value):
    result, count = re.subn(pattern, lambda _: value, page, count=1, flags=re.S)
    if count != 1:
        raise ValueError("NEWS_TEMPLATE_MISMATCH")
    return result


def prepend(page, marker, markup):
    if not markup:
        return page
    if marker not in page:
        raise ValueError("NEWS_LIST_TEMPLATE_MISMATCH")
    return page.replace(marker, marker + markup, 1)


GRID = '<div class="card-grid">'


def listing(rows, category=None, home=False):
    if not home:
        file = f"kategori/{category}/index.html" if category else "son-haberler/index.html"
        return prepend(template(file), GRID, "".join(map(card, rows)))
    page = template("index.html")
    if not rows:
        return page
    marker = '<a class="latest-item"'
    if marker not in page:
        raise ValueError("NEWS_HOME_TEMPLATE_MISMATCH")
    page = page.replace(marker, "".join(map(sidebar, rows[:6])) + marker, 1)

    def desk(match):
        section = match[0]
        headline = re.search(r"<h2>(.*?)</h2>", section)
        selected = [row for row in rows if headline and CATEGORIES[row["category"]] == headline[1]][:4]
        marker = '<article class="story-card">'
        if selected and marker in section:
            return section.replace(marker, "".join(map(card, selected)) + marker, 1)
        return section

    return re.sub(r'<section class="desk">.*?</section>', desk, page, flags=re.S)


def article(row, origin, production):
    href, title, image, label, time = fields(row)
    category = row["category"]
    body = "".join("<p>" + html.escape(p).replace("\n", "<br>") + "</p>"
                   for p in re.split(r"\n\s*\n", row["content"]))
    source = f'<a href="{html.escape(row["source_url"])}" rel="noopener noreferrer">{html.escape(row["source_name"])}</a>'
    tags = html.escape(" · ".join(row["tags"]))
    content = (f'<main id="main" class="shell article-page facebook-edition">'
               f'<nav class="breadcrumbs" aria-label="Sayfa yolu"><a href="/">Ana sayfa</a> / '
               f'<a href="/kategori/{category}">{label}</a></nav>'
               f'<article><header class="article-header"><span class="kicker">{label}</span><h1>{title}</h1>'
               f'<div class="article-meta"><span>Haberler KKTC</span>{time}</div></header>'
               f'<figure class="article-photo"><img src="{image}" alt="{title}" fetchpriority="high"></figure>'
               f'<div class="article-columns"><div class="article-copy"><div class="article-text">{body}</div>'
               f'<p class="source">Kaynak: {source}</p><p>{tags}</p></div></div></article></main>')
    page = replace(template(TEMPLATE), r"<main\b[^>]*>.*?</main>", content)
    page = replace(page, r"<title>.*?</title>", f"<title>{title} | Haberler KKTC</title>")
    page = re.sub(r'<(?:link|meta)\b[^>]*(?:rel="canonical"|name="description"|property="og:[^"]+")[^>]*>', "", page)
    if production:
        page = re.sub(r'<meta\b[^>]*name="robots"[^>]*>', "", page)
    description = html.escape(row["summary"])
    canonical = html.escape(origin + href)
    head = (f'<meta name="description" content="{description}"><link rel="canonical" href="{canonical}">'
            f'<meta property="og:title" content="{title}"><meta property="og:description" content="{description}">'
            f'<meta property="og:image" content="{image}"><meta property="og:url" content="{canonical}">')
    return page.replace("</head>", head + "</head>", 1)
