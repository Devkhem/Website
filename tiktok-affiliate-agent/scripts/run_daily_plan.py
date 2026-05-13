#!/usr/bin/env python3
"""Generate a daily TikTok affiliate content plan without external deps."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Product:
    name: str
    category: str
    price: float
    commission_percent: float
    rating: float
    reviews: int
    main_benefit: str
    pain_point: str
    tiktok_angle: str
    stock_status: str
    affiliate_link: str

    @property
    def estimated_commission_thb(self) -> float:
        return self.price * self.commission_percent / 100


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a daily TikTok affiliate content plan.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Plan date in YYYY-MM-DD format.")
    parser.add_argument("--goal", default="", help="Daily content goal.")
    parser.add_argument("--products", default=str(ROOT / "data" / "products.csv"), help="Product CSV path.")
    parser.add_argument("--brand", default=str(ROOT / "data" / "brand_profile.json"), help="Brand profile JSON path.")
    parser.add_argument("--account", default=str(ROOT / "data" / "tiktok_account.json"), help="TikTok account JSON path.")
    parser.add_argument(
        "--revenue-targets",
        default=str(ROOT / "data" / "revenue_targets.json"),
        help="Revenue target JSON path.",
    )
    parser.add_argument("--out", default=str(ROOT / "outputs"), help="Output directory.")
    parser.add_argument("--count", type=int, default=0, help="Number of content ideas to produce.")
    return parser.parse_args()


def read_brand(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_products(path: Path) -> list[Product]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [to_product(row) for row in reader]


def to_product(row: dict[str, str]) -> Product:
    return Product(
        name=row.get("product_name", "").strip(),
        category=row.get("category", "").strip(),
        price=parse_float(row.get("price")),
        commission_percent=parse_float(row.get("commission_percent")),
        rating=parse_float(row.get("rating")),
        reviews=int(parse_float(row.get("reviews"))),
        main_benefit=row.get("main_benefit", "").strip(),
        pain_point=row.get("pain_point", "").strip(),
        tiktok_angle=row.get("tiktok_angle", "").strip(),
        stock_status=row.get("stock_status", "").strip(),
        affiliate_link=row.get("affiliate_link", "").strip(),
    )


def parse_float(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return 0.0


def score_product(product: Product) -> float:
    price_score = 18 if 49 <= product.price <= 399 else 10 if product.price <= 799 else 5
    review_score = min(product.reviews, 8000) / 8000 * 20
    rating_score = max(product.rating - 3.5, 0) * 16
    commission_score = min(product.commission_percent, 20) * 1.8
    commission_value_score = min(product.estimated_commission_thb, 120) / 120 * 35
    clarity_score = 15 if product.pain_point and product.main_benefit else 5
    stock_score = 10 if product.stock_status.lower() in {"in_stock", "available", "พร้อมขาย"} else -30
    return round(
        price_score + review_score + rating_score + commission_score + commission_value_score + clarity_score + stock_score,
        2,
    )


def rank_products(products: Iterable[Product]) -> list[tuple[Product, float]]:
    available = [product for product in products if product.name]
    ranked = sorted(((product, score_product(product)) for product in available), key=lambda item: item[1], reverse=True)
    return ranked


def hook_for(product: Product) -> str:
    templates = [
        f"ถ้า{product.pain_point} ลองดูชิ้นนี้ก่อนซื้อ",
        f"ของชิ้นนี้ช่วยเรื่อง{product.main_benefit}ได้แบบใช้ง่ายมาก",
        f"ลองของราคา {format_price(product.price)} ที่หลายคนซื้อซ้ำ",
    ]
    return templates[0] if product.pain_point else templates[1]


def format_price(price: float) -> str:
    return f"{price:,.0f} บาท" if price else "ราคานี้"


def make_plan_item(product: Product, score: float, index: int, posting_time: str) -> dict[str, str]:
    hook = hook_for(product)
    estimated_commission = product.estimated_commission_thb
    product_role = classify_product(estimated_commission)
    caption = f"{product.pain_point} ใครเจอบ่อย ลองดูตัวนี้ไว้เป็นตัวเลือกนะ กดดูสินค้าในตะกร้าได้เลย"
    hashtags = f"#TikTokShop #ป้ายยาของดี #{product.category.replace(' ', '')} #รีวิวของใช้ #ของมันต้องมี"
    voiceover = (
        f"{hook}\n"
        f"ตัวนี้คือ {product.name} จุดที่น่าสนใจคือ {product.main_benefit}. "
        f"เหมาะกับคนที่เจอปัญหา {product.pain_point}. "
        f"ในคลิปนี้ลองให้ดูแบบสั้น ๆ ว่าใช้งานจริงเป็นยังไง "
        f"ถ้าคิดว่าเหมาะกับคุณ กดดูรายละเอียดในตะกร้าได้เลย."
    )
    shot_list = "\n".join(
        [
            "1. 0-2s: เปิดด้วยภาพปัญหาจริง + text hook",
            f"2. 2-6s: โชว์สินค้า {product.name} แบบ close-up",
            f"3. 6-12s: สาธิตการใช้เพื่อแก้ปัญหา {product.pain_point}",
            f"4. 12-20s: โชว์ผลลัพธ์หรือความสะดวกจาก {product.main_benefit}",
            "5. 20-28s: สรุปใครเหมาะกับสินค้านี้",
            "6. 28-35s: ปิดด้วย CTA ให้กดตะกร้า",
        ]
    )
    return {
        "order": str(index),
        "product": product.name,
        "score": str(score),
        "category": product.category,
        "price_thb": f"{product.price:.0f}",
        "commission_percent": f"{product.commission_percent:.1f}",
        "estimated_commission_thb": f"{estimated_commission:.2f}",
        "product_role": product_role,
        "hook": hook,
        "angle": product.tiktok_angle or "รีวิวจากปัญหาจริง",
        "voiceover": voiceover,
        "shot_list": shot_list,
        "caption": caption,
        "hashtags": hashtags,
        "posting_time": posting_time,
        "affiliate_link": product.affiliate_link,
    }


def classify_product(estimated_commission: float) -> str:
    if estimated_commission >= 100:
        return "High Commission Product"
    if estimated_commission >= 30:
        return "Core Product"
    return "Traffic Product"


def render_markdown(
    brand: dict,
    account: dict,
    revenue_targets: dict,
    goal: str,
    plan_date: str,
    items: list[dict[str, str]],
) -> str:
    title = brand.get("brand_name", "TikTok Affiliate Agent")
    handle = account.get("handle", "unknown")
    profile_url = account.get("profile_url", "")
    posting_status = account.get("posting_status", "not_connected")
    effective_goal = goal or brand.get("goal", "สร้างคอนเทนต์ TikTok Affiliate ประจำวัน")
    weekly_target = float(revenue_targets.get("weekly_commission_target_thb", 30000))
    daily_target = float(revenue_targets.get("daily_commission_target_thb", weekly_target / 7))
    average_commission = average_item_commission(items)
    orders_needed = math.ceil(daily_target / average_commission) if average_commission else 0
    minimum_posts = revenue_targets.get("daily_operating_targets", {}).get("minimum_posts", len(items))
    lines = [
        f"# Daily Content Plan: {plan_date}",
        "",
        f"Brand: {title}",
        f"TikTok account: {handle} ({profile_url})",
        f"Direct posting status: {posting_status}",
        f"Goal: {effective_goal}",
        "",
        "## Revenue Target",
        "",
        f"- Weekly commission target: {weekly_target:,.0f} THB",
        f"- Daily commission target: {daily_target:,.0f} THB",
        f"- Average estimated commission from today's selected products: {average_commission:,.2f} THB/order",
        f"- Estimated orders needed today at this average: {orders_needed:,}",
        f"- Minimum posts today: {minimum_posts}",
        "",
        "## Today's Focus",
        "",
        "- ทำคลิปอย่างน้อย 4 ชิ้นจากสินค้าที่ pain point ชัด",
        "- ใช้สินค้าคอมมิชชันต่ำเป็น traffic product เท่านั้น",
        "- หาสินค้าคอมมิชชัน 50-120 บาทต่อออเดอร์เพิ่มก่อนเริ่ม scale",
        "- เปิดคลิปด้วยปัญหาจริงใน 3 วินาทีแรก",
        f"- เตรียมทุกโพสต์สำหรับบัญชี {handle}",
        "- ตรวจราคา ลิงก์ และตะกร้าก่อนโพสต์",
        "",
    ]

    for item in items:
        lines.extend(
            [
                f"## Clip {item['order']}: {item['product']}",
                "",
                f"Score: {item['score']}",
                f"Category: {item['category']}",
                f"Product role: {item['product_role']}",
                f"Price: {item['price_thb']} THB",
                f"Commission: {item['commission_percent']}%",
                f"Estimated commission/order: {item['estimated_commission_thb']} THB",
                f"Angle: {item['angle']}",
                f"Posting time: {item['posting_time']}",
                "",
                "### Hook",
                "",
                item["hook"],
                "",
                "### Voiceover",
                "",
                item["voiceover"],
                "",
                "### Shot List",
                "",
                item["shot_list"],
                "",
                "### Caption",
                "",
                item["caption"],
                "",
                "### Hashtags",
                "",
                item["hashtags"],
                "",
                "### Approval Checklist",
                "",
                "- ตรวจราคาล่าสุด",
                f"- ตรวจว่าโพสต์ลงบัญชี {handle}",
                "- ตรวจลิงก์ตะกร้าให้ตรงสินค้า",
                "- ตรวจว่าไม่มีคำเคลมเกินจริง",
                "- ดูวิดีโอเต็มก่อนโพสต์",
                "",
            ]
        )

    lines.extend(
        [
            "## End-of-Day Review",
            "",
            "- คลิปไหน retention สูงสุด",
            "- คลิปไหน CTR เข้าตะกร้าดีสุด",
            "- คลิปไหนสร้างคอมมิชชันจริง",
            "- คอมมิชชันวันนี้ห่างจาก 4,286 บาทเท่าไร",
            "- สินค้าไหนควรทำซ้ำพรุ่งนี้",
            "- Hook แบบไหนควรเลิกใช้",
            "",
        ]
    )
    return "\n".join(lines)


def average_item_commission(items: list[dict[str, str]]) -> float:
    if not items:
        return 0
    values = [float(item["estimated_commission_thb"]) for item in items]
    return sum(values) / len(values)


def write_posting_queue(path: Path, items: list[dict[str, str]]) -> None:
    fields = [
        "order",
        "product",
        "category",
        "product_role",
        "price_thb",
        "commission_percent",
        "estimated_commission_thb",
        "hook",
        "caption",
        "hashtags",
        "posting_time",
        "affiliate_link",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in items:
            writer.writerow({field: item[field] for field in fields})


def main() -> None:
    args = parse_args()
    brand = read_brand(Path(args.brand))
    account = read_json(Path(args.account))
    revenue_targets = read_json(Path(args.revenue_targets))
    products = read_products(Path(args.products))
    ranked = rank_products(products)
    posting_windows = brand.get("posting_windows") or ["09:00", "12:00", "19:00"]
    minimum_posts = int(revenue_targets.get("daily_operating_targets", {}).get("minimum_posts", 4))
    item_count = args.count if args.count > 0 else minimum_posts
    selected = ranked[: max(item_count, 1)]
    items = [
        make_plan_item(product, score, index + 1, posting_windows[index % len(posting_windows)])
        for index, (product, score) in enumerate(selected)
    ]

    output_dir = Path(args.out) / args.date
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "daily-content-plan.md"
    queue_path = output_dir / "posting_queue.csv"

    plan_path.write_text(render_markdown(brand, account, revenue_targets, args.goal, args.date, items), encoding="utf-8")
    write_posting_queue(queue_path, items)

    print(f"Created {plan_path}")
    print(f"Created {queue_path}")


if __name__ == "__main__":
    main()
