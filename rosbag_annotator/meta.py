"""
RosBag metadata loader — reads metadata.yaml and returns BagMeta.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

import yaml

from .models import BagMeta

_DEBUG = True


def load_bag_meta(bag_path: str) -> Optional[BagMeta]:
    p = Path(bag_path)
    f = p / "metadata.yaml"
    if not f.exists():
        return None
    try:
        with open(f, encoding="utf-8") as fh:
            meta = yaml.safe_load(fh)
        rb = meta.get("rosbag2_bagfile_information", {})
        start_ns = None; end_ns = 0; total = 0
        for fi in rb.get("files", []):
            st  = fi.get("starting_time", {}).get("nanoseconds_since_epoch", 0)
            dur = fi.get("duration", {}).get("nanoseconds", 0)
            if start_ns is None or st < start_ns: start_ns = st
            end_ns = max(end_ns, st + dur)
            total += fi.get("message_count", 0)
        if start_ns is None: start_ns = 0

        # ★ 修正 end_ns < start_ns（metadata 中 uint32 回绕导致）
        if end_ns < start_ns:
            candidate = end_ns
            while candidate < start_ns and (candidate - end_ns) < (1 << 34):
                candidate += (1 << 32)
            if candidate > start_ns:
                end_ns = candidate
                if _DEBUG:
                    print(f"[load_bag_meta] end_ns wrapped, corrected to "
                          f"+{(end_ns-start_ns)/1e9:.3f}s")

        topics = [
            {"name":  t.get("topic_metadata", {}).get("name",  ""),
             "type":  t.get("topic_metadata", {}).get("type",  ""),
             "count": t.get("message_count", 0)}
            for t in rb.get("topics_with_message_count", [])
        ]
        return BagMeta(
            bag_path=str(p), topics=topics,
            start_time_ns=start_ns, end_time_ns=end_ns,
            duration_ns=end_ns - start_ns, message_count=total,
            storage_id=rb.get("storage_identifier", "sqlite3"),
        )
    except Exception as e:
        print(f"[load_bag_meta] {e}")
        return None
