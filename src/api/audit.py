"""Frozen tail sampling, independent of display order and the shared queue CSV contract."""

from __future__ import annotations

import hashlib
import json
import math
import random

POLICY_VERSION = "tail-outside-top-v1"


def policy(top_frac=0.2, rate=0.05, seed=42):
    if (
        not isinstance(top_frac, (float, int))
        or isinstance(top_frac, bool)
        or not math.isfinite(top_frac)
        or not 0 < top_frac <= 1
    ):
        raise ValueError("audit_top_frac phải trong (0,1]")
    if (
        not isinstance(rate, (float, int))
        or isinstance(rate, bool)
        or not math.isfinite(rate)
        or not 0 <= rate <= 1
    ):
        raise ValueError("audit_rate phải trong [0,1]")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("audit_seed phải là số nguyên")
    return {"policy_version": POLICY_VERSION, "top_frac": top_frac, "rate": rate, "seed": seed}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def make_plan(frame, queue_id, *, top_frac=0.2, rate=0.05, seed=42):
    options = policy(top_frac, rate, seed)
    rows = frame.sort_values("rank")
    ids = rows.image_id.tolist()
    if len(set(ids)) != len(ids):
        raise ValueError("Queue audit có image_id trùng")
    if rows['rank'].tolist() != list(range(1, len(rows)+1)):
        raise ValueError('Plan phải được freeze từ rank1..N của queue gốc')
    n_top = math.ceil(top_frac * len(ids))
    tail = ids[n_top:]
    n_audit = math.ceil(rate * len(tail))
    selected = random.Random(seed).sample(tail, n_audit)
    order, cursor = [], 0
    interval = max(1, n_top // n_audit) if n_audit else None
    for index, image_id in enumerate(ids[:n_top], 1):
        order.append(image_id)
        if interval and index % interval == 0 and cursor < n_audit:
            order.append(selected[cursor])
            cursor += 1
    order.extend(selected[cursor:])
    sampled = set(selected)
    order.extend(i for i in tail if i not in sampled)
    result = {
        **options,
        "source_queue_id": queue_id,
        "source_model_version": str(rows.model_version.iloc[0]) if len(rows) else None,
        "source_ranks": {r.image_id: int(r.rank) for r in rows.itertuples(index=False)},
        "N": len(ids),
        "n_top": n_top,
        "n_tail": len(tail),
        "n_audit": n_audit,
        "interval": interval,
        "audit_ids": selected,
        "order": order,
    }
    return {**result, "policy_id": digest(result)}


def validate_plan(plan):
    import pandas as pd

    frame = pd.DataFrame(
        [[i, r, plan["source_model_version"]] for i, r in plan["source_ranks"].items()],
        columns=["image_id", "rank", "model_version"],
    )
    expected = make_plan(
        frame, plan["source_queue_id"], top_frac=plan["top_frac"], rate=plan["rate"], seed=plan["seed"]
    )
    if expected != plan:
        raise ValueError("Sampling plan không khớp nguồn/chính sách/hash")
    return plan


def summary(plan, records):
    """Unique latest labels per sampled image; old policies and file-order sessions excluded."""
    if plan.get("status") == "unavailable":
        return {**plan, "status": "unavailable", "valid": 0, "wilson95": None, "tail_errors_estimate": None}
    sampled = set(plan['audit_ids'])
    eligible = [
        r
        for r in records
        if r["review_order"] == "priority"
        and r["is_audit"]
        and r.get("audit_policy_id") == plan["policy_id"]
        and r.get("audit_source_queue_id") == plan["source_queue_id"]
        and r["image_id"] in sampled
    ]
    latest = {r["image_id"]: r for r in eligible}
    counts = {
        key: sum(r["verdict"] == key for r in latest.values()) for key in ("error", "false_alarm", "skip")
    }
    n = counts["error"] + counts["false_alarm"]
    rate, interval = None, None
    if n:
        rate = counts["error"] / n
        z = 1.959963984540054
        denominator = 1 + z * z / n
        center = (rate + z * z / (2 * n)) / denominator
        radius = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denominator
        interval = [max(0, center - radius), min(1, center + radius)]
    metadata = {
        k: plan[k]
        for k in (
            "policy_version",
            "policy_id",
            "source_queue_id",
            "source_model_version",
            "N",
            "n_top",
            "n_tail",
            "n_audit",
            "seed",
            "top_frac",
            "rate",
        )
    }
    return {
        **metadata,
        "status": "sufficient" if n >= 30 else "insufficient",
        "message": "Có ít nhất 30 verdict hợp lệ" if n >= 30 else "Chưa đủ mẫu (<30); không suy rộng",
        "valid": n,
        "verdicts": counts,
        "events": len(eligible),
        "error_rate": rate,
        "wilson95": interval,
        "tail_errors_estimate": rate * plan["n_tail"] if n >= 30 else None,
        "tail_errors_interval95": [v * plan["n_tail"] for v in interval] if n >= 30 else None,
        "planned_review_images": plan["n_top"] + plan["n_audit"],
        "planned_review_fraction": (plan["n_top"] + plan["n_audit"]) / plan["N"] if plan["N"] else 0,
        "note": "Top và chi phí audit báo riêng; rank CSV không phải thứ tự đã chèn audit.",
    }
