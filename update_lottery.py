#!/usr/bin/env python3
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

OUTPUT_FILE = Path("latest-draws.json")
HISTORY_FILES = {
    "539": Path("history-539.json"),
    "dayday": Path("history-dayday.json"),
}
MAX_HISTORY_DRAWS = 500
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
        year, month, day = map(int, match.groups())
        return f"{year:04d}/{month:02d}/{day:02d}"

    match = re.search(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})",
        value,
    )
    if match:
        month_name, day, year = match.groups()
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                return datetime.strptime(
                    f"{month_name} {day} {year}", fmt
                ).strftime("%Y/%m/%d")
            except ValueError:
                pass

    raise RuntimeError(f"日期無法辨識：{value!r}")


def validate_recent_date(date_text: str) -> None:
    parsed = datetime.strptime(date_text, "%Y/%m/%d")
    if parsed.year < 2020:
        raise RuntimeError(f"日期年份異常：{date_text}")


def parse_five_comma_numbers(text: str) -> list[int]:
    match = re.search(
        r"(?<!\d)(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])"
        r"\s*[,，]\s*"
        r"(0?[1-9]|[12]\d|3[0-9])(?!\d)",
        text,
    )
    if not match:
        return []
    nums = [int(value) for value in match.groups()]
    return nums if valid_nums(nums) else []


def parse_pilio_date(line: str) -> str:
    # Pilio目前格式：
    # 07/30 26(四)
    # 其中「26」代表西元2026年的後兩碼，不是民國26年。
    match = re.search(
        r"(?<!\d)(\d{1,2})/(\d{1,2})\s+(\d{2})(?:\([^)]*\))?",
        line,
    )
    if match:
        month, day, year_2 = map(int, match.groups())
        year = 2000 + year_2
        date = f"{year:04d}/{month:02d}/{day:02d}"
        validate_recent_date(date)
        return date

    # 若網站改成完整西元日期，直接使用。
    match = re.search(
        r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})",
        line,
    )
    if match:
        year, month, day = map(int, match.groups())
        date = f"{year:04d}/{month:02d}/{day:02d}"
        validate_recent_date(date)
        return date

    # 若未來改成完整民國年，例如115/07/30。
    match = re.search(
        r"(?<!\d)(1\d{2})[/-](\d{1,2})[/-](\d{1,2})(?!\d)",
        line,
    )
    if match:
        roc_year, month, day = map(int, match.groups())
        year = 1911 + roc_year
        date = f"{year:04d}/{month:02d}/{day:02d}"
        validate_recent_date(date)
        return date

    raise RuntimeError(f"Pilio資料列找不到可用日期：{line!r}")


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

            for tr in soup.find_all("tr"):
                cells = [
                    re.sub(r"\s+", " ", cell.get_text(" ", strip=True))
                    for cell in tr.find_all(["td", "th"])
                ]
                if not cells:
                    continue

                line = " | ".join(cells)
                nums = parse_five_comma_numbers(line)
                if not valid_nums(nums):
                    continue

                date = parse_pilio_date(line)

                return {
                    "date": date,
                    "issue": "",
                    "nums": sorted(nums),
                    "source": url,
                }

            errors.append(f"{url}: 找不到同列日期與5個開獎號碼")

        except Exception as exc:
            errors.append(f"{url}: {exc}")

    raise RuntimeError("539抓取失敗；" + " | ".join(errors))


def unique_in_order(values: list[int]) -> list[int]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def extract_ball_elements(container) -> list[int]:
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
        for node in container.select(selector):
            value = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
            if re.fullmatch(r"0?[1-9]|[12]\d|3[0-9]", value):
                values.append(int(value))

    return unique_in_order(values)


def official_winning_container(soup: BeautifulSoup):
    # 從文字節點「Winning Numbers」往上尋找最小且含日期、期號的容器。
    labels = soup.find_all(
        string=lambda value: (
            isinstance(value, str)
            and "winning numbers" in value.lower()
        )
    )

    for label in labels:
        node = label.parent
        for _ in range(7):
            if node is None:
                break
            text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
            has_date = bool(
                re.search(
                    r"(?:MON|TUE|WED|THU|FRI|SAT|SUN)"
                    r"/[A-Z]{3}\s+\d{1,2},\s+20\d{2}",
                    text,
                    flags=re.I,
                )
            )
            has_issue = bool(re.search(r"Draw\s*#\s*\d+", text, flags=re.I))
            if has_date and has_issue:
                return node
            node = node.parent

    return None


def parse_calottery_official_page() -> dict:
    url = "https://www.calottery.com/en/draw-games/fantasy-5"
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")

    container = official_winning_container(soup)
    if container is None:
        raise RuntimeError("官方頁面找不到Winning Numbers容器")

    text = re.sub(r"\s+", " ", container.get_text(" ", strip=True))

    date_match = re.search(
        r"(?:MON|TUE|WED|THU|FRI|SAT|SUN)"
        r"/([A-Z]{3})\s+(\d{1,2}),\s+(20\d{2})",
        text,
        flags=re.I,
    )
    if not date_match:
        raise RuntimeError("Winning Numbers容器找不到日期")

    month_name, day, year = date_match.groups()
    california_date = datetime.strptime(
        f"{month_name.title()} {day} {year}",
        "%b %d %Y",
    )
    # 加州晚間開獎時，台灣已經是隔日。
    date = (california_date + timedelta(days=1)).strftime("%Y/%m/%d")
    validate_recent_date(date)

    issue_match = re.search(r"Draw\s*#\s*(\d+)", text, flags=re.I)
    if not issue_match:
        raise RuntimeError("Winning Numbers容器找不到期號")
    issue = issue_match.group(1)

    # 第一優先：讀取官方頁球號DOM元素。
    nums = extract_ball_elements(container)

    # 容器可能含重複的桌機版與手機版元素；尋找任一連續5碼有效組合。
    if len(nums) >= 5:
        for index in range(len(nums) - 4):
            candidate = nums[index:index + 5]
            if valid_nums(candidate):
                nums = candidate
                break

    # 第二優先：從「Draw #期號」後方的有限文字區段取得候選數字。
    # 官方頁曾出現一個額外的「3」在五顆球之前，因此採最後5個有效數字，
    # 避免把前置欄位誤當第一顆球號。
    if not valid_nums(nums):
        after_issue = text[issue_match.end():]
        stop = re.search(
            r"(?:Draw Results|Prize Payouts|Winning Details|"
            r"Next Draw|Estimated Jackpot|Past Winning Numbers|How to Play)",
            after_issue,
            flags=re.I,
        )
        if stop:
            after_issue = after_issue[:stop.start()]

        candidates = [
            int(value)
            for value in re.findall(
                r"(?<!\d)(0?[1-9]|[12]\d|3[0-9])(?!\d)",
                after_issue,
            )
        ]
        candidates = unique_in_order(candidates)

        if len(candidates) >= 5:
            # 從尾端向前尋找有效的連續5碼。
            for index in range(len(candidates) - 5, -1, -1):
                candidate = candidates[index:index + 5]
                if valid_nums(candidate):
                    nums = candidate
                    break

    if not valid_nums(nums):
        raise RuntimeError(
            f"官方Fantasy 5球號解析失敗；容器候選值：{nums}"
        )

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

        values = extract_ball_elements(node)
        if len(values) >= 5:
            for index in range(len(values) - 4):
                candidate = values[index:index + 5]
                if valid_nums(candidate):
                    source_date = datetime.strptime(
                        normalize_date(date_match.group(0)),
                        "%Y/%m/%d",
                    )
                    # 備援網站同樣使用加州當地日期，轉成台灣日期。
                    date = (source_date + timedelta(days=1)).strftime("%Y/%m/%d")
                    validate_recent_date(date)
                    return {
                        "date": date,
                        "issue": "",
                        "nums": sorted(candidate),
                        "source": url,
                    }

    raise RuntimeError("LotteryUSA找不到同區塊日期與5個球號")


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
            validate_recent_date(result["date"])
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
    if not (
        isinstance(game, dict)
        and bool(str(game.get("date", "")).strip())
        and valid_nums(game.get("nums"))
    ):
        return False

    try:
        validate_recent_date(str(game["date"]))
    except Exception:
        return False

    return True



def load_history(key: str) -> dict:
    path = HISTORY_FILES[key]
    if not path.exists():
        return {
            "game": key,
            "updated_at": "",
            "draws": [],
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "game": key,
            "updated_at": "",
            "draws": [],
        }

    if isinstance(data, list):
        draws = data
    elif isinstance(data, dict):
        draws = data.get("draws", [])
    else:
        draws = []

    if not isinstance(draws, list):
        draws = []

    return {
        "game": key,
        "updated_at": str(data.get("updated_at", "")) if isinstance(data, dict) else "",
        "draws": [draw for draw in draws if valid_game(draw)],
    }


def draw_identity(key: str, draw: dict) -> tuple:
    issue = str(draw.get("issue", "")).strip()

    # 天天樂優先用期號去重；539目前沒有期號，改用日期加號碼。
    if key == "dayday" and issue:
        return ("issue", issue)

    return (
        "date_nums",
        str(draw.get("date", "")).strip(),
        tuple(draw.get("nums", [])),
    )


def update_history(key: str, latest: dict, updated_at: str) -> None:
    history = load_history(key)
    existing = history.get("draws", [])

    merged = [latest]
    seen = {draw_identity(key, latest)}

    for draw in existing:
        identity = draw_identity(key, draw)
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(draw)

    # 日期最新的排最上方；相同日期時以期號較大的優先。
    def sort_key(draw: dict):
        try:
            date_value = datetime.strptime(
                str(draw.get("date", "")),
                "%Y/%m/%d",
            )
        except ValueError:
            date_value = datetime.min

        issue_text = str(draw.get("issue", "")).strip()
        issue_value = int(issue_text) if issue_text.isdigit() else 0
        return (date_value, issue_value)

    merged.sort(key=sort_key, reverse=True)
    merged = merged[:MAX_HISTORY_DRAWS]

    output = {
        "game": key,
        "updated_at": updated_at,
        "count": len(merged),
        "draws": merged,
    }

    HISTORY_FILES[key].write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
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

    updated_at = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )
    output = {
        "updated_at": updated_at,
        "games": games,
        "warnings": warnings,
    }
    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for key, game in games.items():
        update_history(key, game, updated_at)
        print(
            f"{key}歷史資料：{HISTORY_FILES[key]}｜"
            f"最多保留{MAX_HISTORY_DRAWS}期"
        )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
