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

URL_539 = "https://www.lotto-8.com/listlto539bbk.asp"
URL_DAYDAY = "https://sc888.net/index.php?s=/LotteryFan/index"

POLL_SECONDS = 30
MAX_POLL_MINUTES = 30

TW_TZ = timezone(timedelta(hours=8))

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


# ============================================================
# 即時輸出
# ============================================================

def log(*args):
    print(*args, flush=True)


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
# 驗證
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

    date = str(game.get("date", "")).strip()
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
                cell.get_text(" ", strip=True),
            )
            for cell in tr.find_all(["td", "th"])
        ]

        if not cells:
            continue

        line = " | ".join(cells)

        date_match = re.search(
            r"\b(20\d{2})\s+"
            r"(\d{1,2})/"
            r"(\d{1,2})\b",
            line,
        )

        if not date_match:
            continue

        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))

        date = (
            f"{year:04d}/"
            f"{month:02d}/"
            f"{day:02d}"
        )

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
                cell.get_text(" ", strip=True),
            )
            for cell in tr.find_all(["td", "th"])
        ]

        if len(cells) < 2:
            continue

        line = " | ".join(cells)

        issue_match = re.search(
            r"第\s*(\d+)\s*期",
            line,
        )

        date_match = re.search(
            r"(20\d{2})[-/]"
            r"(\d{1,2})[-/]"
            r"(\d{1,2})",
            line,
        )

        if not issue_match or not date_match:
            continue

        issue = issue_match.group(1)

        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))

        date = (
            f"{year:04d}/"
            f"{month:02d}/"
            f"{day:02d}"
        )

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

    candidates.sort(
        key=lambda item: int(item["issue"]),
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
        draws = data.get("draws", [])
    elif isinstance(data, list):
        draws = data
    else:
        draws = []

    if not isinstance(draws, list):
        draws = []

    return {
        "game": key,
        "updated_at": (
            str(data.get("updated_at", ""))
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
# 判斷兩筆資料是否完全相同
# ============================================================

def same_draw(key, a, b):

    if not valid_game(a):
        return False

    if not valid_game(b):
        return False

    if key == "dayday":

        return (
            str(a.get("issue", "")).strip()
            == str(b.get("issue", "")).strip()
            and a.get("date") == b.get("date")
            and a.get("nums") == b.get("nums")
        )

    return (
        a.get("date") == b.get("date")
        and a.get("nums") == b.get("nums")
    )


# ============================================================
# 判斷是否已經是今天最新資料
# ============================================================

def already_today(key, old_game, website_game):

    today = datetime.now(
        TW_TZ
    ).strftime("%Y/%m/%d")

    if not same_draw(
        key,
        old_game,
        website_game,
    ):
        return False

    return (
        website_game.get("date") == today
    )


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

    if not valid_game(old_game):
        return True

    if key == "dayday":

        old_issue = str(
            old_game.get("issue", "")
        ).strip()

        new_issue = str(
            new_game.get("issue", "")
        ).strip()

        if (
            old_issue.isdigit()
            and new_issue.isdigit()
        ):

            if int(new_issue) > int(old_issue):
                return True

            if int(new_issue) < int(old_issue):
                return False

    old_date = str(
        old_game.get("date", "")
    )

    new_date = str(
        new_game.get("date", "")
    )

    if new_date > old_date:
        return True

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
        draw.get("issue", "")
    ).strip()

    if key == "dayday" and issue:

        return (
            "issue",
            issue,
        )

    return (
        "date_nums",
        str(draw.get("date", "")).strip(),
        tuple(draw.get("nums", [])),
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

    merged = [latest]

    seen = {
        draw_identity(
            key,
            latest,
        )
    }

    for draw in history["draws"]:

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
                str(draw.get("date", "")),
                "%Y/%m/%d",
            )
        except Exception:
            date_value = datetime.min

        issue_text = str(
            draw.get("issue", "")
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

    merged = merged[:MAX_HISTORY_DRAWS]

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
# 寫入新資料
# ============================================================

def save_game(
    key,
    latest,
):

    old = load_old()

    games = dict(
        old.get("games", {})
    )

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

    log(
        f"✅ {key} 已寫入 latest-draws.json"
    )


# ============================================================
# 30秒即時監看
# ============================================================

def poll_game(
    key,
    getter,
):

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

    log(
        "======================================"
    )

    if key == "539":
        log("開始即時監看：539")
        log("唯一來源：lotto-8.com")
    else:
        log("開始即時監看：天天樂")
        log("唯一來源：SC888")

    log(
        f"每 {POLL_SECONDS} 秒檢查一次"
    )

    log(
        f"最多監看 {MAX_POLL_MINUTES} 分鐘"
    )

    if valid_game(old_game):

        log(
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

            log(
                "JSON目前期號："
                f"{old_game.get('issue', '')}"
            )

    log(
        "======================================"
    )

    for check in range(
        1,
        max_checks + 1,
    ):

        now_tw = datetime.now(
            TW_TZ
        )

        log(
            f"[{now_tw:%Y/%m/%d %H:%M:%S}] "
            f"第 {check}/{max_checks} 次檢查"
        )

        try:

            latest = getter()

            text = (
                f"網站目前："
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

            log(text)

            # =================================================
            # 關鍵修正：
            # JSON已經是今天最新一期
            # 立即停止，不再等待30分鐘
            # =================================================

            if already_today(
                key,
                old_game,
                latest,
            ):

                log(
                    "✅ JSON已經是今天最新一期。"
                )

                log(
                    "不需要再次更新，立即結束監看。"
                )

                return True

            # =================================================
            # 網站出現比JSON更新的一期
            # =================================================

            if is_new_draw(
                key,
                old_game,
                latest,
            ):

                log(
                    "🔥 發現新一期開獎號碼！"
                )

                log(
                    "立即寫入資料..."
                )

                save_game(
                    key,
                    latest,
                )

                log(
                    "✅ 更新完成，停止監看。"
                )

                return True

            log(
                f"尚未出現新一期，"
                f"{POLL_SECONDS}秒後再檢查。"
            )

        except Exception as exc:

            log(
                "⚠️ 本次抓取失敗：",
                exc,
            )

        if check < max_checks:

            time.sleep(
                POLL_SECONDS
            )

    log(
        "======================================"
    )

    log(
        f"{MAX_POLL_MINUTES}分鐘內"
        "沒有發現新一期。"
    )

    log(
        "保留目前資料並結束。"
    )

    return False


# ============================================================
# 手動測試
# ============================================================

def manual_fetch_all():

    log(
        "非自動監看時段。"
    )

    log(
        "執行手動測試模式。"
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
        ("539", fetch_539),
        ("dayday", fetch_dayday),
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

            log(text)

        except Exception as exc:

            warning = (
                f"{key}抓取失敗：{exc}"
            )

            warnings.append(
                warning
            )

            log(
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

    log(
        "✅ 手動測試完成。"
    )


# ============================================================
# 主程式
# ============================================================

def main():

    now_tw = datetime.now(
        TW_TZ
    )

    log(
        "======================================"
    )

    log(
        "台灣時間："
        + now_tw.strftime(
            "%Y/%m/%d %H:%M:%S"
        )
    )

    log(
        "======================================"
    )

    hour = now_tw.hour
    minute = now_tw.minute

    # ========================================================
    # 天天樂
    # GitHub即使延遲到10點多啟動仍有效
    #
    # 09:40 ～ 10:40
    # ========================================================

    in_dayday_window = (
        (hour == 9 and minute >= 40)
        or
        (hour == 10 and minute <= 40)
    )

    if in_dayday_window:

        log(
            "判定：天天樂即時監看時段"
        )

        poll_game(
            "dayday",
            fetch_dayday,
        )

        return

    # ========================================================
    # 539
    #
    # 20:25 ～ 21:30
    # ========================================================

    in_539_window = (
        (hour == 20 and minute >= 25)
        or
        (hour == 21 and minute <= 30)
    )

    if in_539_window:

        # 星期日不開539
        if now_tw.weekday() == 6:

            log(
                "今天星期日，539不開獎。"
            )

            return

        log(
            "判定：539即時監看時段"
        )

        poll_game(
            "539",
            fetch_539,
        )

        return

    # ========================================================
    # 其他時間＝手動測試
    # ========================================================

    manual_fetch_all()


if __name__ == "__main__":
    main()
