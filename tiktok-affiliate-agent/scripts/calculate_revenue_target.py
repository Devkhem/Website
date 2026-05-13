#!/usr/bin/env python3
"""Calculate TikTok affiliate order targets from a weekly commission goal."""

from __future__ import annotations

import argparse
import math


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate order targets for TikTok affiliate revenue goals.")
    parser.add_argument("--weekly-target", type=float, default=30000, help="Weekly commission target in THB.")
    parser.add_argument(
        "--commission-per-order",
        type=float,
        nargs="+",
        default=[30, 50, 80, 120],
        help="Average commission per order scenarios in THB.",
    )
    parser.add_argument("--days", type=int, default=7, help="Working days per week.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    daily_target = args.weekly_target / args.days
    print(f"Weekly commission target: {args.weekly_target:,.0f} THB")
    print(f"Daily commission target: {daily_target:,.0f} THB")
    print()
    print("commission/order | orders/week | orders/day")
    print("-----------------|-------------|-----------")
    for commission in args.commission_per_order:
        if commission <= 0:
            continue
        weekly_orders = math.ceil(args.weekly_target / commission)
        daily_orders = math.ceil(daily_target / commission)
        print(f"{commission:>15,.0f} | {weekly_orders:>11,} | {daily_orders:>9,}")


if __name__ == "__main__":
    main()

