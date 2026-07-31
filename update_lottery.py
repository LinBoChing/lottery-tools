#!/usr/bin/env python3

import json
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen


OUTPUT_FILE = Path("latest-draws.json")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/html,application/xhtml+xml,*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
        },
    )

    with urlopen(request, timeout=35) as response:
        status = getattr(response, "status", 200)

        if status != 200:
            raise RuntimeError(f"HTTP {status}: {url}")

        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"

        try:
            return raw.decode(charset, errors="ignore")
        except LookupError:
            return raw.decode("utf-8", errors="ignore")


def html_to_text(content: str) -> str:
    content = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        content,
        flags=re.I | re.S,
    )
    content = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        content,
        flags=re.I | re.S,
    )
    content = re.sub(r"<br\s*/?>", "\n", content, flags=re.I)
    content = re.sub(r"</(?:tr|td|th|li|div|p|section|article|h\d)>", "\n", content, flags=re.I)
    content = re.sub(r"<[^>]+>", " ", content)

    content = unescape(content)
    content = content.replace("\xa0", " ")
    content = content.replace("\u3000", " ")

    lines = []

    for line in content.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


def valid_numbers(numbers: list[int]) -> bool:
    return (
        len(numbers) == 5
        and len(set(numbers)) == 5
        and all(1 <= number <= 39 for number in numbers)
    )


def normalize_numbers(values) -> list[int]:
    numbers = []

    for value in values:
        match = re.search(r"\d{1,2}", str(value))

        if match:
            numbers.append(int(match.group(0)))

    return numbers


def normalize_date(value: str) -> str:
    value = unescape(str(value)).replace("\xa0", " ").strip()
    value = re.sub(r"\s+", " ", value)

    value = re.sub(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*",
        "",
        value,
        flags=re.I,
    )

    formats = (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    )

    clean_value = value.rstrip("Z")

    for date_format in formats:
        try:
            parsed = datetime.strptime(clean_value, date_format)
            return parsed.strftime("%Y/%m/%d")
        except ValueError:
            pass

    match = re.search(
        r"(20\d{2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{1,2})",
        value,
    )

    if match:
        year, month, day = map(int, match.groups())
        return f"{year:04d}/{month:02d}/{day:02d}"

    match = re.search(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})",
        value,
    )

    if match:
        month_name, day, year = match.groups()

        for date_format in ("%B %d %Y", "%b %d %Y"):
            try:
                parsed = datetime.strptime(
                    f"{month_name} {day} {year}",
                    date_format,
                )
                return parsed.strftime("%Y/%m/%d")
            except ValueError:
                pass

    raise ValueError(f"無法辨識日期：{value!r}")


def parse_api_draw(draw: dict) -> dict | None:
    winning_numbers = draw.get("WinningNumbers") or draw.get("winningNumbers") or []

    if not isinstance(winning_numbers, list):
        return None

    values = []

    for item in winning_numbers:
        if isinstance(item, dict):
            value = (
                item.get("Number")
                or item.get("number")
                or item.get("Value")
                or item.get("value")
            )
        else:
            value = item

        values.append(value)

    numbers = normalize_numbers(values)

    if not valid_numbers(numbers):
        return None

    date_value = (
        draw.get("DrawDate")
        or draw.get("drawDate")
        or draw.get("Date")
        or draw.get("date")
        or ""
    )

    date = normalize_date(str(date_value))

    issue = str(
        draw.get("DrawNumber")
        or draw.get("drawNumber")
        or draw.get("Issue")
        or draw.get("issue")
        or ""
    ).strip()

    return {
        "date": date,
        "issue": issue,
        "nums": sorted(numbers),
        "source": "California Lottery API",
    }


def fantasy5_from_official_api() -> dict:
    errors = []

    # 掃描可能的遊戲編號，但每一筆都必須通過：
    # 1. 恰好5個號碼
    # 2. 號碼1～39
    # 3. 有有效開獎日期
    #
    # 若API資料有遊戲名稱，也必須包含 Fantasy 5。
    for game_id in range(1, 31):
        url = (
            "https://www.calottery.com/api/DrawGameApi/"
            f"DrawGamePastDrawResults/{game_id}/1/5"
        )

        try:
            data = json.loads(fetch_text(url))

            game_name = str(
                data.get("GameName")
                or data.get("DrawGameName")
                or data.get("Name")
                or ""
            )

            draws = (
                data.get("PreviousDraws")
                or data.get("previousDraws")
                or data.get("Draws")
                or data.get("draws")
                or []
            )

            if not isinstance(draws, list) or not draws:
                continue

            candidates = []

            for draw in draws:
                if not isinstance(draw, dict):
                    continue

                parsed = parse_api_draw(draw)

                if parsed:
                    candidates.append(parsed)

            if not candidates:
                continue

            if game_name and "fantasy" not in game_name.lower():
                continue

            candidates.sort(
                key=lambda item: item["date"],
                reverse=True,
            )

            result = candidates[0]
            result["source"] = f"California Lottery API game {game_id}"

            return result

        except Exception as error:
            errors.append(f"game {game_id}: {error}")

    raise RuntimeError(
        "California Lottery API 無有效 Fantasy 5 資料；"
        + " | ".join(errors[-4:])
    )


def fantasy5_from_lotteryusa() -> dict:
    url = "https://www.lotteryusa.com/california/fantasy-5/"
    content = fetch_text(url)
    text = html_to_text(content)

    latest_position = text.lower().find("latest numbers")

    if latest_position < 0:
        raise RuntimeError("找不到 Latest numbers 區塊")

    section = text[latest_position : latest_position + 3500]

    date_match = re.search(
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
        r"([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
        section,
        flags=re.I,
    )

    if not date_match:
        raise RuntimeError("找不到 Fantasy 5 最新日期")

    date_text = date_match.group(0)
    after_date = section[date_match.end() :]

    stop_markers = (
        "Est. jackpot",
        "Estimated jackpot",
        "Jackpot",
        "Monday,",
        "Tuesday,",
        "Wednesday,",
        "Thursday,",
        "Friday,",
        "Saturday,",
        "Sunday,",
    )

    cut_positions = []

    for marker in stop_markers:
        position = after_date.find(marker)

        if position > 0:
            cut_positions.append(position)

    if cut_positions:
        after_date = after_date[: min(cut_positions)]

    number_tokens = re.findall(
        r"(?<!\d)(0?[1-9]|[12]\d|3[0-9])(?!\d)",
        after_date,
    )

    numbers = [int(value) for value in number_tokens[:5]]

    if not valid_numbers(numbers):
        raise RuntimeError(
            f"Fantasy 5 號碼解析失敗：{numbers}"
        )

    return {
        "date": normalize_date(date_text),
        "issue": "",
        "nums": sorted(numbers),
        "source": "LotteryUSA Fantasy 5",
    }


def fetch_fantasy5() -> dict:
    errors = []

    for fetcher in (
        fantasy5_from_official_api,
        fantasy5_from_lotteryusa,
    ):
        try:
            result = fetcher()

            if not result.get("date"):
                raise RuntimeError("日期空白")

            if not valid_numbers(result.get("nums", [])):
                raise RuntimeError("號碼驗證失敗")

            return result

        except Exception as error:
            errors.append(f"{fetcher.__name__}: {error}")

    raise RuntimeError("；".join(errors))


def lotto539_from_pilio() -> dict:
    url = "https://www.pilio.idv.tw/lto539/drawlist/drawlist.asp"
    content = fetch_text(url)
    text = html_to_text(content)

    position = text.find("日期")

    if position >= 0:
        text = text[position:]

    # 頁面格式：
    # 2026
    # 07/30
    # (四) | 04, 07, 08, 16, 38
    pattern = re.compile(
        r"(?P<year>20\d{2})\s*[\r\n ]+"
        r"(?P<month>\d{1,2})\s*/\s*(?P<day>\d{1,2})"
        r".{0,80}?"
        r"(?P<n1>0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
        r"(?P<n2>0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
        r"(?P<n3>0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
        r"(?P<n4>0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
        r"(?P<n5>0?[1-9]|[12]\d|3[0-9])",
        flags=re.S,
    )

    match = pattern.search(text)

    if not match:
        # 備援：日期在同一行，例如 2026/07/30
        pattern_same_line = re.compile(
            r"(?P<year>20\d{2})\s*/\s*"
            r"(?P<month>\d{1,2})\s*/\s*"
            r"(?P<day>\d{1,2})"
            r".{0,120}?"
            r"(?P<n1>0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
            r"(?P<n2>0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
            r"(?P<n3>0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
            r"(?P<n4>0?[1-9]|[12]\d|3[0-9])\s*[,，]\s*"
            r"(?P<n5>0?[1-9]|[12]\d|3[0-9])",
            flags=re.S,
        )

        match = pattern_same_line.search(text)

    if not match:
        raise RuntimeError("找不到今彩539最新資料列")

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))

    numbers = [
        int(match.group("n1")),
        int(match.group("n2")),
        int(match.group("n3")),
        int(match.group("n4")),
        int(match.group("n5")),
    ]

    if not valid_numbers(numbers):
        raise RuntimeError(f"今彩539號碼驗證失敗：{numbers}")

    return {
        "date": f"{year:04d}/{month:02d}/{day:02d}",
        "issue": "",
        "nums": sorted(numbers),
        "source": url,
    }


def fetch_lotto539() -> dict:
    result = lotto539_from_pilio()

    if not result.get("date"):
        raise RuntimeError("今彩539日期空白")

    if not valid_numbers(result.get("nums", [])):
        raise RuntimeError("今彩539號碼驗證失敗")

    return result


def load_old_data() -> dict:
    if not OUTPUT_FILE.exists():
        return {}

    try:
        return json.loads(
            OUTPUT_FILE.read_text(encoding="utf-8")
        )
    except Exception as error:
        print(f"讀取舊 JSON 失敗：{error}")
        return {}


def game_is_valid(game: dict) -> bool:
    if not isinstance(game, dict):
        return False

    date = str(game.get("date", "")).strip()
    numbers = game.get("nums", [])

    return bool(date) and valid_numbers(numbers)


def main() -> None:
    old_data = load_old_data()
    old_games = old_data.get("games", {})

    games = {}
    warnings = []

    fetchers = {
        "539": fetch_lotto539,
        "dayday": fetch_fantasy5,
    }

    for game_key, fetcher in fetchers.items():
        try:
            result = fetcher()

            if not game_is_valid(result):
                raise RuntimeError("抓取結果未通過最終驗證")

            games[game_key] = result

            print(
                f"{game_key} 成功："
                f"{result['date']} | "
                f"{' '.join(f'{n:02d}' for n in result['nums'])} | "
                f"{result['source']}"
            )

        except Exception as error:
            warning = f"{game_key}: {error}"
            warnings.append(warning)
            print(f"警告：{warning}")

            old_game = old_games.get(game_key)

            if game_is_valid(old_game):
                games[game_key] = old_game
                print(f"{game_key} 使用舊資料保留")
            else:
                print(f"{game_key} 沒有可用的舊資料")

    missing_games = [
        key
        for key in ("539", "dayday")
        if key not in games
    ]

    if missing_games:
        raise SystemExit(
            "以下彩種抓取失敗且沒有舊資料："
            + ", ".join(missing_games)
        )

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "games": games,
        "warnings": warnings,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print("\n完成寫入 latest-draws.json")
    print(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
