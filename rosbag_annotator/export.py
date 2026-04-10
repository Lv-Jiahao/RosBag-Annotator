"""
ExportWorker — QThread that cuts and exports sub-bags.

Strategy:
  1. rosbag2_py (Python API) if available, else ros2 bag filter CLI
  2. Overwrites existing output directory (replace semantics, no _2 suffixes)
  3. Patches metadata.yaml with lerobot.operator_prompt in custom_data
"""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

import yaml
from PyQt6.QtCore import QThread, pyqtSignal

try:
    import rosbag2_py
    HAS_ROSBAG2_PY = True
except ImportError:
    HAS_ROSBAG2_PY = False


class ExportWorker(QThread):
    progress = pyqtSignal(str, int, int)   # (message, done, total)
    finished = pyqtSignal(bool, str)       # (ok, message)

    def __init__(self, annotations, parent=None):
        super().__init__(parent)
        self.annotations = annotations

    def run(self):
        total = sum(len(a.get_segments()) for a in self.annotations)
        done  = 0
        for ann in self.annotations:
            stem    = Path(ann.bag_path).stem
            storage = self._detect_storage(ann.bag_path)
            for idx, seg in enumerate(ann.get_segments()):
                if not seg.out_dir:
                    self.finished.emit(
                        False, f"分段 {idx+1}（{stem}）未设置输出目录。"); return
                self.progress.emit(f"Exporting {stem} — seg {idx+1}", done, total)
                task_dir = Path(seg.out_dir)
                task_dir.mkdir(parents=True, exist_ok=True)
                out = self._out_path(task_dir, stem, idx)
                try:
                    if HAS_ROSBAG2_PY: self._export_py(ann.bag_path, seg, out, storage)
                    else:              self._export_cli(ann.bag_path, seg, out)
                    self._patch_yaml(seg, out)
                except Exception as e:
                    self.finished.emit(False, f"Seg {idx+1} of {stem}:\n{e}"); return
                done += 1
        self.finished.emit(True, f"Done — {done} sub-bags exported")

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _out_path(task_dir: Path, stem: str, idx: int) -> Path:
        """Replace existing output directory (overwrite semantics)."""
        p = task_dir / f"{stem}_{idx+1:03d}"
        if p.exists():
            shutil.rmtree(p)
        return p

    @staticmethod
    def _detect_storage(bag_path: str) -> str:
        try:
            with open(Path(bag_path) / "metadata.yaml") as f:
                m = yaml.safe_load(f)
            return (m.get("rosbag2_bagfile_information", {})
                     .get("storage_identifier", "sqlite3"))
        except Exception:
            return "sqlite3"

    @staticmethod
    def _export_py(bag_path: str, seg, out_path: Path, storage: str):
        reader = rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=bag_path, storage_id=storage),
                    rosbag2_py.ConverterOptions("", ""))
        writer = rosbag2_py.SequentialWriter()
        writer.open(rosbag2_py.StorageOptions(uri=str(out_path), storage_id="sqlite3"),
                    rosbag2_py.ConverterOptions("", ""))
        for tm in reader.get_all_topics_and_types():
            writer.create_topic(tm)
        try: reader.seek(seg.start_ns)
        except AttributeError: pass
        while reader.has_next():
            topic, data, ts = reader.read_next()
            if ts < seg.start_ns: continue
            if ts > seg.end_ns:   break
            writer.write(topic, data, ts)
        del writer, reader

    @staticmethod
    def _export_cli(bag_path: str, seg, out_path: Path):
        cmd = ["ros2", "bag", "filter", bag_path, "-o", str(out_path),
               "--start-time", str(seg.start_ns / 1e9),
               "--end-time",   str(seg.end_ns   / 1e9)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"ros2 bag filter:\n{r.stderr}")

    @staticmethod
    def _patch_yaml(seg, out_path: Path):
        """Append custom_data.lerobot.operator_prompt to metadata.yaml (idempotent)."""
        f = out_path / "metadata.yaml"
        if not f.exists(): return

        # strip any existing custom_data block
        lines = f.read_text(encoding="utf-8").splitlines()
        clean, in_custom = [], False
        for line in lines:
            s = line.rstrip()
            if s == "  custom_data:":
                in_custom = True; continue
            if in_custom:
                if s == "" or s.startswith("    "): continue
                in_custom = False
            clean.append(line)

        # YAML-safe scalar for prompt
        prompt = (seg.prompt or "").strip()
        special = set(list('-?:,[]{}#&*!|>@`%') + [chr(39), chr(34)])
        needs_q = (not prompt
                   or prompt[0] in special
                   or ": " in prompt
                   or prompt.startswith("- "))
        if needs_q:
            escaped    = prompt.replace("\\", "\\\\").replace('"', '\\"')
            prompt_val = f'"{escaped}"'
        else:
            prompt_val = prompt

        body = "\n".join(clean).rstrip("\n")
        block = f"\n  custom_data:\n    lerobot.operator_prompt: {prompt_val}\n"
        f.write_text(body + block, encoding="utf-8")
