#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup


DEFAULT_SOURCE_URL = (
    "https://sites.google.com/fhes.tn.edu.tw/fhes002/%E5%8D%88%E9%A4%90%E5%BB%9A%E6%88%BF"
)
DRIVE_FILE_RE = re.compile(r"https://drive\.google\.com/file/d/([A-Za-z0-9_-]+)/")


@dataclass
class DriveFile:
    file_id: str
    title: str
    view_url: str


def get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def now_taipei_str() -> str:
    # Fixed offset avoids extra tz dependency in Actions runners.
    tz = dt.timezone(dt.timedelta(hours=8))
    return dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %z")


def extract_drive_files(html: str, keyword_list: Iterable[str]) -> list[DriveFile]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, DriveFile] = {}

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        match = DRIVE_FILE_RE.search(href)
        if not match:
            continue

        file_id = match.group(1)
        title = " ".join(a_tag.get_text(" ", strip=True).split())
        if not title:
            title = f"Google Drive file {file_id}"

        found[file_id] = DriveFile(file_id=file_id, title=title, view_url=href)

    files = list(found.values())
    if not files:
        return files

    lowered_keywords = [k.strip().lower() for k in keyword_list if k.strip()]
    if not lowered_keywords:
        return files

    filtered = [
        file
        for file in files
        if any(k in file.title.lower() for k in lowered_keywords)
    ]
    return filtered or files


def guess_filename_from_response(resp: requests.Response, default_name: str) -> str:
    content_disp = resp.headers.get("content-disposition", "")
    quoted_name = re.search(r'filename="([^"]+)"', content_disp)
    if quoted_name:
        return normalize_filename(quoted_name.group(1))

    plain_name = re.search(r"filename=([^;]+)", content_disp)
    if plain_name:
        return normalize_filename(plain_name.group(1).strip().strip('"'))

    return default_name


def normalize_filename(name: str) -> str:
    # Google Drive may return UTF-8 bytes interpreted as latin1 by clients.
    try:
        repaired = name.encode("latin1").decode("utf-8")
        if repaired:
            return repaired
    except UnicodeError:
        pass
    return name


def download_drive_file(session: requests.Session, file: DriveFile, target_dir: Path) -> Path:
    download_url = f"https://drive.google.com/uc?export=download&id={file.file_id}"
    resp = session.get(download_url, timeout=60, allow_redirects=True, stream=True)
    resp.raise_for_status()

    filename = guess_filename_from_response(resp, f"{file.file_id}.bin")
    safe_name = filename.replace("/", "_")
    output_path = target_dir / safe_name

    with output_path.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 128):
            if chunk:
                f.write(chunk)

    return output_path


def send_message(webhook_url: str, content: str) -> None:
    resp = requests.post(webhook_url, json={"content": content}, timeout=30)
    resp.raise_for_status()


def send_file(webhook_url: str, file_path: Path, caption: str) -> None:
    with file_path.open("rb") as f:
        resp = requests.post(
            webhook_url,
            data={"content": caption},
            files={"file": (file_path.name, f)},
            timeout=120,
        )
    resp.raise_for_status()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only test extraction and download; do not post to Discord.",
    )
    parser.add_argument(
        "--state-file",
        default=".state/posted_files.json",
        help="Path to state file for tracking already posted Drive file IDs.",
    )
    return parser.parse_args()


def load_posted_ids(state_file: Path) -> set[str]:
    if not state_file.exists():
        return set()

    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    ids = payload.get("posted_file_ids", [])
    if not isinstance(ids, list):
        return set()
    return {str(item) for item in ids}


def save_posted_ids(state_file: Path, posted_ids: set[str]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": now_taipei_str(),
        "posted_file_ids": sorted(posted_ids),
    }
    state_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    state_file = Path(args.state_file)
    source_url = os.getenv("SOURCE_URL") or DEFAULT_SOURCE_URL
    webhook_url = ""
    if not args.dry_run:
        webhook_url = get_env("DISCORD_WEBHOOK_URL")
    keywords = (os.getenv("MENU_KEYWORDS") or "午餐,菜單,用餐").split(",")

    session = requests.Session()
    session.headers.update({"User-Agent": "school-lunch-bot/1.0"})

    page_resp = session.get(source_url, timeout=60)
    page_resp.raise_for_status()

    drive_files = extract_drive_files(page_resp.text, keywords)
    posted_ids = load_posted_ids(state_file)
    new_files = [item for item in drive_files if item.file_id not in posted_ids]

    if not drive_files:
        if args.dry_run:
            print("No downloadable menu files found.")
            return

        send_message(
            webhook_url,
            (
                "[school_lunch] 未找到可下載菜單檔案。\n"
                f"來源：{source_url}\n"
                f"時間：{now_taipei_str()}"
            ),
        )
        return

    if not new_files:
        msg = (
            "No new files to post.\n"
            f"Total found this run: {len(drive_files)}\n"
            f"Already posted: {len(posted_ids)}"
        )
        if args.dry_run:
            print(msg)
        else:
            send_message(
                webhook_url,
                (
                    "[school_lunch] 本週沒有新檔案，已略過重複發送。\n"
                    f"來源：{source_url}\n"
                    f"時間：{now_taipei_str()}"
                ),
            )
        return

    if args.dry_run:
        print(f"Found {len(drive_files)} file(s), new {len(new_files)} file(s):")
        for item in new_files:
            print(f"- {item.title} ({item.view_url})")
    else:
        send_message(
            webhook_url,
            (
                f"[school_lunch] 本週菜單更新（新增 {len(new_files)} 份）\n"
                f"來源：{source_url}\n"
                f"時間：{now_taipei_str()}"
            ),
        )

    with tempfile.TemporaryDirectory(prefix="school_lunch_") as tmp:
        tmp_dir = Path(tmp)
        for drive_file in new_files:
            downloaded = download_drive_file(session, drive_file, tmp_dir)
            if args.dry_run:
                print(f"Downloaded: {downloaded}")
                continue

            send_file(
                webhook_url,
                downloaded,
                f"{drive_file.title}\n{drive_file.view_url}",
            )
            posted_ids.add(drive_file.file_id)

    if not args.dry_run:
        save_posted_ids(state_file, posted_ids)


if __name__ == "__main__":
    main()