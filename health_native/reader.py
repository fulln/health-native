"""Read native Health JSON without writing or transmitting user records."""
import datetime as dt
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

SEP_MARKER = "|||HEALTH_NATIVE_ROW|||"
SEPARATORS = ("\x1f", SEP_MARKER)
TYPES = {
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_kcal",
    "HKQuantityTypeIdentifierHeartRate": "heart_rate_avg_bpm",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_bpm",
    "HKQuantityTypeIdentifierBodyMass": "weight_kg",
    "HKCategoryTypeIdentifierSleepAnalysis": "sleep_minutes",
}
FIELDS = tuple(TYPES.values())
DEFAULT_SUBDIRS = (
    "Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents",
    "Library/Mobile Documents/com~apple~CloudDocs/HealthNative",
)
MAX_BYTES, MAX_ROWS, MAX_FILES = 20 * 1024 * 1024, 100000, 1000
MAX_TOTAL_ROWS = 1000000
SF_DATALESS = 0x40000000  # Darwin sys/stat.h
PRODUCTION = re.compile(r"^health-native-(?:latest|\d{4}-\d{2}-\d{2}_\d{6})\.json$")
UNITS = {
    "steps": {"count": 1},
    "active_kcal": {"kcal": 1, "kJ": 1 / 4.184},
    "heart_rate_avg_bpm": {"count/min": 1, "bpm": 1},
    "resting_bpm": {"count/min": 1, "bpm": 1},
    "weight_kg": {"kg": 1, "g": 0.001, "lb": 0.45359237},
}
SLEEP = {
    "core": "core", "asleepcore": "core",
    "deep": "deep", "asleepdeep": "deep",
    "rem": "rem", "asleeprem": "rem",
    "asleep": "asleep", "asleepunspecified": "asleep",
    "inbed": "ignored", "awake": "ignored",
}


def default_data_dirs():
    return [Path.home() / part for part in DEFAULT_SUBDIRS]


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("时间必须为带时区的 ISO8601 字符串")
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("无效时间")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("时间缺少时区")
    return result.astimezone(dt.timezone.utc)


def number(value, unit, metric):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("无效数值")
    if not isinstance(unit, str) or unit not in UNITS[metric]:
        raise ValueError("不支持的单位")
    try:
        result = float(value) * UNITS[metric][unit]
    except (TypeError, ValueError, OverflowError):
        raise ValueError("无效数值")
    if not math.isfinite(result) or result < 0:
        raise ValueError("无效数值")
    return result


def stage(value):
    if not isinstance(value, str):
        raise ValueError("无效睡眠阶段")
    key = value.replace("HKCategoryValueSleepAnalysis", "").replace(" ", "").lower()
    if key not in SLEEP:
        raise ValueError("不支持的睡眠阶段")
    return SLEEP[key]


def expanded_rows(payload):
    """Validate column alignment before yielding a file's records."""
    schema = payload.get("schema")
    if schema == "apple_health_native_columns_v1":
        separator = payload.get("column_separator", "\x1f")
        if separator not in SEPARATORS:
            raise ValueError("不支持的列分隔符")
        batches = payload.get("batches")
        if not isinstance(batches, list) or len(batches) > 6:
            raise ValueError("batches 必须为最多六个批次")
        rows = []
        for batch in batches:
            if not isinstance(batch, dict):
                raise ValueError("无效批次")
            count = batch.get("count")
            if isinstance(count, bool) or not isinstance(count, (int, str)):
                raise ValueError("无效批次数量")
            if isinstance(count, str) and (not count.isdigit() or len(count) > 6):
                raise ValueError("无效批次数量")
            count = int(count)
            if not 0 <= count <= MAX_ROWS or len(rows) + count > MAX_ROWS:
                raise ValueError("样本数量超出上限")
            columns = {}
            for name in ("sourceName", "startDate", "endDate", "value", "unit"):
                value = batch.get(name)
                if not isinstance(value, str):
                    raise ValueError("批次缺少字符串列")
                if value == "" and (count == 0 or
                                    (batch.get("type") == "HKCategoryTypeIdentifierSleepAnalysis"
                                     and name in ("sourceName", "unit"))):
                    columns[name] = [""] * count
                else:
                    columns[name] = value.split(separator)
                if len(columns[name]) != count:
                    raise ValueError("列长度与 count 不一致")
            rows.extend(dict(type=batch.get("type"), **{
                name: column[index] for name, column in columns.items()
            }) for index in range(count))
        return rows
    if schema not in (None, "apple_health_native_shortcut_v1"):
        raise ValueError("不支持的原生导出格式")
    rows = payload.get("records")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("records 必须为有界数组")
    return rows


@dataclass
class Sample:
    metric: str
    source: str
    start: dt.datetime
    end: dt.datetime
    value: object
    rank: tuple
    allowed_wakes: set = field(default_factory=set)
    unrestricted_sleep: bool = False
    partial: bool = False

    def identity(self):
        return (self.metric, self.source, self.start, self.end,
                self.value if self.metric == "sleep_minutes" else None)


def union_seconds(rows):
    stop = None
    seconds = 0
    for start, end in sorted(set((r.start, r.end) for r in rows)):
        if stop is None or start >= stop:
            seconds += (end - start).total_seconds()
        elif end > stop:
            seconds += (end - stop).total_seconds()
        stop = max(stop, end) if stop is not None else end
    return seconds


def source_overlap(rows):
    active, point_time, point_sources = {}, None, set()
    for row in sorted(rows, key=lambda r: (r.start, r.end, r.source)):
        active = {source: end for source, end in active.items() if end > row.start}
        if any(source != row.source for source in active):
            return True
        if point_time != row.start:
            point_time, point_sources = row.start, set()
        if any(source != row.source for source in point_sources):
            return True
        if row.end == row.start:
            point_sources.add(row.source)
        else:
            active[row.source] = max(active.get(row.source, row.end), row.end)
    return False


def activity(rows):
    partial = any(row.partial for row in rows)
    if source_overlap(rows):
        by_source = defaultdict(list)
        for row in rows:
            by_source[row.source].append(row)
        chosen = max(sorted(by_source), key=lambda name: (
            union_seconds(by_source[name]), len(by_source[name])))
        rows = by_source[chosen]
        partial = True
    stop, total = None, 0
    for row in sorted(rows, key=lambda r: (r.start, r.end, r.source)):
        if stop is not None and row.start < stop:
            partial = True
            continue
        stop = row.end
        total += row.value
    return round(total, 2), "、".join(sorted({r.source for r in rows})), partial


def sleep_intervals(rows):
    """Sweep intervals, assigning contradictory detailed stages to unspecified."""
    events = defaultdict(Counter)
    for row in rows:
        if row.end > row.start:
            events[row.start][row.value] += 1
            events[row.end][row.value] -= 1
    active, totals, previous, conflict = Counter(), Counter(), None, False
    for instant in sorted(events):
        if previous is not None and instant > previous:
            present = {key for key, count in active.items() if count > 0}
            detailed = present - {"asleep"}
            if present:
                selected = next(iter(detailed)) if len(detailed) == 1 else "asleep"
                if len(detailed) > 1:
                    conflict = True
                totals[selected] += (instant - previous).total_seconds() / 60
        active.update(events[instant])
        previous = instant
    return {key: round(value, 2) for key, value in totals.items()}, conflict


class HealthReader:
    def __init__(self, data_dirs=None, timezone="Asia/Shanghai"):
        self.data_dirs = [Path(path).expanduser() for path in (
            default_data_dirs() if data_dirs is None else data_dirs)]
        self.tz = ZoneInfo(timezone)

    def _files(self, warnings):
        found = set()
        for directory in self.data_dirs:
            if not directory.exists():
                continue
            try:
                found.update(path for path in directory.rglob("health-native-*.json")
                             if PRODUCTION.fullmatch(path.name) and path.is_file())
            except OSError:
                warnings.append("目录暂不可读，请检查 iCloud 同步状态")
        def modified(path):
            try:
                return path.stat().st_mtime_ns
            except OSError:
                return -1
        paths = sorted(found, key=lambda path: (modified(path), str(path)), reverse=True)
        if len(paths) > MAX_FILES:
            warnings.append("文件过多，仅读取最近 %d 个文件" % MAX_FILES)
        return paths[:MAX_FILES]

    def _sample(self, row, exported, scope, rank):
        if not isinstance(row, dict) or row.get("type") not in TYPES:
            raise ValueError("无效记录类型")
        metric = TYPES[row["type"]]
        start, end = timestamp(row.get("startDate")), timestamp(row.get("endDate"))
        if end < start:
            raise ValueError("结束时间早于开始时间")
        source = row.get("sourceName")
        if not isinstance(source, str) or (not source.strip() and metric != "sleep_minutes"):
            raise ValueError("缺少来源")
        partial = not source.strip()
        source = source.strip() or "未提供来源"
        value = (stage(row.get("value")) if metric == "sleep_minutes" else
                 number(row.get("value"), row.get("unit"), metric))
        if metric == "sleep_minutes":
            if row.get("unit", "") != "":
                raise ValueError("睡眠单位应为空")
            if value == "ignored":
                return None
        local_day = start.astimezone(self.tz).date()
        export_day = exported.astimezone(self.tz).date()
        if metric != "sleep_minutes" and scope == "daily" and local_day != export_day - dt.timedelta(days=1):
            return None
        if metric != "sleep_minutes":
            partial = partial or end.astimezone(self.tz).date() != local_day or local_day >= export_day
        sample = Sample(metric, source, start, end, value, rank, partial=partial)
        if metric == "sleep_minutes":
            if scope == "daily":
                sample.allowed_wakes.add(export_day)
            else:
                sample.unrestricted_sleep = True
        return sample

    @staticmethod
    def _day(date):
        return dict(date=date, **{metric: None for metric in FIELDS},
                    sleep_stages=None, sources={}, partial_metrics=[])

    def read(self):
        warnings, revisions, latest, read, skipped, duplicates, invalid = [], {}, None, 0, 0, 0, 0
        total = 0
        for path in self._files(warnings):
            try:
                info = path.stat()
                if getattr(info, "st_flags", 0) & SF_DATALESS:
                    skipped += 1
                    warnings.append("%s：iCloud 文件尚未下载，请在 Finder 中下载后刷新" % path.name)
                    continue
                if info.st_size == 0:
                    skipped += 1
                    warnings.append("%s：文件为空，可能仍在同步，请稍后刷新" % path.name)
                    continue
                if info.st_size > MAX_BYTES:
                    raise ValueError("文件超过 20MB 上限")
                with path.open("rb") as stream:
                    raw = stream.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("文件超过 20MB 上限")
                payload = json.loads(raw.decode("utf-8-sig"))
                if not isinstance(payload, dict):
                    raise ValueError("JSON 顶层必须为对象")
                if payload.get("probe") or "probe" in str(payload.get("schema", "")).lower():
                    skipped += 1
                    continue
                exported = timestamp(payload.get("export_date"))
                rows = expanded_rows(payload)
                total += len(rows)
                if total > MAX_TOTAL_ROWS:
                    warnings.append("样本总量超过上限，剩余文件未读取")
                    skipped += 1
                    break
                bad = 0
                for row in rows:
                    try:
                        sample = self._sample(row, exported, payload.get("capture_scope"),
                                              (exported, info.st_mtime_ns, str(path)))
                    except (ValueError, TypeError, OverflowError):
                        bad += 1
                        continue
                    if sample is None:
                        continue
                    key = sample.identity()
                    old = revisions.get(key)
                    if old is not None:
                        duplicates += 1
                        sample.allowed_wakes.update(old.allowed_wakes)
                        sample.unrestricted_sleep |= old.unrestricted_sleep
                        sample.partial |= old.partial
                        if old.rank > sample.rank:
                            old.allowed_wakes.update(sample.allowed_wakes)
                            old.unrestricted_sleep |= sample.unrestricted_sleep
                            continue
                    revisions[key] = sample
                if bad:
                    warnings.append("%s：跳过 %d 条单位、来源或时间无效的记录" % (path.name, bad))
                    invalid += bad
                read += 1
                latest = max(latest, exported) if latest else exported
            except (OSError, ValueError, UnicodeError, OverflowError):
                skipped += 1
                warnings.append("%s：文件未读取，请检查格式和 iCloud 下载状态" % path.name)
        days, grouped, sleepers = {}, defaultdict(list), defaultdict(list)
        for row in revisions.values():
            if row.metric == "sleep_minutes":
                # Unspecified unknown-source sleep is a separate candidate,
                # avoiding double-counting an unlabelled detailed stage stream.
                stream = row.source + (" · 未分层" if row.partial and row.value == "asleep" else "")
                sleepers[stream].append(row)
            else:
                grouped[(row.start.astimezone(self.tz).date().isoformat(), row.metric)].append(row)
        for (day, metric), rows in grouped.items():
            bucket = days.setdefault(day, self._day(day))
            partial = any(row.partial for row in rows)
            if metric in ("steps", "active_kcal"):
                value, source, partial = activity(rows)
            elif metric == "weight_kg":
                chosen = max(rows, key=lambda row: (row.end, row.start, row.rank))
                value, source = round(chosen.value, 2), chosen.source
            else:
                candidates = defaultdict(list)
                for row in rows:
                    candidates[row.source].append(row)
                source = max(sorted(candidates), key=lambda name: len(candidates[name]))
                chosen = candidates[source]
                value = round(sum(row.value for row in chosen) / len(chosen), 2)
                partial |= len(candidates) > 1
            bucket[metric], bucket["sources"][metric] = value, source
            if partial:
                bucket["partial_metrics"].append(metric)
        candidates = defaultdict(dict)
        for stream, rows in sleepers.items():
            sessions, current, stop = [], [], None
            for row in sorted(rows, key=lambda item: (item.start, item.end)):
                if stop is not None and row.start - stop > dt.timedelta(hours=3):
                    sessions.append(current)
                    current, stop = [], None
                current.append(row)
                stop = max(stop, row.end) if stop else row.end
            if current:
                sessions.append(current)
            for session in sessions:
                wake = max(row.end for row in session).astimezone(self.tz).date()
                if not any(row.unrestricted_sleep or wake in row.allowed_wakes for row in session):
                    continue
                candidates[wake.isoformat()].setdefault(stream, []).extend(session)
        for day, streams in candidates.items():
            chosen_stream = max(sorted(streams), key=lambda name: (
                any(row.value != "asleep" for row in streams[name]),
                union_seconds([row for row in streams[name] if row.value != "asleep"]),
                union_seconds(streams[name])))
            chosen = streams[chosen_stream]
            stages, conflict = sleep_intervals(chosen)
            if not stages:
                continue
            bucket = days.setdefault(day, self._day(day))
            bucket["sleep_minutes"] = round(sum(stages.values()), 2)
            bucket["sleep_stages"] = stages
            bucket["sources"]["sleep_minutes"] = chosen_stream
            if conflict or len(streams) > 1 or any(row.partial for row in chosen):
                bucket["partial_metrics"].append("sleep_minutes")
        return {
            "mode": "local", "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source": {"label": "iCloud · 快捷指令", "directories": [str(path) for path in self.data_dirs],
                       "files_read": read, "files_skipped": skipped,
                       "latest_export": latest.isoformat() if latest else None,
                       "timezone": str(self.tz), "warnings": warnings},
            "counts": {"unique_samples": len(revisions), "duplicate_samples": duplicates,
                       "invalid_samples": invalid},
            "days": [days[day] for day in sorted(days)],
        }
