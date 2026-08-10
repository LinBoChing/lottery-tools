#!/usr/bin/env python3

import json
import re
import time
from datetime import datetime, timezone, timedelta
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

# 今彩539唯一來源
URL_539 = "https://www.lotto-8.com/listlto539bbk.asp"

# 天天樂唯一來源
URL_DAYDAY = "https://sc888.net/index.php?s=/LotteryFan/index"

# 每30秒檢查一次
POLL_SECONDS = 30

# 最多持續監看30分鐘
MAX_POLL_MINUTES = 30

# 台灣時區
TW_TZ = timezone(timedelta(hours=8))

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


# ============================================================
# 網頁抓取
# ============================================================

def fetch(url: str) -> str:

    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

    with urlopen(req, timeout=35) as response:

        status = getattr(response, "status", 200)

        if status != 200:
            raise RuntimeError(
                f"HTTP {status}: {url}"
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


# ============================================================
# 驗證函式
# ============================================================

def valid_nums(nums):

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


def valid_game(game):

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
        parsed = datetime.strptime(
            date,
            "%Y/%m/%d",
        )

        if parsed.year < 2020:
            return False

    except Exception:
        return False

    return True


# ============================================================
# 今彩539
# 唯一來源：lotto-8.com
# ============================================================

def fetch_539():

    html = fetch(URL_539)

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

        # ----------------------------------------------------
        # 日期
        # lotto-8 常見格式：
        # 2026 08/08
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

        # ----------------------------------------------------
        # 5個號碼
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
            int(value)
            for value in nums_match.groups()
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

    if not candidates:

        raise RuntimeError(
            "lotto-8 找不到539最新開獎資料"
        )

    candidates.sort(
        key=lambda item: datetime.strptime(
            item["date"],
            "%Y/%m/%d",
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# 天天樂
# 唯一來源：SC888
# ============================================================

def fetch_dayday():

    html = fetch(URL_DAYDAY)

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

        # ----------------------------------------------------
        # 尋找5個號碼
        # ----------------------------------------------------

        nums = []

        for cell in cells[1:]:

            values = [
                int(value)
                for value in re.findall(
                    r"(?<!\d)"
                    r"(0?[1-9]|[12]\d|3[0-9])"
                    r"(?!\d)",
                    cell,
                )
            ]

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

    if not candidates:

        raise RuntimeError(
            "SC888 找不到天天樂最新開獎資料"
        )

    # 最新期號優先
    candidates.sort(
        key=lambda item: int(
            item["issue"]
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# latest-draws.json
# ============================================================

def load_old():

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

def load_history(key):

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

        data = {}

    if isinstance(data, dict):

        draws = data.get(
            "draws",
            [],
        )

    elif isinstance(data, list):

        draws = data

    else:

        draws = []

    if not isinstance(draws, list):

        draws = []

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
        "draws": [
            draw
            for draw in draws
            if valid_game(draw)
        ],
    }


# ============================================================
# 判斷是否為新一期
# ============================================================

def is_new_draw(
    key,
    old_game,
    new_game,
):

    if not valid_game(new_game):

        return False

    # 沒有舊資料，直接視為新資料
    if not valid_game(old_game):

        return True

    # --------------------------------------------------------
    # 天天樂優先比較期號
    # --------------------------------------------------------

    if key == "dayday":

        old_issue = str(
            old_game.get(
                "issue",
                "",
            )
        ).strip()

        new_issue = str(
            new_game.get(
                "issue",
                "",
            )
        ).strip()

        if (
            old_issue.isdigit()
            and new_issue.isdigit()
        ):

            if int(new_issue) > int(old_issue):
                return True

            if int(new_issue) < int(old_issue):
                return False

    # --------------------------------------------------------
    # 比較日期
    # --------------------------------------------------------

    old_date = str(
        old_game.get(
            "date",
            "",
        )
    )

    new_date = str(
        new_game.get(
            "date",
            "",
        )
    )

    if new_date > old_date:
        return True

    # --------------------------------------------------------
    # 同一天號碼不同
    # 也視為資料更新
    # --------------------------------------------------------

    if (
        new_date == old_date
        and new_game.get("nums")
        != old_game.get("nums")
    ):

        return True

    return False


# ============================================================
# 去重
# ============================================================

def draw_identity(
    key,
    draw,
):

    issue = str(
        draw.get(
            "issue",
            "",
        )
    ).strip()

    if (
        key == "dayday"
        and issue
    ):

        return (
            "issue",
            issue,
        )

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
    key,
    latest,
    updated_at,
):

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
        ) + "\n",
        encoding="utf-8",
    )


# ============================================================
# 寫入最新一期
# ============================================================

def save_game(
    key,
    latest,
):

    old = load_old()

    old_games = old.get(
        "games",
        {},
    )

    games = dict(
        old_games
    )

    # 只替換本次更新的彩種
    games[key] = latest

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
        "warnings": [],
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    update_history(
        key,
        latest,
        updated_at,
    )

    print(
        f"{key} 已寫入 "
        f"{OUTPUT_FILE}"
    )

    print(
        f"{key} 歷史資料已更新 "
        f"{HISTORY_FILES[key]}"
    )


# ============================================================
# 30秒輪詢
# ============================================================

def poll_game(
    key,
    getter,
):

    # 啟動時先讀目前JSON資料
    old = load_old()

    old_game = (
        old.get(
            "games",
            {}
        ).get(
            key,
            {}
        )
    )

    max_checks = int(
        MAX_POLL_MINUTES
        * 60
        / POLL_SECONDS
    )

    print(
        "======================================"
    )

    if key == "539":

        print(
            "開始即時監看：539"
        )

        print(
            "唯一來源：lotto-8.com"
        )

    else:

        print(
            "開始即時監看：天天樂"
        )

        print(
            "唯一來源：SC888"
        )

    print(
        f"每 {POLL_SECONDS} 秒檢查一次"
    )

    print(
        f"最多監看 {MAX_POLL_MINUTES} 分鐘"
    )

    if valid_game(old_game):

        print(
            "JSON目前資料："
            f"{old_game.get('date')}｜"
            + " ".join(
                f"{n:02d}"
                for n in old_game.get(
                    "nums",
                    [],
                )
            )
        )

        if key == "dayday":

            print(
                "JSON目前期號："
                f"{old_game.get('issue', '')}"
            )

    print(
        "======================================"
    )

    for check in range(
        1,
        max_checks + 1,
    ):

        now_tw = datetime.now(
            TW_TZ
        )

        print(
            f"[{now_tw:%Y/%m/%d %H:%M:%S}] "
            f"第 {check}/{max_checks} 次檢查"
        )

        try:

            latest = getter()

            message = (
                f"網站目前："
                f"{latest['date']}｜"
                + " ".join(
                    f"{n:02d}"
                    for n in latest["nums"]
                )
            )

            if key == "dayday":

                message += (
                    f"｜第{latest.get('issue', '')}期"
                )

            print(message)

            # ------------------------------------------------
            # 發現新一期
            # ------------------------------------------------

            if is_new_draw(
                key,
                old_game,
                latest,
            ):

                print(
                    "★ 發現新一期開獎號碼 ★"
                )

                print(
                    "立即更新 latest-draws.json"
                )

                save_game(
                    key,
                    latest,
                )

                print(
                    "★ 更新成功，停止監看 ★"
                )

                return True

            print(
                "尚未出現新一期，30秒後再檢查。"
            )

        except Exception as exc:

            print(
                "WARNING：本次抓取失敗：",
                exc,
            )

        if check < max_checks:

            time.sleep(
                POLL_SECONDS
            )

    print(
        "======================================"
    )

    print(
        f"{MAX_POLL_MINUTES}分鐘內"
        "沒有發現新一期。"
    )

    print(
        "結束本次監看，保留原資料。"
    )

    return False


# ============================================================
# 手動測試
# ============================================================

def manual_fetch_all():

    print(
        "非自動監看時段。"
    )

    print(
        "執行手動測試模式："
        "539與天天樂各抓一次。"
    )

    old = load_old()

    games = dict(
        old.get(
            "games",
            {},
        )
    )

    warnings = []

    for key, getter in (
        (
            "539",
            fetch_539,
        ),
        (
            "dayday",
            fetch_dayday,
        ),
    ):

        try:

            latest = getter()

            games[key] = latest

            text = (
                f"{key}："
                f"{latest['date']}｜"
                + " ".join(
                    f"{n:02d}"
                    for n in latest["nums"]
                )
            )

            if key == "dayday":

                text += (
                    f"｜第"
                    f"{latest.get('issue', '')}"
                    f"期"
                )

            print(text)

        except Exception as exc:

            warning = (
                f"{key}抓取失敗：{exc}"
            )

            warnings.append(
                warning
            )

            print(
                "WARNING：",
                warning,
            )

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

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    for key, game in games.items():

        if valid_game(game):

            update_history(
                key,
                game,
                updated_at,
            )

    print(
        "手動測試完成。"
    )


# ============================================================
# 主程式
# ============================================================

def main():

    now_tw = datetime.now(
        TW_TZ
    )

    print(
        "======================================"
    )

    print(
        "台灣時間："
        + now_tw.strftime(
            "%Y/%m/%d %H:%M:%S"
        )
    )

    print(
        "======================================"
    )

    hour = now_tw.hour
    minute = now_tw.minute

    # ========================================================
    # 天天樂監看時段
    #
    # 排程原本09:47啟動。
    # 但GitHub可能延遲，所以放寬：
    #
    # 09:40 ～ 10:40
    #
    # 即使GitHub 10點多才啟動，
    # 仍然會進天天樂監看模式。
    # ========================================================

    in_dayday_window = (
        (hour == 9 and minute >= 40)
        or
        (hour == 10 and minute <= 40)
    )

    if in_dayday_window:

        print(
            "判定：天天樂即時監看時段"
        )

        poll_game(
            "dayday",
            fetch_dayday,
        )

        return

    # ========================================================
    # 539監看時段
    #
    # 排程20:32啟動。
    # GitHub可能延遲，所以放寬：
    #
    # 20:25 ～ 21:30
    # ========================================================

    in_539_window = (
        (hour == 20 and minute >= 25)
        or
        (hour == 21 and minute <= 30)
    )

    if in_539_window:

        # 星期日沒有539
        # Python datetime.weekday():
        # Monday=0 ... Sunday=6

        if now_tw.weekday() == 6:

            print(
                "今天星期日，539不開獎。"
            )

            print(
                "跳過539監看。"
            )

            return

        print(
            "判定：539即時監看時段"
        )

        poll_game(
            "539",
            fetch_539,
        )

        return

    # ========================================================
    # 其他時間
    # 手動Run workflow時測試兩個來源
    # ========================================================

    manual_fetch_all()


if __name__ == "__main__":
    main()
