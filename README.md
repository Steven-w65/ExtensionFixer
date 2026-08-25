# Extension Fixer

<p align="center">
<strong>A safe, local desktop utility that detects and repairs incorrect file extensions using binary magic numbers.</strong>
</p>

<p align="center">
<img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white">
<img src="https://img.shields.io/badge/GUI-Tkinter-4A90A4">
<img src="https://img.shields.io/badge/Dependencies-None-2E8B57">
<img src="https://img.shields.io/badge/Scanner-Threaded-success">
<img src="https://img.shields.io/badge/Results-Live%20Updates-blue">
<img src="https://img.shields.io/badge/Repair-Safe%20Rename-orange">
<img src="https://img.shields.io/badge/File%20Content-Never%20Modified-C75B4A">
</p>

---

## Introduction

Extension Fixer identifies files using binary magic numbers instead of trusting filenames. It detects incorrect extensions and safely repairs filenames without modifying file contents.

A file named `photo.tmp` may still be a PNG image, or `document.bin` may actually be a PDF. Extension Fixer helps recover these files through content-based detection.

### Core Principles

- Detect files using binary signatures.
- Rename files only; never modify file contents.
- Keep the UI responsive during large scans.
- Require user selection before repair.
- Provide backup and undo support.

---

## Features

| Feature | Description |
|---|---|
| Magic-number detection | Reads the first 16 bytes to identify supported formats. |
| Background scanner | Uses a worker thread for large folders. |
| Live scan results | Displays results while scanning. |
| Stop and restart scanning | Safely cancel and restart scans. |
| Stable selection | Checkbox selections are tracked by file path. |
| Preview repairs | Review changes before execution. |
| Safe repair | Conflict checks, backups, and undo history. |
| CSV reports | Export to `extensionfixer_report.csv`. |
| DPI-aware UI | Supports different display scaling. |
| No dependencies | Uses Python standard library only. |

---

## Quick Start

Requirements:

- Python 3.9+
- Tkinter enabled

Run:

```bash
python main.py
```

---

## Workflow

1. Select a folder.
2. Configure settings.
3. Click **Scan Files**.
4. Review results.
5. Select files with checkboxes.
6. Click **Preview Repairs**.
7. Confirm **Execute Repair**.
8. Use undo if restoration is needed.

---

## Selection System

The result table uses file-path based selection tracking.

Benefits:

- Selecting files does not refresh the table.
- Large lists remain easy to manage.
- Selection survives table refreshes and filtering.
- Repair actions only affect selected files.

---

## Performance

Extension Fixer improves large-folder handling by:

- Running scans in a background thread.
- Using queue-based GUI updates.
- Streaming directory traversal.
- Updating results incrementally.
- Avoiding unnecessary table rebuilds.

---

## Safety

The application:

- Never modifies binary file contents.
- Only renames files during repair.
- Checks conflicts before changes.
- Supports backups.
- Records operations for undo.

---

## Configuration Files

| File | Purpose |
|---|---|
| `settings.json` | Application settings. |
| `custom_magic_formats.json` | Magic-number definitions. |
| `operation_log.json` | Undo records. |

---

## CSV Report

Default export filename:

```text
extensionfixer_report.csv
```

Contains:

- File path
- Current extension
- Detected extension
- File size
- Status
- Repair information

---

## Project Structure

```text
.
├── main.py
├── settings.json
├── custom_magic_formats.json
├── operation_log.json
└── README.md
```

---

## License

MIT
