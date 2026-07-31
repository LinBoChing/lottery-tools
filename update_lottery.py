#!/usr/bin/env python3
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

OUTPUT_FILE = Path("latest-draws.json")
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def fetch(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(req, timeout=35) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise RuntimeError(f"HTTP {status}: {url}")
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            return raw.decode(charset, errors="ignore")
        except LookupError:
            return raw.decode("utf-8", errors="ignore")


def valid_nums(nums) -> bool:
    return (
        isinstance(nums, list)
        and len(nums) == 5
        and len(set(nums)) == 5
        and all(isinstance(n, int) and 1 <= n <= 39 for n in nums)
    )


def normalize_date(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value)).strip()
    value = re.sub(
        r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)(day)?,?\s+",
        "",
        value,
        flags=re.I,
    )

    for fmt in (
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ):
        try:
            return datetime.strptime(value, fmt).strftime("%Y/%m/%d")
        except ValueError:
            pass

    match = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", value)
    if match:
        y, m, d = map(int, match.groups())
        return f"{y:04d}/{m:02d}/{d:02d}"

    match = re.search(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})",
        value,
    )
    if match:
        month, day, year = match.groups()
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                return datetime.strptime(
                    f"{month} {day} {year}", fmt
                ).strftime("%Y/%m/%d")
            except ValueError:
                pass

    raise RuntimeError(f"日期無法辨識：{value!r}")


def row_numbers(text: str) -> list[int]:
    # 先移除完整日期，避免月份、日期被誤當球號。
    cleaned = re.sub(
        r"20\d{2}[/-]\d{1,2}[/-]\d{1,2}",
        " ",
        text,
    )
    cleaned = re.sub(
        r"\d{1,2}[/-]\d{1,2}[/-]20\d{2}",
        " ",
        cleaned,
    )

    # 優先讀取逗號分隔的五碼。
    groups = re.findall(
        r"(?<!\d)(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])(?!\d)",
        cleaned,
    )
    for group in groups:
        nums = [int(x) for x in group]
        if valid_nums(nums):
            return nums

    return []


def fetch_539() -> dict:
    urls = [
        "https://www.pilio.idv.tw/lto539/list.asp",
        "https://www.pilio.idv.tw/lto539/drawlist/drawlist.asp",
    ]
    errors = []

    for url in urls:
        try:
            html = fetch(url)
            soup = BeautifulSoup(html, "lxml")

            # 僅逐列解析，不再從整頁連續抽取任意五個數字。
            for tr in soup.find_all("tr"):
                cells = [
                    re.sub(r"\s+", " ", cell.get_text(" ", strip=True))
                    for cell in tr.find_all(["td", "th"])
                ]
                if not cells:
                    continue

                line = " | ".join(cells)
                nums = row_numbers(line)
                if not valid_nums(nums):
                    continue

                # Pilio 常見日期格式：07/30 26(四)
                # 其中 26 是民國年尾碼，不可當成球號。
                date_match = re.search(
                    r"(?<!\d)(\d{1,2})/(\d{1,2})\s+(\d{2,3})(?:\([^)]*\))?",
                    line,
                )
                if date_match:
                    month, day, roc_year = map(int, date_match.groups())
                    year = 1911 + roc_year
                    date = f"{year:04d}/{month:02d}/{day:02d}"
                else:
                    full_date = re.search(
                        r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})",
                        line,
                    )
                    if not full_date:
                        continue
                    year, month, day = map(int, full_date.groups())
                    date = f"{year:04d}/{month:02d}/{day:02d}"

                return {
                    "date": date,
                    "issue": "",
                    "nums": sorted(nums),
                    "source": url,
                }

            errors.append(f"{url}: 找不到含日期及5碼的資料列")

        except Exception as exc:
            errors.append(f"{url}: {exc}")

    raise RuntimeError("539抓取失敗；" + " | ".join(errors))


def parse_calottery_official_page() -> dict:
    url = "https://www.calottery.com/en/draw-games/fantasy-5"
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    # 官方頁目前會呈現：
    # Winning Numbers: WED/JUL 29, 2026 Draw #11953 12 19 26 29 39
    match = re.search(
        r"Winning Numbers:\s*"
        r"(?:MON|TUE|WED|THU|FRI|SAT|SUN)"
        r"/([A-Z]{3})\s+(\d{1,2}),\s+(20\d{2})"
        r"\s+Draw\s*#\s*(\d+)"
        r"\s+((?:(?:0?[1-9]|[12]\d|3[0-9])\s+){4}"
        r"(?:0?[1-9]|[12]\d|3[0-9]))",
        text,
        flags=re.I,
    )
    if not match:
        raise RuntimeError("官方Fantasy 5頁面找不到Winning Numbers資料")

    month_name, day, year, issue, nums_text = match.groups()
    date = datetime.strptime(
        f"{month_name.title()} {day} {year}",
        "%b %d %Y",
    ).strftime("%Y/%m/%d")

    nums = [int(x) for x in re.findall(r"\d{1,2}", nums_text)]
    if not valid_nums(nums):
        raise RuntimeError(f"官方Fantasy 5號碼驗證失敗：{nums}")

    return {
        "date": date,
        "issue": issue,
        "nums": sorted(nums),
        "source": url,
    }


def parse_lotteryusa_fallback() -> dict:
    url = "https://www.lotteryusa.com/california/fantasy-5/year"
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")

    # 逐個結構區塊尋找「日期 + 同區塊內5個球號」。
    for node in soup.find_all(["tr", "article", "li", "section", "div"]):
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        date_match = re.search(
            r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
            r"([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
            text,
            flags=re.I,
        )
        if not date_match:
            continue

        # 只讀取該DOM區塊中具球號語意的元素。
        values = []
        for ball in node.select(
            ".ball, [class*='ball'], [class*='number'], "
            "[data-testid*='ball'], [aria-label*='number']"
        ):
            ball_text = ball.get_text(" ", strip=True)
            if re.fullmatch(r"0?[1-9]|[12]\d|3[0-9]", ball_text):
                values.append(int(ball_text))

        # 去重但保留順序。
        nums = []
        for value in values:
            if value not in nums:
                nums.append(value)

        if valid_nums(nums[:5]):
            return {
                "date": normalize_date(date_match.group(0)),
                "issue": "",
                "nums": sorted(nums[:5]),
                "source": url,
            }

    raise RuntimeError("LotteryUSA找不到日期與同區塊5個球號")


def fetch_fantasy5() -> dict:
    errors = []
    for parser in (
        parse_calottery_official_page,
        parse_lotteryusa_fallback,
    ):
        try:
            result = parser()
            if not result.get("date"):
                raise RuntimeError("日期空白")
            if not valid_nums(result.get("nums")):
                raise RuntimeError("號碼格式不正確")
            return result
        except Exception as exc:
            errors.append(f"{parser.__name__}: {exc}")

    raise RuntimeError("Fantasy 5抓取失敗；" + " | ".join(errors))


def load_old() -> dict:
    if not OUTPUT_FILE.exists():
        return {}
    try:
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def valid_game(game) -> bool:
    return (
        isinstance(game, dict)
        and bool(str(game.get("date", "")).strip())
        and valid_nums(game.get("nums"))
    )


def main() -> None:
    old = load_old()
    old_games = old.get("games", {})
    games = {}
    warnings = []

    for key, getter in (
        ("539", fetch_539),
        ("dayday", fetch_fantasy5),
    ):
        try:
            result = getter()
            if not valid_game(result):
                raise RuntimeError("最終驗證失敗")
            games[key] = result
            print(
                f"{key}：{result['date']}｜"
                + " ".join(f"{n:02d}" for n in result["nums"])
            )
        except Exception as exc:
            warning = f"{key}: {exc}"
            warnings.append(warning)
            print("WARNING:", warning)

            old_game = old_games.get(key)
            if valid_game(old_game):
                games[key] = old_game
                print(f"{key}保留舊資料")
            else:
                raise SystemExit(
                    f"{key}抓取失敗且沒有可保留的舊資料"
                )

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "games": games,
        "warnings": warnings,
    }
    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
