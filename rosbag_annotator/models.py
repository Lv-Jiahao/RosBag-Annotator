"""
Data models: Segment, BagMeta, BagAnnotation
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


def _is_image_type(t: str) -> bool:
    return "sensor_msgs" in t and "Image" in t


@dataclass
class Segment:
    start_ns: int
    end_ns:   int
    prompt:   str = ""
    out_dir:  str = ""

    @property
    def duration_ns(self): return self.end_ns - self.start_ns

    def duration_str(self):
        s = self.duration_ns / 1e9
        return f"{int(s//60)}m {s%60:.1f}s" if s >= 60 else f"{s:.2f}s"

    def start_str(self): return f"{self.start_ns/1e9:.3f}s"
    def end_str(self):   return f"{self.end_ns/1e9:.3f}s"


@dataclass
class BagMeta:
    bag_path:      str
    topics:        List[dict]
    start_time_ns: int
    end_time_ns:   int
    duration_ns:   int
    message_count: int
    storage_id:    str = "sqlite3"

    @property
    def name(self): return Path(self.bag_path).name

    @property
    def duration_str(self):
        s = self.duration_ns / 1e9
        return f"{int(s//60)}m {s%60:.1f}s" if s >= 60 else f"{s:.2f}s"

    @property
    def image_topics(self):
        return [t for t in self.topics if _is_image_type(t["type"])]


@dataclass
class BagAnnotation:
    bag_path:      str
    start_ns:      int
    end_ns:        int
    cut_points_ns: List[int] = field(default_factory=list)
    prompts:       List[str] = field(default_factory=list)
    out_dirs:      List[str] = field(default_factory=list)

    def _ensure_lists(self):
        n = len(self.cut_points_ns) + 1
        while len(self.prompts)  < n: self.prompts.append("")
        while len(self.out_dirs) < n: self.out_dirs.append("")
        self.prompts  = self.prompts[:n]
        self.out_dirs = self.out_dirs[:n]

    def _ensure_prompts(self): self._ensure_lists()

    def get_segments(self) -> List[Segment]:
        self._ensure_lists()
        b = [self.start_ns] + sorted(self.cut_points_ns) + [self.end_ns]
        return [Segment(b[i], b[i+1],
                        self.prompts[i]  if i < len(self.prompts)  else "",
                        self.out_dirs[i] if i < len(self.out_dirs) else "")
                for i in range(len(b)-1)]

    def set_prompt(self, idx: int, text: str):
        self._ensure_lists()
        if 0 <= idx < len(self.prompts): self.prompts[idx] = text

    def set_out_dir(self, idx: int, path: str):
        self._ensure_lists()
        if 0 <= idx < len(self.out_dirs): self.out_dirs[idx] = path

    def to_dict(self) -> dict:
        self._ensure_lists()
        return {
            "bag_path": self.bag_path,
            "start_ns": self.start_ns,
            "end_ns":   self.end_ns,
            "cut_points_ns": sorted(self.cut_points_ns),
            "prompts":  self.prompts,
            "out_dirs": self.out_dirs,
            "segments": [
                {"index": i, "start_ns": s.start_ns, "end_ns": s.end_ns,
                 "duration_ns": s.duration_ns, "prompt": s.prompt, "out_dir": s.out_dir}
                for i, s in enumerate(self.get_segments())
            ],
        }
