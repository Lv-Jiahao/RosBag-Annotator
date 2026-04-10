"""
FullFrameExtractor — QThread that loads ALL frames from a RosBag image topic.

Key design decisions:
  - Reads .db3 files directly via SQLite (bypasses rosbag2_py ordering bugs)
  - Monotonic unwrapping handles 32-bit counter rollover (~4.295 s period)
  - Prefers CDR header.stamp (absolute Unix epoch) for cross-topic alignment
  - Falls back to rosbag2_py for non-SQLite formats (MCAP, etc.)
  - Emits QImage (not QPixmap) — QPixmap must be created in the main thread
"""
from __future__ import annotations
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui  import QImage

from .cdr import raw_to_image, extract_header_stamp_ns, HAS_CV2

_DEBUG = True

try:
    import rosbag2_py
    HAS_ROSBAG2_PY = True
except ImportError:
    HAS_ROSBAG2_PY = False


class FullFrameExtractor(QThread):
    frame_ready = pyqtSignal(object, object)  # (ts_ns: int, qi: QImage)
    progress    = pyqtSignal(int)             # frames loaded so far
    finished    = pyqtSignal(int)             # total frames decoded

    def __init__(self, bag_path, topic, topic_type,
                 start_ns, end_ns, storage_id="sqlite3", parent=None):
        super().__init__(parent)
        self.bag_path   = bag_path
        self.topic      = topic
        self.topic_type = topic_type
        self.start_ns   = start_ns
        self.end_ns     = end_ns
        self.storage_id = storage_id
        self._stop      = False

    def stop(self):
        self._stop = True

    def run(self):
        if not HAS_CV2:
            self.finished.emit(0); return
        db3_files = sorted(Path(self.bag_path).glob("*.db3"))
        if db3_files:
            self._run_sqlite(db3_files)
        elif HAS_ROSBAG2_PY:
            self._run_rosbag2py_fallback()
        else:
            print("[FullFrameExtractor] No .db3 and no rosbag2_py")
            self.finished.emit(0)

    # ── SQLite path ────────────────────────────────────────────────────────────

    def _run_sqlite(self, db3_files):
        import sqlite3

        if _DEBUG:
            print(f"[DEBUG] _run_sqlite: topic='{self.topic}'")

        def read_db3_rowid(path):
            result = []
            try:
                conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                cur  = conn.cursor()
                cur.execute("SELECT id FROM topics WHERE name=?", (self.topic,))
                row = cur.fetchone()
                if row is None:
                    conn.close(); return result
                topic_id = row[0]
                conn.execute("PRAGMA cache_size=-32768")   # 32 MB page cache
                dcur = conn.cursor()
                dcur.execute(
                    "SELECT timestamp, data FROM messages "
                    "WHERE topic_id=? ORDER BY rowid", (topic_id,))
                rows = dcur.fetchall()
                conn.close()
            except Exception as ex:
                print(f"[read_db3 {path.name}] {ex}"); return result
            for recv_ts, blob in rows:
                ts = int(recv_ts)
                if ts < 0: ts += (1 << 32)
                result.append((ts, bytes(blob)))
            return result

        # ── monotonic unwrapping ───────────────────────────────────────────────
        HALF_RANGE    = 1 << 31
        accumulated   = 0
        prev_unsigned = None
        all_frames    = []

        for f in db3_files:
            for raw_ts, blob in read_db3_rowid(f):
                if prev_unsigned is not None:
                    diff = raw_ts - prev_unsigned
                    if diff < -HALF_RANGE:
                        accumulated += (1 << 32)
                all_frames.append((raw_ts + accumulated, blob))
                prev_unsigned = raw_ts

        if not all_frames:
            if _DEBUG: print("[DEBUG] no frames found")
            self.finished.emit(0); return

        # ── time-axis alignment ────────────────────────────────────────────────
        bag_dur    = max(self.end_ns - self.start_ns, 1)
        first_ts   = all_frames[0][0]
        time_offset = 0
        if abs(first_ts - self.start_ns) > bag_dur * 10:
            time_offset = self.start_ns - first_ts
            if _DEBUG:
                print(f"[DEBUG] Time-axis mismatch — applying offset "
                      f"{time_offset/1e9:+.3f}s")

        # ── decode + emit ──────────────────────────────────────────────────────
        count = 0; fail_count = 0
        header_ok = 0; header_fail = 0

        for ts_raw, blob in all_frames:
            if self._stop: break

            hdr_ns = extract_header_stamp_ns(blob)
            if hdr_ns > 0:
                emit_ts = hdr_ns
                header_ok += 1
            else:
                ts_c = ts_raw + time_offset
                if ts_c < self.start_ns: continue
                if ts_c > self.end_ns:   continue
                emit_ts = ts_c
                header_fail += 1

            qi = raw_to_image(blob, self.topic_type)
            if qi is not None:
                if _DEBUG and count < 5:
                    print(f"[DEBUG]   frame #{count+1}: "
                          f"stamp={emit_ts/1e9:.3f}s  {qi.width()}x{qi.height()}  "
                          f"({'header' if hdr_ns > 0 else 'counter'})")
                self.frame_ready.emit(emit_ts, qi)
                count += 1
                if count % 20 == 0: self.progress.emit(count)
            else:
                fail_count += 1

        if _DEBUG:
            print(f"[DEBUG] done: {count} decoded, {fail_count} failed, "
                  f"header_ok={header_ok} header_fail={header_fail}")
        self.finished.emit(count)

    # ── rosbag2_py fallback ────────────────────────────────────────────────────

    def _run_rosbag2py_fallback(self):
        count = 0; prev_ts = -1
        try:
            reader = rosbag2_py.SequentialReader()
            reader.open(
                rosbag2_py.StorageOptions(uri=self.bag_path,
                                          storage_id=self.storage_id),
                rosbag2_py.ConverterOptions("", ""))
            reader.set_filter(rosbag2_py.StorageFilter(topics=[self.topic]))
            try: reader.seek(self.start_ns)
            except AttributeError: pass

            while reader.has_next() and not self._stop:
                _, data, ts = reader.read_next()
                if ts < self.start_ns: continue
                if ts > self.end_ns:   break
                if ts < prev_ts:
                    print(f"[WARN] rosbag2_py out-of-order: {ts} < {prev_ts}")
                    continue
                prev_ts = ts
                qi = raw_to_image(bytes(data), self.topic_type)
                if qi is not None:
                    self.frame_ready.emit(ts, qi)
                    count += 1
                    if count % 20 == 0: self.progress.emit(count)
            del reader
        except Exception as ex:
            print(f"[FullFrameExtractor rosbag2py] {ex}")
        self.finished.emit(count)
