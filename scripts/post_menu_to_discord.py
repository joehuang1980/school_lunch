#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup


TAIPEI_TZ = dt.timezone(dt.timedelta(hours=8))
DEFAULT_SOURCE_URL = "https://www.fhes.tn.edu.tw/"
WEEKDAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


@dataclass
class LunchMenu:
    date: dt.date
    school_name: str
    note: str
    dishes: list  # [(category, name), ...]


def get_env(name, default=None):
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def now_taipei():
    return dt.datetime.now(TAIPEI_TZ)


def now_taipei_str():
    return now_taipei().strftime("%Y-%m-%d %H:%M:%S %z")


def next_school_day(today):
    candidate = today + dt.timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += dt.timedelta(days=1)
    return candidate


def fetch_lunch_menu(session, source_url, date):
    resp = session.get(source_url, params={"period": date.isoformat()}, timeout=30)
    resp.raise_for_status()
    return parse_lunch_menu(resp.text, date)


def parse_lunch_menu(html, date):
    soup = BeautifulSoup(html, "html.parser")

    heading = soup.find("h3", string=lambda t: t and "今日午餐" in t)
    if not heading:
        return None
    block = heading.find_parent("div", class_="centerBottomBlock")
    if not block:
        return None

    content = block.find("div", class_="blockContent")
    if not content:
        return None

    title_tag = content.find("h3")
    school_name = title_tag.get_text(strip=True) if title_tag else ""

    note_tag = content.find("code")
    note = note_tag.get_text(strip=True) if note_tag else ""

    dishes = []
    for a_tag in content.find_all("a", {"data-caption": True}):
        caption = a_tag["data-caption"].strip()
        if "(" in caption and caption.endswith(")"):
            name, rest = caption.rsplit("(", 1)
            category = rest.rstrip(")")
        else:
            name, category = caption, ""
        dishes.append((category.strip(), name.strip()))

    if not dishes:
        return None

    return LunchMenu(date=date, school_name=school_name, note=note, dishes=dishes)


def format_menu_message(menu):
    weekday = WEEKDAY_NAMES[menu.date.weekday()]
    lines = [
        f"🍱 **{menu.date.isoformat()}（{weekday}）午餐菜單**",
        f"*{menu.school_name}*",
    ]
    if menu.note:
        lines.append(f"> {menu.note}")
    lines.append("")
    for category, name in menu.dishes:
        lines.append(f"**{category}**　{name}")
    return "\n".join(lines)


def send_message(webhook_url, content):
    resp = requests.post(webhook_url, json={"content": content}, timeout=30)
    resp.raise_for_status()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and print the menu without posting to Discord.")
    parser.add_argument("--state-file", default=".state/posted_dates.json",
                        help="Path to state file for tracking already-posted dates.")
    parser.add_argument("--date", default=None,
                        help="Override target date (YYYY-MM-DD). Defaults to next school day.")
    return parser.parse_args()


def load_posted_dates(state_file):
    if not state_file.exists():
        return set()
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    dates = payload.get("posted_dates", [])
    if not isinstance(dates, list):
        return set()
    return set(dates)


def save_posted_dates(state_file, posted_dates):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": now_taipei_str(),
        "posted_dates": sorted(posted_dates),
    }
    state_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    args = parse_args()
    state_file = Path(args.state_file)

    if args.date:
        target_date = dt.date.fromisoformat(args.date)
    else:
        target_date = next_school_day(now_taipei().date())

    webhook_url = ""
    if not args.dry_run:
        webhook_url = get_env("DISCORD_WEBHOOK_URL")

    source_url = os.getenv("SOURCE_URL") or DEFAULT_SOURCE_URL
    posted_dates = load_posted_dates(state_file)
    date_key = target_date.isoformat()

    if date_key in posted_dates:
        print(f"Menu for {date_key} already posted. Skipping.")
        return

    session = requests.Session()
    session.headers.update({"User-Agent": "school-lunch-bot/1.0"})

    menu = fetch_lunch_menu(session, source_url, target_date)

    if menu is None:
        msg = f"[school_lunch] 找不到 {date_key} 的午餐資訊（可能尚未公布）。"
        if args.dry_run:
            print(msg)
        else:
            send_message(webhook_url, msg)
        return

    message = format_menu_message(menu)

    if args.dry_run:
        print(message)
        return

    send_message(webhook_url, message)
    posted_dates.add(date_key)
    save_posted_dates(state_file, posted_dates)


if __name__ == "__main__":
    main()
