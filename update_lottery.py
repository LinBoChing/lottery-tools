#!/usr/bin/env python3

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


# ============================================================
# 固定檔案
# ============================================================

OUTPUT_FILE = Path("latest-draws.json")

HISTORY_FILES = {
    "539": Path("history-539.json"),
    "dayday": Path("history-dayday.json"),
}

MAX_HISTORY_DRAWS = 500


# ============================================================
# 唯一資料來源
# ============================================================

# 今彩539：唯一來源
URL_539 = "https://www.lotto-8.com/listlto539bbk.asp"

# 加州天天樂：唯一來源
URL_DAYDAY = "https://sc888.net/index.php?s=/LotteryFan/index"


UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


# ============================================================
# 基本抓取
# ============================================================

def fetch(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )

    with urlopen(req, timeout=35) as response:
        status = getattr(response, "status", 200)

        if status != 200:
            raise RuntimeError(f"HTTP {status}: {url}")

        raw = response.read()

        charset = (
            response.headers.get_content_charset()
            or "utf-8"
        )

        try:
            return raw.decode(charset, errors="ignore")
        except LookupError:
            return raw.decode("utf-8", errors="ignore")


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


def validate_recent_date(date_text: str) -> None:
    parsed = datetime.strptime(
        date_text,
        "%Y/%m/%d",
    )

    if parsed.year < 2020:
        raise RuntimeError(
            f"日期年份異常：{date_text}"
        )


def valid_game(game) -> bool:

    if not isinstance(game, dict):
        return False

    date = str(
        game.get("date", "")
    ).strip()

    nums = game.get("nums")

    if not date:
        return False

    if not valid_nums(nums):
        return False

    try:
        validate_recent_date(date)
    except Exception:
        return False

    return True


# ============================================================
# 539
# lotto-8.com 唯一來源
# ============================================================

def fetch_539() -> dict:

    html = fetch(URL_539)

    soup = BeautifulSoup(
        html,
        "lxml",
    )

    candidates = []

    # --------------------------------------------------------
    # 先從表格逐列找
    # --------------------------------------------------------

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

        # ----------------------------------------------------
        # 日期格式：
        # 2026 08/08
        # 或
        # 2026 08/08 (六)
        # ----------------------------------------------------

        date_match = re.search(
            r"\b(20\d{2})\s+"
            r"(\d{1,2})/"
            r"(\d{1,2})\b",
            line,
        )

        if not date_match:
            continue

        year = int(
            date_match.group(1)
        )

        month = int(
            date_match.group(2)
        )

        day = int(
            date_match.group(3)
        )

        date = (
            f"{year:04d}/"
            f"{month:02d}/"
            f"{day:02d}"
        )

        try:
            validate_recent_date(date)
        except Exception:
            continue

        # ----------------------------------------------------
        # 找五個開獎號碼
        # lotto-8 格式：
        # 05, 11, 24, 31, 32
        # ----------------------------------------------------

        nums_match = re.search(
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
            line,
        )

        if not nums_match:
            continue

        nums = [
            int(x)
            for x in nums_match.groups()
        ]

        if not valid_nums(nums):
            continue

        candidates.append(
            {
                "date": date,
                "issue": "",
                "nums": sorted(nums),
                "source": URL_539,
            }
        )

    # --------------------------------------------------------
    # 找不到就失敗
    # 不使用任何其他網站
    # --------------------------------------------------------

    if not candidates:
        raise RuntimeError(
            "lotto-8 找不到539最新開獎資料"
        )

    # 日期最新的放前面
    candidates.sort(
        key=lambda x: datetime.strptime(
            x["date"],
            "%Y/%m/%d",
        ),
        reverse=True,
    )

    latest = candidates[0]

    print(
        "539來源：lotto-8.com"
    )

    print(
        "539抓取結果："
        f"{latest['date']}｜"
        + " ".join(
            f"{n:02d}"
            for n in latest["nums"]
        )
    )

    return latest


# ============================================================
# 天天樂
# SC888 唯一來源
# ============================================================

def fetch_dayday() -> dict:

    html = fetch(URL_DAYDAY)

    soup = BeautifulSoup(
        html,
        "lxml",
    )

    candidates = []

    # --------------------------------------------------------
    # SC888 表格格式：
    #
    # 第 11963 期2026-08-09 星期日
    # 05 11 14 27 33
    # --------------------------------------------------------

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

        if len(cells) < 2:
            continue

        line = " | ".join(cells)

        # ----------------------------------------------------
        # 期號
        # ----------------------------------------------------

        issue_match = re.search(
            r"第\s*(\d+)\s*期",
            line,
        )

        if not issue_match:
            continue

        issue = issue_match.group(1)

        # ----------------------------------------------------
        # 日期
        # ----------------------------------------------------

        date_match = re.search(
            r"(20\d{2})[-/]"
            r"(\d{1,2})[-/]"
            r"(\d{1,2})",
            line,
        )

        if not date_match:
            continue

        year = int(
            date_match.group(1)
        )

        month = int(
            date_match.group(2)
        )

        day = int(
            date_match.group(3)
        )

        date = (
            f"{year:04d}/"
            f"{month:02d}/"
            f"{day:02d}"
        )

        try:
            validate_recent_date(date)
        except Exception:
            continue

        # ----------------------------------------------------
        # 第二欄通常就是5個球號
        # ----------------------------------------------------

        nums = []

        for cell in cells[1:]:

            values = [
                int(v)
                for v in re.findall(
                    r"(?<!\d)"
                    r"(0?[1-9]|[12]\d|3[0-9])"
                    r"(?!\d)",
                    cell,
                )
            ]

            # 完整五個號碼的欄位
            if (
                len(values) == 5
                and valid_nums(values)
            ):
                nums = values
                break

        if not valid_nums(nums):
            continue

        candidates.append(
            {
                "date": date,
                "issue": issue,
                "nums": sorted(nums),
                "source": URL_DAYDAY,
            }
        )

    # --------------------------------------------------------
    # 找不到就失敗
    # 不使用加州官方
    # 不使用 LotteryUSA
    # --------------------------------------------------------

    if not candidates:
        raise RuntimeError(
            "SC888 找不到天天樂最新開獎資料"
        )

    # --------------------------------------------------------
    # 優先用期號判斷最新
    # --------------------------------------------------------

    candidates.sort(
        key=lambda x: int(
            x["issue"]
        ),
        reverse=True,
    )

    latest = candidates[0]

    print(
        "天天樂來源：SC888"
    )

    print(
        "天天樂抓取結果："
        f"第{latest['issue']}期｜"
        f"{latest['date']}｜"
        + " ".join(
            f"{n:02d}"
            for n in latest["nums"]
        )
    )

    return latest


# ============================================================
# 舊 latest-draws.json
# ============================================================

def load_old() -> dict:

    if not OUTPUT_FILE.exists():
        return {}

    try:
        return json.loads(
            OUTPUT_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        return {}


# ============================================================
# 歷史資料
# ============================================================

def load_history(key: str) -> dict:

    path = HISTORY_FILES[key]

    if not path.exists():
        return {
            "game": key,
            "updated_at": "",
            "draws": [],
        }

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return {
            "game": key,
            "updated_at": "",
            "draws": [],
        }

    if isinstance(data, list):

        draws = data

    elif isinstance(data, dict):

        draws = data.get(
            "draws",
            [],
        )

    else:

        draws = []

    if not isinstance(draws, list):
        draws = []

    valid_draws = []

    for draw in draws:

        if valid_game(draw):
            valid_draws.append(draw)

    return {
        "game": key,
        "updated_at": (
            str(
                data.get(
                    "updated_at",
                    "",
                )
            )
            if isinstance(data, dict)
            else ""
        ),
        "draws": valid_draws,
    }


# ============================================================
# 防止重複
# ============================================================

def draw_identity(
    key: str,
    draw: dict,
):

    issue = str(
        draw.get(
            "issue",
            "",
        )
    ).strip()

    # 天天樂用期號去重
    if key == "dayday" and issue:

        return (
            "issue",
            issue,
        )

    # 539用日期+號碼去重
    return (
        "date_nums",
        str(
            draw.get(
                "date",
                "",
            )
        ).strip(),
        tuple(
            draw.get(
                "nums",
                [],
            )
        ),
    )


# ============================================================
# 更新歷史資料
# ============================================================

def update_history(
    key: str,
    latest: dict,
    updated_at: str,
) -> None:

    history = load_history(key)

    existing = history.get(
        "draws",
        [],
    )

    merged = [latest]

    seen = {
        draw_identity(
            key,
            latest,
        )
    }

    for draw in existing:

        identity = draw_identity(
            key,
            draw,
        )

        if identity in seen:
            continue

        seen.add(identity)

        merged.append(draw)

    # --------------------------------------------------------
    # 日期最新排前
    # 同日期天天樂期號較大排前
    # --------------------------------------------------------

    def sort_key(draw):

        try:

            date_value = datetime.strptime(
                str(
                    draw.get(
                        "date",
                        "",
                    )
                ),
                "%Y/%m/%d",
            )

        except Exception:

            date_value = datetime.min

        issue_text = str(
            draw.get(
                "issue",
                "",
            )
        ).strip()

        issue_value = (
            int(issue_text)
            if issue_text.isdigit()
            else 0
        )

        return (
            date_value,
            issue_value,
        )

    merged.sort(
        key=sort_key,
        reverse=True,
    )

    merged = merged[
        :MAX_HISTORY_DRAWS
    ]

    output = {
        "game": key,
        "updated_at": updated_at,
        "count": len(merged),
        "draws": merged,
    }

    HISTORY_FILES[key].write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# ============================================================
# 主程式
# ============================================================

def main():

    print(
        "======================================"
    )

    print(
        "開始更新開獎號碼"
    )

    print(
        "539唯一來源：lotto-8.com"
    )

    print(
        "天天樂唯一來源：SC888"
    )

    print(
        "======================================"
    )

    old = load_old()

    old_games = old.get(
        "games",
        {},
    )

    games = {}

    warnings = []

    getters = (
        (
            "539",
            fetch_539,
        ),
        (
            "dayday",
            fetch_dayday,
        ),
    )

    for key, getter in getters:

        try:

            result = getter()

            if not valid_game(result):

                raise RuntimeError(
                    "最終資料驗證失敗"
                )

            games[key] = result

        except Exception as exc:

            warning = (
                f"{key}: {exc}"
            )

            warnings.append(
                warning
            )

            print(
                "WARNING:",
                warning,
            )

            # -----------------------------------------------
            # 唯一來源失敗：
            # 不抓其他網站。
            # 只保留上次成功資料。
            # -----------------------------------------------

            old_game = old_games.get(
                key
            )

            if valid_game(old_game):

                games[key] = old_game

                print(
                    f"{key}來源尚未更新或抓取失敗，"
                    "保留原本最新資料"
                )

            else:

                raise SystemExit(
                    f"{key}抓取失敗，"
                    "而且沒有舊資料可以保留"
                )

    # UTC時間
    updated_at = (
        datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )
    )

    output = {
        "updated_at": updated_at,
        "games": games,
        "warnings": warnings,
    }

    # --------------------------------------------------------
    # latest-draws.json
    # --------------------------------------------------------

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # 歷史資料
    # --------------------------------------------------------

    for key, game in games.items():

        update_history(
            key,
            game,
            updated_at,
        )

        print(
            f"{key}歷史資料已更新："
            f"{HISTORY_FILES[key]}"
        )

    print(
        "======================================"
    )

    print(
        "本次更新完成"
    )

    print(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
