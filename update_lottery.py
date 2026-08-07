#!/usr/bin/env python3

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


# ============================================================
# 基本設定
# ============================================================

OUTPUT_FILE = Path("latest-draws.json")

HISTORY_FILES = {
    "539": Path("history-539.json"),
    "dayday": Path("history-dayday.json"),
}

MAX_HISTORY_DRAWS = 500

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)


# ============================================================
# 網頁下載
# ============================================================

def fetch(url: str, retries: int = 3) -> str:
    last_error = None

    for attempt in range(1, retries + 1):

        try:
            req = Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": (
                        "text/html,application/xhtml+xml,"
                        "application/json,text/plain,*/*"
                    ),
                    "Accept-Language": (
                        "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
                    ),
                    "Cache-Control": "no-cache, no-store, max-age=0",
                    "Pragma": "no-cache",
                },
            )

            with urlopen(req, timeout=40) as response:

                status = getattr(response, "status", 200)

                if status != 200:
                    raise RuntimeError(
                        f"HTTP {status}"
                    )

                raw = response.read()

                charset = (
                    response.headers.get_content_charset()
                    or "utf-8"
                )

                try:
                    return raw.decode(
                        charset,
                        errors="ignore",
                    )

                except LookupError:
                    return raw.decode(
                        "utf-8",
                        errors="ignore",
                    )

        except Exception as exc:

            last_error = exc

            print(
                f"下載失敗 {attempt}/{retries}："
                f"{url}｜{exc}"
            )

            if attempt < retries:
                time.sleep(3)

    raise RuntimeError(
        f"下載失敗：{url}｜{last_error}"
    )


# ============================================================
# 共用驗證
# ============================================================

def valid_nums(nums) -> bool:

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


def normalize_date(value: str) -> str:

    value = re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()

    value = re.sub(
        r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
        r"(day)?,?\s+",
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

            return datetime.strptime(
                value,
                fmt,
            ).strftime("%Y/%m/%d")

        except ValueError:
            pass

    match = re.search(
        r"(20\d{2})[/-]"
        r"(\d{1,2})[/-]"
        r"(\d{1,2})",
        value,
    )

    if match:

        year, month, day = map(
            int,
            match.groups(),
        )

        return (
            f"{year:04d}/"
            f"{month:02d}/"
            f"{day:02d}"
        )

    match = re.search(
        r"([A-Za-z]+)\s+"
        r"(\d{1,2}),?\s+"
        r"(20\d{2})",
        value,
    )

    if match:

        month_name, day, year = (
            match.groups()
        )

        for fmt in (
            "%B %d %Y",
            "%b %d %Y",
        ):

            try:

                return datetime.strptime(
                    f"{month_name} {day} {year}",
                    fmt,
                ).strftime("%Y/%m/%d")

            except ValueError:
                pass

    raise RuntimeError(
        f"日期無法辨識：{value!r}"
    )


def validate_recent_date(date_text: str) -> None:

    parsed = datetime.strptime(
        date_text,
        "%Y/%m/%d",
    )

    if parsed.year < 2020:

        raise RuntimeError(
            f"日期年份異常：{date_text}"
        )


def parse_five_comma_numbers(
    text: str,
) -> list[int]:

    match = re.search(
        r"(?<!\d)"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"(?!\d)",
        text,
    )

    if not match:
        return []

    nums = [
        int(value)
        for value in match.groups()
    ]

    if valid_nums(nums):
        return nums

    return []


def unique_in_order(
    values: list[int],
) -> list[int]:

    result = []

    for value in values:

        if value not in result:
            result.append(value)

    return result


# ============================================================
# 539
# ============================================================

def parse_pilio_date(
    line: str,
) -> str:

    # Pilio 格式：
    # 08/07 26(五)
    #
    # 26 = 2026 年

    match = re.search(
        r"(?<!\d)"
        r"(\d{1,2})/"
        r"(\d{1,2})\s+"
        r"(\d{2})"
        r"(?:\([^)]*\))?",
        line,
    )

    if match:

        month, day, year_2 = map(
            int,
            match.groups(),
        )

        year = 2000 + year_2

        date = (
            f"{year:04d}/"
            f"{month:02d}/"
            f"{day:02d}"
        )

        validate_recent_date(date)

        return date

    # 完整西元年

    match = re.search(
        r"(20\d{2})[/-]"
        r"(\d{1,2})[/-]"
        r"(\d{1,2})",
        line,
    )

    if match:

        year, month, day = map(
            int,
            match.groups(),
        )

        date = (
            f"{year:04d}/"
            f"{month:02d}/"
            f"{day:02d}"
        )

        validate_recent_date(date)

        return date

    # 民國年

    match = re.search(
        r"(?<!\d)"
        r"(1\d{2})[/-]"
        r"(\d{1,2})[/-]"
        r"(\d{1,2})"
        r"(?!\d)",
        line,
    )

    if match:

        roc_year, month, day = map(
            int,
            match.groups(),
        )

        year = 1911 + roc_year

        date = (
            f"{year:04d}/"
            f"{month:02d}/"
            f"{day:02d}"
        )

        validate_recent_date(date)

        return date

    raise RuntimeError(
        f"Pilio找不到日期：{line!r}"
    )


def parse_pilio_539(
    url: str,
) -> dict:

    html = fetch(url)

    soup = BeautifulSoup(
        html,
        "lxml",
    )

    candidates = []

    for tr in soup.find_all("tr"):

        cells = [
            re.sub(
                r"\s+",
                " ",
                cell.get_text(
                    " ",
                    strip=True,
                ),
            )
            for cell in tr.find_all(
                ["td", "th"]
            )
        ]

        if not cells:
            continue

        line = " | ".join(cells)

        nums = parse_five_comma_numbers(
            line
        )

        if not valid_nums(nums):
            continue

        try:

            date = parse_pilio_date(
                line
            )

        except Exception:
            continue

        candidates.append(
            {
                "date": date,
                "issue": "",
                "nums": sorted(nums),
                "source": url,
            }
        )

    if not candidates:

        raise RuntimeError(
            "找不到539開獎資料"
        )

    # 一律取最新日期
    candidates.sort(
        key=lambda x: datetime.strptime(
            x["date"],
            "%Y/%m/%d",
        ),
        reverse=True,
    )

    return candidates[0]


def fetch_539() -> dict:

    urls = [

        # 第一來源
        (
            "https://www.pilio.idv.tw/"
            "lto539/list.asp"
        ),

        # 第二來源
        (
            "https://www.pilio.idv.tw/"
            "lto539/drawlist/drawlist.asp"
            "?orderby=new"
        ),

        # 第三次用不同網址參數，
        # 避免取得 CDN / 網頁舊快取
        (
            "https://www.pilio.idv.tw/"
            "lto539/drawlist/drawlist.asp"
            "?orderby=new&nocache=1"
        ),
    ]

    results = []
    errors = []

    for url in urls:

        try:

            result = parse_pilio_539(
                url
            )

            if not valid_nums(
                result["nums"]
            ):
                raise RuntimeError(
                    "號碼驗證失敗"
                )

            results.append(result)

            print(
                "539來源成功："
                f"{url}"
            )

            print(
                "539資料："
                f"{result['date']}｜"
                + " ".join(
                    f"{n:02d}"
                    for n in result["nums"]
                )
            )

        except Exception as exc:

            errors.append(
                f"{url}: {exc}"
            )

            print(
                "539來源失敗："
                f"{url}｜{exc}"
            )

    if not results:

        raise RuntimeError(
            "539所有來源皆失敗；"
            + " | ".join(errors)
        )

    # 多來源成功時取日期最新的
    results.sort(
        key=lambda x: datetime.strptime(
            x["date"],
            "%Y/%m/%d",
        ),
        reverse=True,
    )

    newest = results[0]

    return newest


# ============================================================
# 天天樂 / California Fantasy 5
# ============================================================

def extract_ball_elements(
    container,
) -> list[int]:

    selectors = (
        ".ball",
        "[class*='ball']",
        "[class*='winning-number']",
        "[class*='winning_number']",
        "[class*='draw-number']",
        "[data-testid*='ball']",
        "[aria-label*='ball']",
    )

    values = []

    for selector in selectors:

        for node in container.select(
            selector
        ):

            value = re.sub(
                r"\s+",
                " ",
                node.get_text(
                    " ",
                    strip=True,
                ),
            )

            if re.fullmatch(
                r"0?[1-9]|[12]\d|3[0-9]",
                value,
            ):

                values.append(
                    int(value)
                )

    return unique_in_order(
        values
    )


def official_winning_container(
    soup: BeautifulSoup,
):

    labels = soup.find_all(
        string=lambda value: (
            isinstance(value, str)
            and "winning numbers"
            in value.lower()
        )
    )

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
                    strip=True,
                ),
            )

            has_date = bool(
                re.search(
                    r"(?:MON|TUE|WED|THU|"
                    r"FRI|SAT|SUN)"
                    r"/[A-Z]{3}\s+"
                    r"\d{1,2},\s+"
                    r"20\d{2}",
                    text,
                    flags=re.I,
                )
            )

            has_issue = bool(
                re.search(
                    r"Draw\s*#\s*\d+",
                    text,
                    flags=re.I,
                )
            )

            if has_date and has_issue:

                return node

            node = node.parent

    return None


def parse_calottery_official_page() -> dict:

    url = (
        "https://www.calottery.com/"
        "en/draw-games/fantasy-5"
        "?nocache=1"
    )

    html = fetch(url)

    soup = BeautifulSoup(
        html,
        "lxml",
    )

    container = (
        official_winning_container(
            soup
        )
    )

    if container is None:

        raise RuntimeError(
            "官方網站找不到Winning Numbers"
        )

    text = re.sub(
        r"\s+",
        " ",
        container.get_text(
            " ",
            strip=True,
        ),
    )

    date_match = re.search(
        r"(?:MON|TUE|WED|THU|"
        r"FRI|SAT|SUN)"
        r"/([A-Z]{3})\s+"
        r"(\d{1,2}),\s+"
        r"(20\d{2})",
        text,
        flags=re.I,
    )

    if not date_match:

        raise RuntimeError(
            "官方頁面找不到日期"
        )

    month_name, day, year = (
        date_match.groups()
    )

    california_date = datetime.strptime(
        f"{month_name.title()} "
        f"{day} {year}",
        "%b %d %Y",
    )

    # 加州晚上開獎時，
    # 台灣已經是隔天
    taiwan_date = (
        california_date
        + timedelta(days=1)
    )

    date = taiwan_date.strftime(
        "%Y/%m/%d"
    )

    validate_recent_date(date)

    issue_match = re.search(
        r"Draw\s*#\s*(\d+)",
        text,
        flags=re.I,
    )

    if not issue_match:

        raise RuntimeError(
            "官方頁面找不到期號"
        )

    issue = issue_match.group(1)

    nums = extract_ball_elements(
        container
    )

    # DOM 中可能同時存在
    # 手機版 / 電腦版相同球號
    if len(nums) >= 5:

        found = None

        for index in range(
            len(nums) - 4
        ):

            candidate = nums[
                index:index + 5
            ]

            if valid_nums(candidate):

                found = candidate
                break

        if found:
            nums = found

    # DOM 抓不到時，
    # 改由 Draw # 後面的文字找
    if not valid_nums(nums):

        after_issue = text[
            issue_match.end():
        ]

        stop = re.search(
            r"(?:Draw Results|"
            r"Prize Payouts|"
            r"Winning Details|"
            r"Next Draw|"
            r"Estimated Jackpot|"
            r"Past Winning Numbers|"
            r"How to Play)",
            after_issue,
            flags=re.I,
        )

        if stop:

            after_issue = (
                after_issue[
                    :stop.start()
                ]
            )

        candidates = [
            int(value)
            for value in re.findall(
                r"(?<!\d)"
                r"(0?[1-9]|[12]\d|"
                r"3[0-9])"
                r"(?!\d)",
                after_issue,
            )
        ]

        candidates = unique_in_order(
            candidates
        )

        if len(candidates) >= 5:

            for index in range(
                len(candidates) - 5,
                -1,
                -1,
            ):

                candidate = (
                    candidates[
                        index:index + 5
                    ]
                )

                if valid_nums(
                    candidate
                ):

                    nums = candidate
                    break

    if not valid_nums(nums):

        raise RuntimeError(
            "官方Fantasy 5"
            "球號解析失敗"
        )

    return {
        "date": date,
        "issue": issue,
        "nums": sorted(nums),
        "source": url,
    }


# ============================================================
# 天天樂備援 LotteryUSA
# ============================================================

def parse_lotteryusa_fallback() -> dict:

    url = (
        "https://www.lotteryusa.com/"
        "california/fantasy-5/year"
    )

    html = fetch(url)

    soup = BeautifulSoup(
        html,
        "lxml",
    )

    found_results = []

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
                strip=True,
            ),
        )

        date_match = re.search(
            r"(Monday|Tuesday|"
            r"Wednesday|Thursday|"
            r"Friday|Saturday|Sunday)"
            r",?\s+"
            r"([A-Za-z]+\s+"
            r"\d{1,2},\s+"
            r"20\d{2})",
            text,
            flags=re.I,
        )

        if not date_match:
            continue

        values = extract_ball_elements(
            node
        )

        if len(values) < 5:
            continue

        for index in range(
            len(values) - 4
        ):

            candidate = values[
                index:index + 5
            ]

            if not valid_nums(
                candidate
            ):
                continue

            date_string = (
                date_match.group(2)
            )

            source_date = datetime.strptime(
                normalize_date(
                    date_string
                ),
                "%Y/%m/%d",
            )

            # LotteryUSA 顯示的是
            # 加州當地日期，
            # 台灣日期 +1 天
            date = (
                source_date
                + timedelta(days=1)
            ).strftime(
                "%Y/%m/%d"
            )

            validate_recent_date(date)

            found_results.append(
                {
                    "date": date,
                    "issue": "",
                    "nums": sorted(
                        candidate
                    ),
                    "source": url,
                }
            )

            break

    if not found_results:

        raise RuntimeError(
            "LotteryUSA找不到"
            "Fantasy 5資料"
        )

    found_results.sort(
        key=lambda x: datetime.strptime(
            x["date"],
            "%Y/%m/%d",
        ),
        reverse=True,
    )

    return found_results[0]


def fetch_fantasy5() -> dict:

    parsers = (
        parse_calottery_official_page,
        parse_lotteryusa_fallback,
    )

    results = []
    errors = []

    for parser in parsers:

        try:

            result = parser()

            if not result.get("date"):

                raise RuntimeError(
                    "日期空白"
                )

            validate_recent_date(
                result["date"]
            )

            if not valid_nums(
                result.get("nums")
            ):

                raise RuntimeError(
                    "號碼格式錯誤"
                )

            results.append(result)

            print(
                "天天樂來源成功："
                f"{result['source']}"
            )

            print(
                "天天樂資料："
                f"{result['date']}｜"
                + " ".join(
                    f"{n:02d}"
                    for n in result["nums"]
                )
            )

        except Exception as exc:

            errors.append(
                f"{parser.__name__}: "
                f"{exc}"
            )

            print(
                "天天樂來源失敗："
                f"{parser.__name__}｜"
                f"{exc}"
            )

    if not results:

        raise RuntimeError(
            "Fantasy 5所有來源皆失敗；"
            + " | ".join(errors)
        )

    # 如果兩個來源日期不同，
    # 一律採最新日期
    results.sort(
        key=lambda x: datetime.strptime(
            x["date"],
            "%Y/%m/%d",
        ),
        reverse=True,
    )

    return results[0]


# ============================================================
# 舊資料
# ============================================================

def load_old() -> dict:

    if not OUTPUT_FILE.exists():
        return {}

    try:

        return json.loads(
           
