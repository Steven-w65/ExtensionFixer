# Suffix Fixer

<p align="center">
  <strong>A safe, local Tkinter utility for repairing incorrect file extensions from binary magic numbers.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-Standard%20Library-3776AB?logo=python&logoColor=white" alt="Python standard library only">
  <img src="https://img.shields.io/badge/GUI-Tkinter-4A90A4" alt="Tkinter GUI">
  <img src="https://img.shields.io/badge/Dependencies-None-2E8B57" alt="No dependencies">
  <img src="https://img.shields.io/badge/File%20Content-Never%20Modified-C75B4A" alt="File contents are never modified">
</p>

---

## What it does

Files sometimes end up with the wrong extension: an image may become `photo.tmp`, a PDF may become `report.bin`, or an archive may lose its suffix entirely. This application identifies supported binary formats by examining their **magic numbers**—the first 16 bytes of each file—and proposes the correct extension.

It changes **only the filename**. File content is never edited, converted, or rewritten by the repair workflow.

> Text-based files such as `.txt`, `.csv`, `.json`, `.py`, and `.html` do not have dependable binary magic numbers, so they are intentionally reported as **Unidentifiable**.

## Highlights

| Capability | Details |
|---|---|
| Magic-number detection | Reads only the first 16 bytes of each file. |
| Fully configurable formats | All signatures live in `custom_magic_formats.json`; no formats are hard-coded in Python. |
| Safe repair workflow | Preview before rename, confirmation before repair, conflict protection, optional backups, and undo logging. |
| Batch undo | Undo the latest repair batch or preview and restore all recorded batches. |
| Large-folder friendly | Uses streamed `os.scandir()` traversal, chunked scanning, and incremental table rendering. |
| Responsive controls | The Scan button becomes **Stop Scan** during scanning; partial results are retained safely. |
| High-resolution UI | Responsive sizing, larger typography, and scaled table rows for high-resolution/4K displays. |
| Reports | Export all scan results to CSV. |
| No dependencies | Uses only Python's standard library. |

---

## Quick start

### Requirements

- Python 3.9 or newer
- Tkinter enabled in the Python installation

### Run

```bash
python main.py
```

No package installation is required.

### Typical workflow

1. Click **Select Folder** and choose the folder to inspect.
2. Open **Settings…** to configure scan and protection options.
3. Click **Scan Files**.
4. Review rows marked **Repair required**.
5. Optionally select only the rows you want to process.
6. Click **Preview Repairs** to inspect proposed target names.
7. Click **Execute Repair** and confirm the operation.
8. If needed, click **Undo Recorded Changes** to preview and restore the latest batch, or choose **Preview All Recorded**.

---

## Interface overview

| Area | Purpose |
|---|---|
| Folder selection | Enter or select the target folder, open Settings, begin or stop scanning. |
| Scan results | Shows relative path, current extension, detected extension, and status. Supports multi-selection. |
| Operation log | Displays scan notices, errors, repairs, backups, and undo activity. |
| Actions | Export CSV, preview repairs, execute repairs, and open undo preview. |
| Settings window | Stores scan behavior, duplicate strategy, backup preference, size limit, blacklist, and access to format definitions. |

### Status meanings

| Status | Meaning |
|---|---|
| `Repair required` | A supported magic number was detected and the filename suffix differs. |
| `Normal: extension matches` | Current suffix already matches the detected format. |
| `Unidentifiable: no supported magic number` | No configured binary signature matched. |
| `Skipped: blacklisted extension` | The current suffix matches the blacklist. |
| `Skipped: exceeds size limit` | File exceeds the configured scan size threshold. |
| `Skipped: symbolic link` | Symbolic links are intentionally not processed. |
| `Error: ...` | The file could not be read, backed up, or renamed safely. |

---

## Supported formats

All built-in defaults are defined in [`custom_magic_formats.json`](custom_magic_formats.json).

| Category | Extensions |
|---|---|
| Images | `png`, `jpg`, `gif`, `bmp`, `webp`, `ico`, `psd` |
| Archives | `zip`, `rar`, `7z` |
| Documents | `pdf` |
| Executables | `exe` |
| Video | `mp4`, `avi` |
| Audio | `wav` |

### Important format limitations

Magic-number identification is intentionally conservative but some container and executable signatures are shared by related formats:

- `MZ` identifies PE-family files, which can include executable and DLL-style binaries.
- `ftyp` identifies ISO Base Media containers, which can include MP4-related formats.

Always use **Preview Repairs** before executing changes when format precision matters.

---

## Configuration

The application keeps formats and software preferences separate.

| File | Purpose |
|---|---|
| [`settings.json`](settings.json) | Application and scan preferences. |
| [`custom_magic_formats.json`](custom_magic_formats.json) | Format names and magic-number signatures. |
| `operation_log.json` | Generated undo records for pending repair batches. |

### Software settings

Example [`settings.json`](settings.json):

```json
{
  "last_folder": "",
  "recursive_scan": true,
  "show_only_repair_items": false,
  "enable_backup": true,
  "duplicate_strategy": 1,
  "max_size_mb": "1024",
  "suffix_blacklist": ".exe, .dll",
  "window_width": 1180,
  "window_height": 780
}
```

#### Duplicate strategy codes

| Value | Strategy | Behavior |
|---:|---|---|
| `1` | Auto append serial number | Uses names such as `image_1.png` when the preferred name exists. |
| `2` | Skip when duplicate name exists | Leaves only conflicting files unchanged. |
| `3` | Safe mode: forbid overwriting | Cancels the full repair operation when any conflict is found. |

### Blacklist

The suffix blacklist is comma-separated and case-insensitive:

```json
"suffix_blacklist": ".exe, .dll, .sys"
```

The leading dot is optional in the Settings window. The blacklist compares only the final suffix; it does not support wildcard patterns or compound suffix matching such as `.tar.gz`.

### Add or edit file formats

Open **Settings… → Configure Formats…** or edit [`custom_magic_formats.json`](custom_magic_formats.json) directly.

#### One signature

```json
{
  "extension": "psd",
  "offset": 0,
  "signature_hex": "38425053"
}
```

#### Multiple required signatures

Use `signatures` when more than one condition must match, such as RIFF plus WEBP:

```json
{
  "extension": "webp",
  "signatures": [
    { "offset": 0, "signature_hex": "52494646" },
    { "offset": 8, "signature_hex": "57454250" }
  ]
}
```

Rules are checked in configuration order. Each signature must fit entirely inside the first 16 bytes:

- `offset` must be from `0` through `15`.
- `signature_hex` must be valid hexadecimal.
- `offset + signature length` must not exceed `16` bytes.

Invalid changes are rejected before they can replace the active format configuration.

---

## Safety model

The tool is designed around avoiding overwrites and retaining a recovery path.

### Repair safety

- Never changes file binary content during repair.
- Checks for filename conflicts before a rename.
- Rechecks the target immediately before the rename.
- Treats broken symbolic links as occupied targets.
- Skips symbolic links rather than following or renaming them.
- Uses a secondary confirmation dialog before executing repairs.
- Catches errors per file so one problem does not abort the full scan.

### Backups

When **Back up originals before rename** is enabled, the tool writes original files under:

```text
<selected-folder>/backup/<unique-batch-folder>/
```

Backups are independent copies. They are created through a temporary file and committed only after a complete copy succeeds.

### Undo

Each successfully planned repair is stored in `operation_log.json` before the filename is changed.

- **Undo Recorded Changes** previews the latest repair batch first.
- **Preview All Recorded** shows every pending batch.
- The tool rechecks each item immediately before restore.
- Existing original names are never overwritten.
- Blocked entries remain available in the log for later retry.
- Corrupt undo logs block repair actions instead of silently discarding rollback history.

> Undo restores filenames only. It does not overwrite current file content with the backup copy.

---

## Performance notes

For large folders, the application:

- Streams folder entries with `os.scandir()`.
- Scans in small Tkinter event-loop chunks.
- Renders result rows in batches instead of locking the interface while building a large table.
- Lets you stop an active scan without losing results already gathered.
- Excludes the top-level `backup` directory from recursive scans.

The size threshold is a scan-time protection mechanism. A value of `0` means unlimited.

---

## CSV report

Use **Export CSV Report** to write all current scan results, including hidden rows when the repair-only filter is active.

The report includes:

- Relative and full paths
- File name and current extension
- Detected extension
- File size
- Status and error message
- Previewed target path, when available

---

## Project structure

```text
.
├── main.py                     # Tkinter application
├── settings.json               # Software preferences
├── custom_magic_formats.json   # Magic-number format definitions
├── operation_log.json          # Pending undo records; generated/updated by the app
└── README.md
```

## Notes for contributors

- Keep the project dependency-free.
- Use only Python standard-library modules.
- Do not expand magic-number reads beyond the first 16 bytes.
- Preserve the rule that repairs rename files only and never modify their binary content.
- Test normal repair, conflicts, backup, latest-batch undo, restore-all, corruption handling, blacklist behavior, and stopped scans before changing file-operation logic.

---

## License

MIT
