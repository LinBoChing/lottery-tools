#!/usr/bin/env python3
import json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

OUT = Path("latest-draws.json")
HIST = {
    "539": Path("history-539.json"),
    "dayday": Path("history-dayday.json")
}

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 Chrome/131 Safari/537.36"
)


def fetch(url):
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json,*/*",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })

    with urlopen(req, timeout=40) as r:
        raw = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
        return raw.decode(enc, errors="ignore")


def valid(nums):
    return (
        isinstance(nums, list)
        and len(nums) == 5
        and len(set(nums)) == 5
        and all(
            isinstance(n, int)
            and 1 <= n <= 39
            for n in nums
        )
    )


def norm_date(s):
    s = re.sub(r"\s+", " ", str(s)).strip()

    for f in (
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ):
        try:
            return datetime.strptime(
                s, f
            ).strftime("%Y/%m/%d")
        except ValueError:
            pass

    m = re.search(
        r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})",
        s
    )

    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}/{mo:02d}/{d:02d}"

    m = re.search(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})",
        s
    )

    if m:
        mon, d, y = m.groups()

        for f in (
            "%B %d %Y",
            "%b %d %Y"
        ):
            try:
                return datetime.strptime(
                    f"{mon} {d} {y}", f
                ).strftime("%Y/%m/%d")
            except ValueError:
                pass

    raise RuntimeError(
        f"無法辨識日期：{s}"
    )


def five_comma(text):
    m = re.search(
        r"(?<!\d)(0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])(?!\d)",
        text
    )

    nums = (
        [int(x) for x in m.groups()]
        if m else []
    )

    return nums if valid(nums) else []


# =========================================================
# 539
# =========================================================

def pilio_date(text):
    m = re.search(
        r"(?<!\d)(\d{1,2})/(\d{1,2})\s+"
        r"(\d{2})(?:\([^)]*\))?",
        text
    )

    if m:
        mo, d, yy = map(int, m.groups())

        return (
            f"{2000 + yy:04d}/"
            f"{mo:02d}/{d:02d}"
        )

    m = re.search(
        r"(20\d{2})[/-]"
        r"(\d{1,2})[/-](\d{1,2})",
        text
    )

    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}/{mo:02d}/{d:02d}"

    m = re.search(
        r"(?<!\d)(1\d{2})[/-]"
        r"(\d{1,2})[/-](\d{1,2})(?!\d)",
        text
    )

    if m:
        y, mo, d = map(int, m.groups())

        return (
            f"{1911 + y:04d}/"
            f"{mo:02d}/{d:02d}"
        )

    raise RuntimeError(
        "Pilio 找不到日期"
    )


def parse_pilio(url):
    soup = BeautifulSoup(
        fetch(url), "lxml"
    )

    rows = []

    for tr in soup.find_all("tr"):

        text = " | ".join(
            re.sub(
                r"\s+",
                " ",
                c.get_text(" ", strip=True)
            )
            for c in tr.find_all(
                ["td", "th"]
            )
        )

        nums = five_comma(text)

        if not valid(nums):
            continue

        try:
            date = pilio_date(text)
        except Exception:
            continue

        rows.append({
            "date": date,
            "issue": "",
            "nums": sorted(nums),
            "source": url,
        })

    if not rows:
        raise RuntimeError(
            "找不到539開獎列"
        )

    rows.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    return rows[0]


def fetch_539():
    urls = [
        "https://www.pilio.idv.tw/lto539/list.asp",
        "https://www.pilio.idv.tw/lto539/drawlist/drawlist.asp?orderby=new",
    ]

    good = []
    errors = []

    for url in urls:
        try:
            r = parse_pilio(url)

            good.append(r)

            print(
                "539來源成功:",
                r["date"],
                r["nums"],
                url
            )

        except Exception as e:
            errors.append(
                f"{url}: {e}"
            )

            print(
                "539來源失敗:",
                url,
                e
            )

    if not good:
        raise RuntimeError(
            "539全部來源失敗；"
            + " | ".join(errors)
        )

    good.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    return good[0]


# =========================================================
# 天天樂 Fantasy 5
# =========================================================

def balls(node):
    vals = []

    selectors = (
        ".ball",
        "[class*='ball']",
        "[class*='winning-number']",
        "[class*='draw-number']",
        "[data-testid*='ball']",
        "[aria-label*='ball']",
    )

    for sel in selectors:
        for x in node.select(sel):

            t = x.get_text(
                " ",
                strip=True
            )

            if re.fullmatch(
                r"0?[1-9]|[12]\d|3[0-9]",
                t
            ):
                n = int(t)

                if n not in vals:
                    vals.append(n)

    return vals


def parse_calottery():
    url = (
        "https://www.calottery.com/"
        "en/draw-games/fantasy-5"
    )

    soup = BeautifulSoup(
        fetch(url),
        "lxml"
    )

    labels = soup.find_all(
        string=lambda x: (
            isinstance(x, str)
            and "winning numbers"
            in x.lower()
        )
    )

    box = None

    for label in labels:

        node = label.parent

        for _ in range(8):

            if node is None:
                break

            text = re.sub(
                r"\s+",
                " ",
                node.get_text(
                    " ",
                    strip=True
                )
            )

            has_issue = re.search(
                r"Draw\s*#\s*\d+",
                text,
                re.I
            )

            has_date = re.search(
                r"(?:MON|TUE|WED|THU|FRI|SAT|SUN)"
                r"/[A-Z]{3}\s+\d{1,2},\s+20\d{2}",
                text,
                re.I
            )

            if has_issue and has_date:
                box = node
                break

            node = node.parent

        if box is not None:
            break

    if box is None:
        raise RuntimeError(
            "官方頁找不到 Winning Numbers"
        )

    text = re.sub(
        r"\s+",
        " ",
        box.get_text(
            " ",
            strip=True
        )
    )

    dm = re.search(
        r"(?:MON|TUE|WED|THU|FRI|SAT|SUN)"
        r"/([A-Z]{3})\s+"
        r"(\d{1,2}),\s+(20\d{2})",
        text,
        re.I
    )

    im = re.search(
        r"Draw\s*#\s*(\d+)",
        text,
        re.I
    )

    if not dm or not im:
        raise RuntimeError(
            "官方頁找不到日期或期號"
        )

    mon, d, y = dm.groups()

    ca = datetime.strptime(
        f"{mon.title()} {d} {y}",
        "%b %d %Y"
    )

    date = (
        ca + timedelta(days=1)
    ).strftime("%Y/%m/%d")

    vals = balls(box)

    nums = []

    for i in range(
        max(0, len(vals) - 4)
    ):
        c = vals[i:i + 5]

        if valid(c):
            nums = c
            break

    if not valid(nums):

        after = text[im.end():]

        vals = []

        for v in re.findall(
            r"(?<!\d)"
            r"(0?[1-9]|[12]\d|3[0-9])"
            r"(?!\d)",
            after
        ):
            n = int(v)

            if n not in vals:
                vals.append(n)

        for i in range(
            len(vals) - 5,
            -1,
            -1
        ):
            c = vals[i:i + 5]

            if valid(c):
                nums = c
                break

    if not valid(nums):
        raise RuntimeError(
            "官方頁球號解析失敗"
        )

    return {
        "date": date,
        "issue": im.group(1),
        "nums": sorted(nums),
        "source": url,
    }


def parse_lotteryusa():
    url = (
        "https://www.lotteryusa.com/"
        "california/fantasy-5/year"
    )

    soup = BeautifulSoup(
        fetch(url),
        "lxml"
    )

    found = []

    for node in soup.find_all(
        [
            "tr",
            "article",
            "li",
            "section",
            "div",
        ]
    ):

        text = re.sub(
            r"\s+",
            " ",
            node.get_text(
                " ",
                strip=True
            )
        )

        dm = re.search(
            r"(Monday|Tuesday|Wednesday|"
            r"Thursday|Friday|Saturday|Sunday)"
            r",?\s+"
            r"([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
            text,
            re.I
        )

        if not dm:
            continue

        vals = balls(node)

        for i in range(
            max(0, len(vals) - 4)
        ):

            c = vals[i:i + 5]

            if valid(c):

                ca = datetime.strptime(
                    norm_date(
                        dm.group(2)
                    ),
                    "%Y/%m/%d"
                )

                date = (
                    ca + timedelta(days=1)
                ).strftime(
                    "%Y/%m/%d"
                )

                found.append({
                    "date": date,
                    "issue": "",
                    "nums": sorted(c),
                    "source": url,
                })

                break

    if not found:
        raise RuntimeError(
            "LotteryUSA 找不到資料"
        )

    found.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    return found[0]


def fetch_dayday():
    good = []
    errors = []

    for fn in (
        parse_calottery,
        parse_lotteryusa
    ):

        try:
            r = fn()

            if not valid(r["nums"]):
                raise RuntimeError(
                    "球號驗證失敗"
                )

            good.append(r)

            print(
                "天天樂來源成功:",
                r["date"],
                r["nums"],
                r["source"]
            )

        except Exception as e:

            errors.append(
                f"{fn.__name__}: {e}"
            )

            print(
                "天天樂來源失敗:",
                fn.__name__,
                e
            )

    if not good:
        raise RuntimeError(
            "天天樂全部來源失敗；"
            + " | ".join(errors)
        )

    good.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    return good[0]


# =========================================================
# JSON / 歷史資料
# =========================================================

def load_json(path, default):
    try:
        if not path.exists():
            return default

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        return default


def game_ok(g):
    return (
        isinstance(g, dict)
        and bool(g.get("date"))
        and valid(g.get("nums"))
    )


def newer(new, old):
    if not game_ok(old):
        return new

    if new["date"] >= old["date"]:
        return new

    return old


def identity(key, d):
    issue = str(
        d.get("issue", "")
    ).strip()

    if key == "dayday" and issue:
        return (
            "issue",
            issue
        )

    return (
        "date_nums",
        d.get("date", ""),
        tuple(
            d.get("nums", [])
        )
    )


def update_history(
    key,
    latest,
    updated_at
):
    data = load_json(
        HIST[key],
        {"draws": []}
    )

    if isinstance(data, list):
        draws = data
    else:
        draws = data.get(
            "draws",
            []
        )

    merged = [latest]
    seen = {
        identity(
            key,
            latest
        )
    }

    for d in draws:

        if not game_ok(d):
            continue

        ident = identity(
            key,
            d
        )

        if ident not in seen:

            seen.add(ident)
            merged.append(d)

    def sorter(d):

        issue = str(
            d.get(
                "issue",
                ""
            )
        )

        issue_num = (
            int(issue)
            if issue.isdigit()
            else 0
        )

        return (
            d.get(
                "date",
                ""
            ),
            issue_num
        )

    merged.sort(
        key=sorter,
        reverse=True
    )

    merged = merged[:500]

    result = {
        "game": key,
        "updated_at": updated_at,
        "count": len(merged),
        "draws": merged,
    }

    HIST[key].write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )


# =========================================================
# 主程式
# =========================================================

def main():

    old = load_json(
        OUT,
        {}
    )

    old_games = (
        old.get(
            "games",
            {}
        )
        if isinstance(old, dict)
        else {}
    )

    games = {}
    warnings = []

    for key, getter in (
        ("539", fetch_539),
        ("dayday", fetch_dayday),
    ):

        try:
            fetched = getter()

            games[key] = newer(
                fetched,
                old_games.get(key)
            )

        except Exception as e:

            warnings.append(
                f"{key}: {e}"
            )

            if game_ok(
                old_games.get(key)
            ):

                games[key] = (
                    old_games[key]
                )

                print(
                    key,
                    "抓取失敗，保留舊資料"
                )

            else:
                raise

    updated_at = datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )

    output = {
        "updated_at": updated_at,
        "games": games,
        "warnings": warnings,
    }

    OUT.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )

    for key, g in games.items():

        update_history(
            key,
            g,
            updated_at
        )

    print(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        )
    )


if __name__ == "__main__":
    main()
