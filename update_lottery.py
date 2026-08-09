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
# 網頁抓取
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
        raw = response.read()

        charset = response.headers.get_content_charset() or "utf-8"

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

    if not date or not valid_nums(nums):
        return False

    try:
        datetime.strptime(date, "%Y/%m/%d")
    except Exception:
        return False

    return True


# ============================================================
# 539
# 唯一來源 lotto-8.com
# ============================================================

def fetch_539():
    html = fetch(URL_539)
    soup = BeautifulSoup(html, "lxml")

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
            r"\b(20\d{2})\s+(\d{1,2})/(\d{1,2})\b",
            line,
        )

        if not date_match:
            continue

        year, month, day = map(int, date_match.groups())

        date = f"{year:04d}/{month:02d}/{day:02d}"

        nums_match = re.search(
            r"(?<!\d)"
            r"(0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
            r"(0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
            r"(0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
            r"(0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
            r"(0?[1-9]|[12]\d|3[0-9])"
            r"(?!\d)",
            line,
        )

        if not nums_match:
            continue

        nums = [int(x) for x in nums_match.groups()]

        if not valid_nums(nums):
            continue

        candidates.append({
            "date": date,
            "issue": "",
            "nums": sorted(nums),
            "source": URL_539,
        })

    if not candidates:
        raise RuntimeError("lotto-8 找不到539資料")

    candidates.sort(
        key=lambda x: datetime.strptime(
            x["date"],
            "%Y/%m/%d",
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# 天天樂
# 唯一來源 SC888
# ============================================================

def fetch_dayday():
    html = fetch(URL_DAYDAY)
    soup = BeautifulSoup(html, "lxml")

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
            r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})",
            line,
        )

        if not issue_match or not date_match:
            continue

        issue = issue_match.group(1)

        year, month, day = map(
            int,
            date_match.groups(),
        )

        date = f"{year:04d}/{month:02d}/{day:02d}"

        nums = []

        for cell in cells[1:]:
            values = [
                int(v)
                for v in re.findall(
                    r"(?<!\d)(0?[1-9]|[12]\d|3[0-9])(?!\d)",
                    cell,
                )
            ]

            if len(values) == 5 and valid_nums(values):
                nums = values
                break

        if not valid_nums(nums):
            continue

        candidates.append({
            "date": date,
            "issue": issue,
            "nums": sorted(nums),
            "source": URL_DAYDAY,
        })

    if not candidates:
        raise RuntimeError("SC888 找不到天天樂資料")

    candidates.sort(
        key=lambda x: int(x["issue"]),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# JSON
# ============================================================

def load_old():
    if not OUTPUT_FILE.exists():
        return {}

    try:
        return json.loads(
            OUTPUT_FILE.read_text(encoding="utf-8")
        )
    except Exception:
        return {}


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
            path.read_text(encoding="utf-8")
        )
    except Exception:
        data = {}

    draws = data.get("draws", []) if isinstance(data, dict) else []

    return {
        "game": key,
        "updated_at": str(data.get("updated_at", "")),
        "draws": [
            draw
            for draw in draws
            if valid_game(draw)
        ],
    }


# ============================================================
# 判斷是不是新一期
# ============================================================

def is_new_draw(key, old_game, new_game):
    if not valid_game(new_game):
        return False

    if not valid_game(old_game):
        return True

    if key == "dayday":
        old_issue = str(old_game.get("issue", "")).strip()
        new_issue = str(new_game.get("issue", "")).strip()

        if old_issue.isdigit() and new_issue.isdigit():
            return int(new_issue) > int(old_issue)

    old_date = old_game.get("date", "")
    new_date = new_game.get("date", "")

    if new_date > old_date:
        return True

    if (
        new_date == old_date
        and new_game.get("nums") != old_game.get("nums")
    ):
        return True

    return False


# ============================================================
# 歷史資料
# ============================================================

def draw_identity(key, draw):
    issue = str(draw.get("issue", "")).strip()

    if key == "dayday" and issue:
        return ("issue", issue)

    return (
        "date_nums",
        str(draw.get("date", "")).strip(),
        tuple(draw.get("nums", [])),
    )


def update_history(key, latest, updated_at):
    history = load_history(key)

    merged = [latest]
    seen = {draw_identity(key, latest)}

    for draw in history["draws"]:
        identity = draw_identity(key, draw)

        if identity in seen:
            continue

        seen.add(identity)
        merged.append(draw)

    def sort_key(draw):
        try:
            d = datetime.strptime(
                draw.get("date", ""),
                "%Y/%m/%d",
            )
        except Exception:
            d = datetime.min

        issue = str(draw.get("issue", "")).strip()
        issue_num = int(issue) if issue.isdigit() else 0

        return d, issue_num

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
# 寫入結果
# ============================================================

def save_game(key, latest):
    old = load_old()
    games = old.get("games", {})

    games[key] = latest

    # 保留另一彩種原本資料
    updated_at = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

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


# ============================================================
# 30秒即時監看
# ============================================================

def poll_game(key, getter):
    old = load_old()
    old_game = old.get("games", {}).get(key, {})

    max_checks = int(
        MAX_POLL_MINUTES * 60 / POLL_SECONDS
    )

    print("======================================")
    print(f"開始監看：{key}")
    print(f"每 {POLL_SECONDS} 秒檢查一次")
    print(f"最多監看 {MAX_POLL_MINUTES} 分鐘")

    if valid_game(old_game):
        print(
            "目前資料："
            f"{old_game.get('date')}｜"
            + " ".join(
                f"{n:02d}"
                for n in old_game.get("nums", [])
            )
        )

    for check in range(1, max_checks + 1):
        now_tw = datetime.now(TW_TZ)

        print(
            f"[{now_tw:%H:%M:%S}] "
            f"第 {check}/{max_checks} 次檢查"
        )

        try:
            latest = getter()

            print(
                "網站目前："
                f"{latest['date']}｜"
                + " ".join(
                    f"{n:02d}"
                    for n in latest["nums"]
                )
            )

            if is_new_draw(
                key,
                old_game,
                latest,
            ):
                print("★ 發現新一期！立即更新 ★")

                save_game(
                    key,
                    latest,
                )

                print("更新完成，停止監看。")
                return

            print("尚未出現新一期。")

        except Exception as exc:
            print(
                "本次抓取失敗：",
                exc,
            )

        if check < max_checks:
            time.sleep(POLL_SECONDS)

    print(
        f"{MAX_POLL_MINUTES} 分鐘內未發現新一期，"
        "結束本次監看。"
    )


# ============================================================
# 手動測試
# ============================================================

def manual_fetch_all():
    old = load_old()
    games = old.get("games", {})

    for key, getter in (
        ("539", fetch_539),
        ("dayday", fetch_dayday),
    ):
        try:
            latest = getter()

            games[key] = latest

            print(
                f"{key}："
                f"{latest['date']}｜"
                + " ".join(
                    f"{n:02d}"
                    for n in latest["nums"]
                )
            )

        except Exception as exc:
            print(
                f"{key}抓取失敗：{exc}"
            )

    updated_at = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

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

    for key, game in games.items():
        if valid_game(game):
            update_history(
                key,
                game,
                updated_at,
            )


# ============================================================
# 主程式
# ============================================================

def main():
    now_tw = datetime.now(TW_TZ)

    print(
        "台灣時間：",
        now_tw.strftime(
            "%Y/%m/%d %H:%M:%S"
        ),
    )

    hour = now_tw.hour
    minute = now_tw.minute

    # --------------------------------------------------------
    # 天天樂
    # 09:47附近由排程啟動
    # --------------------------------------------------------

    if hour == 9 and 40 <= minute <= 59:
        poll_game(
            "dayday",
            fetch_dayday,
        )
        return

    # --------------------------------------------------------
    # 539
    # 20:32附近由排程啟動
    # --------------------------------------------------------

    if hour == 20 and 25 <= minute <= 59:
        poll_game(
            "539",
            fetch_539,
        )
        return

    # --------------------------------------------------------
    # 其他時間代表手動 Run workflow
    # 兩個來源各測一次
    # --------------------------------------------------------

    print(
        "非指定監看時段，執行手動測試模式。"
    )

    manual_fetch_all()


if __name__ == "__main__":
    main()
