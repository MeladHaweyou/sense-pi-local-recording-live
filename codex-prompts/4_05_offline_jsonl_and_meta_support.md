# Prompt: Add JSONL and .meta.json support to OfflineTab and plotter

You are an AI coding assistant working on the **sensepi** project.
Your task is to extend the **offline log viewer** so that it can handle
JSONL logs written by the Pi logger, and to take advantage of `.meta.json`
sidecar files when available.

Focus on **integration** into existing OfflineTab and plotter code.

---

## Context: OfflineTab and plotter

Relevant modules:

- `sensepi/gui/tabs/tab_offline.py`
- `sensepi/tools/plotter.py` (or similar path; adjust to repo)
- JSON streaming/logging protocol (e.g. `docs/json_protocol.md`)

### OfflineTab (simplified)

```python
class OfflineTab(QWidget):
    def __init__(self, app_config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self._file_list = QListWidget()
        self._load_button = QPushButton("Load")
        ...
        self._load_button.clicked.connect(self._on_load_clicked)
        self._refresh_file_list()

    def _candidate_logs(self) -> list[Path]:
        base = self._app_config.paths.data_root
        raw = base / "data" / "raw"
        processed = base / "data" / "processed"
        logs_dir = base / "logs"
        return list(raw.glob("*.csv")) + list(processed.glob("*.csv")) + list(logs_dir.glob("*.csv"))

    def _on_load_clicked(self):
        path = self._selected_path()
        if not path:
            return
        fig = plotter.build_plot_for_file(path)
        self._show_figure(fig)
```

Currently it assumes **CSV** logs only.

### plotter.build_plot_for_file (simplified)

```python
def build_plot_for_file(path: Path) -> Figure:
    df = _load_csv(path)
    sensor_type = infer_sensor_type_from_columns(df.columns)
    return _plot_for_sensor_type(sensor_type, df)
```

There is currently no JSONL handling or `.meta.json` usage.

The Pi logger, however, can write **JSON lines**, each containing fields for timestamp and channels,
and often writes a sibling `.meta.json` file describing sampling rate and channel names.

---

## What you must implement

### 1. Extend OfflineTab to include JSONL logs

1. In `_candidate_logs`, include `.jsonl` files in the search:

   - Decide whether to show `.jsonl` files alongside `.csv` in the same list.
   - For compatibility, keep `.csv` support unchanged.

   Example:

   ```python
   def _candidate_logs(self) -> list[Path]:
       exts = ("*.csv", "*.jsonl")
       paths: list[Path] = []
       for base in [raw, processed, logs_dir]:
           for pattern in exts:
               paths.extend(base.glob(pattern))
       return sorted(paths)
   ```

2. Make sure the list widget displays the full filename (including extension) or a clear label
   so users can tell CSV and JSONL files apart.

### 2. Teach plotter.build_plot_for_file to handle JSONL

1. Modify `build_plot_for_file(path: Path)` to dispatch based on suffix:

   ```python
   def build_plot_for_file(path: Path) -> Figure:
       if path.suffix.lower() == ".csv":
           df, meta = _load_csv_with_meta(path)
       elif path.suffix.lower() == ".jsonl":
           df, meta = _load_jsonl_with_meta(path)
       else:
           raise ValueError(f"Unsupported log file type: {path.suffix}")
       sensor_type = infer_sensor_type(df, meta)
       return _plot_for_sensor_type(sensor_type, df, meta)
   ```

   You can keep the function names flexible; the key idea is to return both
   a `DataFrame` and some optional metadata.

2. Implement `_load_jsonl_with_meta(path: Path)`:

   - Open the `.jsonl` file.
   - For each line, `json.loads(line)`.
   - Extract fields used by the live JSON parser (e.g. timestamp and axis channels).
   - Build a `pandas.DataFrame` with one row per sample.
   - Try to preserve column names compatible with existing plotting code
     (e.g. `ax`, `ay`, `az`, etc.).

   Example sketch (do not forget imports and error handling):

   ```python
   def _load_jsonl_with_meta(path: Path) -> tuple[pd.DataFrame, dict | None]:
       records: list[dict] = []
       with path.open("r", encoding="utf-8") as f:
           for line in f:
               line = line.strip()
               if not line:
                   continue
               obj = json.loads(line)
               records.append(obj)
       df = pd.DataFrame.from_records(records)
       meta = _load_meta_sidecar(path)
       return df, meta
   ```

### 3. Exploit `.meta.json` sidecar files

1. Add a helper to load sidecar metadata:

   ```python
   def _load_meta_sidecar(path: Path) -> dict | None:
       meta_path = path.with_suffix(path.suffix + ".meta.json")
       if not meta_path.exists():
           return None
       with meta_path.open("r", encoding="utf-8") as f:
           return json.load(f)
   ```

2. Use metadata to improve plotting:

   - **Sampling rate**: if `meta` contains `"device_rate_hz"`, use it to set axis labels,
     titles, or any relevant annotations.
   - **Channels**: if `meta` includes an explicit channel list (e.g. `"channels": ["ax","ay","az"]`),
     prefer that over inferring from column names.

   Implement an `infer_sensor_type(df, meta)` that:

   - If `meta` has a `"sensor_type"` field, trust it.
   - Else, fall back to existing column‑based heuristics.

   The plotting function `_plot_for_sensor_type` can accept `meta` and use it for nicer labels.

3. Make sure CSV handling also reuses `_load_meta_sidecar`:

   - Update `_load_csv` → `_load_csv_with_meta` to call `_load_meta_sidecar` as well,
     so CSV logs benefit from metadata when available.

### 4. Optional safety: filter out unsupported JSONL shapes

If the JSONL format varies, add basic validation:

- Require at least a timestamp and one numeric channel.
- If the file does not match expectations, raise a clear `ValueError`
  that can be surfaced in the GUI (via existing error reporting).

---

## Behaviour expectations

After your changes:

- OfflineTab shows both `.csv` and `.jsonl` log files.
- Selecting and loading a JSONL log produces a valid plot similar to CSV logs.
- When `.meta.json` exists next to a log file, axis labels and inferred sensor type
  become more accurate and robust.
- Existing CSV workflows continue to work unchanged (or improved by metadata).

---

## Constraints & style

- Use only the existing dependencies (probably `pandas`, `numpy`, `json`).
- Be defensive against malformed JSONL lines (skip empty lines, report parse errors cleanly).
- Keep changes local to OfflineTab and plotter; do not change the streaming path.
