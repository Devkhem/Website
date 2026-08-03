#!/usr/bin/env python3
"""Create a daily story-channel plan from one AI image into three TikTok clips."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a 1-image -> 3-clips TikTok story plan.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Plan date in YYYY-MM-DD format.")
    parser.add_argument("--series-id", default="", help="Story series id, e.g. room-407.")
    parser.add_argument("--story", default=str(ROOT / "data" / "story_series.json"), help="Story config JSON.")
    parser.add_argument("--account", default=str(ROOT / "data" / "tiktok_account.json"), help="TikTok account JSON.")
    parser.add_argument("--metrics", default=str(ROOT / "data" / "story_metrics.csv"), help="Story metrics CSV.")
    parser.add_argument("--out", default=str(ROOT / "outputs"), help="Output directory.")
    parser.add_argument("--hook", default="", help="hook ใหม่สำหรับรอบที่ retention สั่งให้เปลี่ยน hook.")
    return parser.parse_args()


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_series_rows(path: Path, series_id: str) -> list:
    """Every row for this series, whatever horizon — this is the posting history."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get("series_id") == series_id]


def read_latest_metrics(path: Path, series_id: str) -> list:
    """Rows for this series that carry a retention number.

    The rules are written in terms of two-hour retention, so prefer rows measured at
    two hours; older files without the column fall back to every row.
    """
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    kept = []
    for row in rows:
        if row.get("series_id") != series_id or not str(row.get("retention_percent") or "").strip():
            continue
        value = parse_float(row.get("retention_percent"), None)
        if value is None or not math.isfinite(value) or not 0 <= value <= 100:
            print(f"[warn] ข้าม metrics แถวที่ retention_percent ใช้ไม่ได้ (ต้องเป็น 0-100): {row.get('retention_percent')!r}")
            continue
        kept.append(row)
    rows = kept
    two_hour = [row for row in rows if str(row.get("measured_after_hours") or "").strip() == "2"]
    if two_hour:
        return two_hour
    if rows and any("measured_after_hours" in row for row in rows):
        # The column exists, so a missing 2h row is missing data — not a reason to
        # judge 24h numbers against thresholds named for two hours.
        print("[warn] ยังไม่มีแถวที่วัดตอน 2 ชั่วโมง จึงยังไม่ตัดสินใจจาก retention รอบนี้")
        return []
    return rows


def select_series(config: dict, requested_id: str) -> dict:
    series = config.get("series", [])
    if requested_id:
        for item in series:
            if item.get("id") == requested_id:
                return item
        raise SystemExit(f"Series id not found: {requested_id}")
    return series[0] if series else {}


def retention_thresholds(config: dict) -> tuple:
    """kill <= rewrite <= strong, all real percentages, or the run stops."""
    rules = config.get("retention_rules", {})
    strong = parse_float(rules.get("strong_continue", {}).get("two_hour_retention_percent"), 35)
    rewrite = parse_float(rules.get("rewrite_hook", {}).get("two_hour_retention_percent"), 25)
    kill = parse_float(rules.get("kill_premise", {}).get("two_hour_retention_percent"), 20)
    for name, value in (("kill_premise", kill), ("rewrite_hook", rewrite), ("strong_continue", strong)):
        if value is None or not math.isfinite(value) or not 0 <= value <= 100:
            raise SystemExit(f"retention_rules.{name} ต้องเป็นตัวเลข 0-100 แต่ได้: {value}")
    if not kill <= rewrite <= strong:
        raise SystemExit(
            f"retention_rules ต้องเรียง kill <= rewrite <= strong แต่ได้ {kill:g} / {rewrite:g} / {strong:g}"
        )
    return kill, rewrite, strong


def decision_from_metrics(config: dict, metrics: list) -> tuple:
    """Return (key, ข้อความอธิบาย) so the plan and the packages agree."""
    if not metrics:
        return "no_data", "ยังไม่มี retention ให้เตรียม 3 ตอน แต่โพสต์ตอนแรกก่อน แล้ววัด retention ที่ 2 ชั่วโมง"
    latest = metrics[-1]
    retention = parse_float(latest.get("retention_percent"))
    kill, rewrite, strong = retention_thresholds(config)
    if retention >= strong:
        return "continue", "Retention แข็งแรง: ทำตอนต่อจาก premise เดิมทันที"
    if retention >= rewrite:
        return "rewrite_hook", "Retention กลาง: ใช้ภาพเดิมได้ แต่ต้องเปลี่ยน hook 3 วินาทีแรก"
    if retention < kill:
        return "kill", "Retention ต่ำ: หยุด premise นี้และเปลี่ยน location/premise"
    return "test_more", "Retention ยังพอทดสอบได้: ทำอีก 1 variation ก่อนตัดสินใจ"


def posted_episodes(metrics: list) -> set:
    numbers = set()
    for row in metrics:
        try:
            numbers.add(int(str(row.get("episode") or "").strip()))
        except ValueError:
            continue
    return numbers


def latest_episode_number(metrics: list) -> int:
    """The episode behind the retention row the decision was made from."""
    for row in reversed(metrics):
        try:
            return int(str(row.get("episode") or "").strip())
        except ValueError:
            continue
    return 0


def select_episodes(series: dict, decision_key: str, posted: set, target_episode: int = 0) -> list:
    """Turn the retention decision into the episodes this run should package."""
    episodes = series.get("episodes", [])
    if decision_key == "kill":
        return []
    if decision_key == "rewrite_hook":
        # One variation of the episode the decision was actually about.
        exact = [item for item in episodes if int(item.get("episode", 0)) == target_episode]
        if exact:
            return exact[:1]
        redo = [item for item in episodes if int(item.get("episode", 0)) in posted]
        return (redo or episodes)[:1]
    fresh = [item for item in episodes if int(item.get("episode", 0)) not in posted]
    if not fresh:
        # Everything configured has been posted; repeating it would queue old content.
        return []
    if decision_key == "test_more":
        # The decision literally says "one more variation before deciding".
        return fresh[:1]
    return fresh[:3]


def parse_float(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_image_prompt(series: dict) -> str:
    seed = series.get("image_prompt_seed", "")
    return "\n".join(
        [
            "สร้างภาพแนวตั้ง 9:16 แบบภาพถ่ายมือถือจริง ไม่ใช่โปสเตอร์หนัง",
            seed,
            "ให้มีพื้นที่มืดหรือ negative space สำหรับใส่ subtitle ด้านบนหรือด้านล่าง",
            "ความน่ากลัวต้องมาจากรายละเอียดเล็ก ๆ ที่คนต้องมองซ้ำ",
            "ห้ามมีตัวหนังสือ ห้ามมี watermark ห้ามมี logo",
            "ห้ามให้เห็นผีชัด ๆ ห้ามหน้าผีใหญ่ ห้ามเลือด ห้าม gore",
        ]
    )


def episode_package(series: dict, episode: dict, posting_time: str, decision_key: str = "no_data", new_hook: str = "") -> dict:
    title = episode.get("title", "")
    hook = episode.get("hook", "")
    if decision_key == "rewrite_hook" and new_hook:
        hook = new_hook
    twist = episode.get("twist", "")
    series_title = series.get("title", "")
    caption = f"{hook} ฟังให้จบแล้วบอกทีว่าคุณจะเปิดไหม"
    hashtags = "#เรื่องผี #เล่าเรื่องผี #เรื่องหลอนก่อนนอน #TikTokThailand #หลอน"
    script = "\n".join(
        [
            f"0-2s: {hook}",
            f"2-8s: เล่าว่าสถานที่คือ {series.get('location', 'สถานที่เกิดเรื่อง')} และมีบางอย่างผิดปกติ",
            f"8-18s: เพิ่มหลักฐานจาก {series.get('fear_mechanic', 'สิ่งที่อธิบายไม่ได้')}",
            f"18-28s: เผย twist: {twist}",
            "28-32s: ปิดด้วยคำถามให้คอมเมนต์",
        ]
    )
    edit_notes = "\n".join(
        (["ต้องเขียน hook 3 วินาทีแรกใหม่ ห้ามใช้ hook เดิมซ้ำ"] if decision_key == "rewrite_hook" else [])
        + [
            "ใช้ภาพแม่ภาพเดียว",
            "เริ่มด้วย crop ใกล้จุดผิดปกติ แล้วค่อย zoom out",
            "ใส่ subtitle สั้น ไม่เกิน 2 บรรทัดต่อ beat",
            "ใช้เสียง low drone + knock หรือ phone vibration",
            "จบด้วย frame ค้าง 0.8 วินาทีให้คนอ่านทัน",
        ]
    )
    return {
        "series_id": series.get("id", ""),
        "series_title": series_title,
        "episode": str(episode.get("episode", "")),
        "clip_id": f"{series.get('id', 'story')}-ep{episode.get('episode', '')}",
        "title": title,
        "hook": hook,
        "twist": twist,
        "posting_time": posting_time,
        "caption": caption,
        "hashtags": hashtags,
        "script": script,
        "edit_notes": edit_notes,
    }


def retention_rule_lines(config: dict) -> list:
    """Rules straight from the config that made the decision, not a copy of it."""
    kill, rewrite, strong = retention_thresholds(config)
    return [
        f"- retention (วัดที่ 2 ชั่วโมง) ต่ำกว่า {kill:g}% ให้หยุด premise",
        f"- {rewrite:g}% ถึงต่ำกว่า {strong:g}% ให้ใช้ภาพเดิมแต่เปลี่ยน hook",
        f"- {strong:g}% ขึ้นไป ให้ทำตอนต่อทันที",
        f"- ระหว่าง {kill:g}% ถึงต่ำกว่า {rewrite:g}% ให้ทำอีก 1 variation ก่อนตัดสินใจ",
    ]


def render_markdown(account: dict, config: dict, series: dict, packages: list, decision: str, plan_date: str, decision_exhausted: bool = False, needs_hook: bool = False, decision_key: str = "", wants_new_image: bool = True) -> str:
    handle = account.get("handle", "@thatslife6969")
    lines = [
        f"# Story Channel Plan: {plan_date}",
        "",
        f"TikTok account: {handle}",
        f"Workflow: {config.get('primary_format', 'ChatGPT image -> Codex 3 clips')}",
        f"Series: {series.get('title', '')} (`{series.get('id', '')}`)",
        f"Decision: {decision}",
        "",
        "## ChatGPT Image Prompt",
        "",
        "```text",
        build_image_prompt(series)
        if wants_new_image
        else (
            "(ใช้ภาพแม่เดิม รอบนี้เปลี่ยนแค่ hook ไม่ต้องสร้างภาพใหม่)"
            if decision_key == "rewrite_hook"
            else "(ไม่ออก prompt ภาพ เพราะรอบนี้ยังไม่ทำ premise นี้ต่อ)"
        ),
        "```",
        "",
        "## Production Rule",
        "",
        "- ใช้ภาพนี้ภาพเดียวให้ครบ 3 คลิปก่อนสร้างภาพใหม่",
    ]
    lines.extend(retention_rule_lines(config))
    lines.append("")
    if not packages:
        if needs_hook:
            reason = (
                "retention บอกให้เปลี่ยน hook แต่ยังไม่ได้ระบุ hook ใหม่\n"
                "เขียน hook ใหม่แล้วรันซ้ำ เช่น --hook \"ประโยคเปิดใหม่ 3 วินาทีแรก\""
            )
        elif decision_exhausted:
            reason = "ตอนทั้งหมดใน series นี้ถูกโพสต์ไปหมดแล้ว ต้องเขียน episode ใหม่ก่อน"
        else:
            reason = "retention ต่ำกว่าเกณฑ์ kill จึงไม่ออก episode package ให้รอบนี้"
        lines.extend(
            [
                "## ยังไม่ออก package รอบนี้",
                "",
                reason,
                "ให้เลือก series อื่นด้วย --series-id หรือเพิ่ม episode ใหม่ใน data/story_series.json",
                "",
            ]
        )
    for package in packages:
        lines.extend(
            [
                f"## Episode {package['episode']}: {package['title']}",
                "",
                f"Clip ID: `{package['clip_id']}`",
                f"Posting time: {package['posting_time']}",
                "",
                "### Hook",
                "",
                package["hook"],
                "",
                "### Script",
                "",
                package["script"],
                "",
                "### Edit Notes",
                "",
                package["edit_notes"],
                "",
                "### Caption",
                "",
                package["caption"],
                "",
                "### Hashtags",
                "",
                package["hashtags"],
                "",
            ]
        )
    if len(packages) > 1:
        lines.extend(
            [
                "## ลำดับการโพสต์",
                "",
                "โพสต์เฉพาะตอนที่ `post_status` เป็น `post_now` ก่อน แล้ววัด retention ที่ 2 ชั่วโมง",
                "ตอนที่เหลือเตรียมไว้ก่อน อย่าเพิ่งโพสต์จนกว่าจะรู้ผล",
                "",
            ]
        )
    lines.extend(
        [
            "## After Posting",
            "",
            "กรอกผลใน `data/story_metrics.csv` หลังโพสต์ 2 ชั่วโมงและ 24 ชั่วโมง:",
            "",
            "- views",
            "- avg_watch_time_seconds",
            "- retention_percent",
            "- comments",
            "- shares",
            "- saves",
            "- next_action",
            "",
        ]
    )
    return "\n".join(lines)


def write_queue(path: Path, packages: list[dict[str, str]]) -> None:
    fields = ["series_id", "episode", "clip_id", "title", "hook", "posting_time", "post_status", "caption", "hashtags"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, package in enumerate(packages):
            row = {field: package.get(field, "") for field in fields}
            # The ops gate is: post one, wait two hours, read retention, then decide.
            row["post_status"] = "post_now" if index == 0 else "hold_until_retention"
            writer.writerow(row)


def write_episode_packages(output_dir: Path, packages: list) -> None:
    # A rerun can select different episodes, so clear the previous ones first;
    # otherwise a killed premise leaves packages that still look actionable.
    for stale in sorted(output_dir.glob("episode-*-package.md")):
        stale.unlink()
    for package in packages:
        path = output_dir / f"episode-{int(package['episode']):02d}-package.md"
        path.write_text(render_episode_package(package), encoding="utf-8")


def render_episode_package(package: dict[str, str]) -> str:
    return "\n".join(
        [
            f"# {package['clip_id']}",
            "",
            f"Title: {package['title']}",
            f"Posting time: {package['posting_time']}",
            "",
            "## Hook",
            "",
            package["hook"],
            "",
            "## Script",
            "",
            package["script"],
            "",
            "## Edit Notes",
            "",
            package["edit_notes"],
            "",
            "## Caption",
            "",
            package["caption"],
            "",
            "## Hashtags",
            "",
            package["hashtags"],
            "",
        ]
    )


def validate_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        raise SystemExit(f"--date ต้องเป็นรูปแบบ YYYY-MM-DD เท่านั้น แต่ได้: {value}")
    return value


def main() -> None:
    args = parse_args()
    args.date = validate_date(args.date)
    config = read_json(Path(args.story))
    retention_thresholds(config)
    account = read_json(Path(args.account))
    series = select_series(config, args.series_id)
    metrics = read_latest_metrics(Path(args.metrics), series.get("id", ""))
    history = read_series_rows(Path(args.metrics), series.get("id", ""))
    decision_key, decision = decision_from_metrics(config, metrics)
    posting_windows = config.get("posting_windows") or ["12:00", "18:30", "22:30"]
    posted = posted_episodes(history)
    exhausted = decision_key != "kill" and not [
        item for item in series.get("episodes", []) if int(item.get("episode", 0)) not in posted
    ]
    episodes = select_episodes(series, decision_key, posted, latest_episode_number(metrics))
    needs_hook = decision_key == "rewrite_hook" and not args.hook.strip()
    if needs_hook:
        # Emitting the old hook again would repeat the test we just failed.
        episodes = []
    packages = [
        episode_package(series, episode, posting_windows[index % len(posting_windows)], decision_key, args.hook.strip())
        for index, episode in enumerate(episodes)
    ]
    # An image with no package to make would spend the daily budget for nothing.
    wants_new_image = bool(packages) and decision_key not in {"kill", "rewrite_hook"}

    output_dir = Path(args.out) / args.date
    output_dir.mkdir(parents=True, exist_ok=True)
    image_prompt_path = output_dir / "chatgpt-image-prompt.txt"
    if wants_new_image:
        image_prompt_path.write_text(build_image_prompt(series), encoding="utf-8")
    elif image_prompt_path.exists():
        # Following it would spend the daily image on a premise we stopped, or on a
        # round that is meant to change only the hook.
        image_prompt_path.unlink()
    (output_dir / "story-channel-plan.md").write_text(
        render_markdown(
            account, config, series, packages, decision, args.date, exhausted, needs_hook,
            decision_key, wants_new_image,
        ),
        encoding="utf-8",
    )
    write_queue(output_dir / "story_posting_queue.csv", packages)
    write_episode_packages(output_dir, packages)

    if wants_new_image:
        print(f"Created {image_prompt_path}")
    elif decision_key == "rewrite_hook":
        print("ใช้ภาพแม่เดิม ไม่ออก prompt ภาพใหม่ เพราะรอบนี้เปลี่ยนแค่ hook")
    print(f"Created {output_dir / 'story-channel-plan.md'}")
    print(f"Created {output_dir / 'story_posting_queue.csv'}")
    print(f"Decision: {decision}")
    if needs_hook:
        print("ไม่ได้สร้าง episode package เพราะยังไม่ได้ระบุ hook ใหม่ ให้รันซ้ำพร้อม --hook")
    elif not packages and exhausted:
        print("ไม่ได้สร้าง episode package เพราะตอนทั้งหมดใน series นี้ถูกโพสต์ไปหมดแล้ว")
    elif not packages:
        print("ไม่ได้สร้าง episode package เพราะ retention ต่ำกว่าเกณฑ์ kill")
    elif posted:
        print(f"ตอนที่โพสต์ไปแล้ว: {', '.join(str(number) for number in sorted(posted))}")


if __name__ == "__main__":
    main()
