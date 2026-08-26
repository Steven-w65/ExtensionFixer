<p align="center">
  <img src="app.ico" width="96" height="96" alt="Extension Fixer icon">
</p>

<h1 align="center">Extension Fixer</h1>

<p align="center">
  <strong>Repair misleading file extensions using what each file actually contains.</strong>
</p>

<p align="center">
  A responsive, safety-focused PyQt6 desktop tool that identifies binary formats
  from magic numbers and renames files without changing their content.
</p>

<p align="center">
  <a href="https://github.com/Steven-w65/ExtensionFixer/actions/workflows/build.yml"><img alt="Tests" src="https://github.com/Steven-w65/ExtensionFixer/actions/workflows/build.yml/badge.svg"></a>
  <img alt="Version 2.0.0" src="https://img.shields.io/badge/version-2.0.0-2563EB">
  <img alt="Python 3.10 or newer" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="PyQt6" src="https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white">
  <img alt="Windows x64 build" src="https://img.shields.io/badge/build-Windows%20x64-0078D4?logo=windows11&logoColor=white">
  <a href="LICENSE"><img alt="GPL version 3" src="https://img.shields.io/badge/license-GPL--3.0--only-5C2D91"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#supported-formats">Formats</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#safety-by-design">Safety</a> ·
  <a href="#development">Development</a>
</p>

---

## Why Extension Fixer?

A filename can lie. A file called `holiday-photo.bin` may still contain a valid
PNG image, and `archive.pdf` may really be a ZIP archive. Extension Fixer reads
only the first **16 bytes**, compares them with configurable binary signatures,
and shows the extension the file should have.

```text
holiday-photo.bin  →  89 50 4E 47 0D 0A 1A 0A  →  holiday-photo.png
```

> [!IMPORTANT]
> Extension Fixer changes file names only. It never rewrites file contents.
> Preview, filtering, scanning, and CSV export are read-only operations.

## At a glance

| | Capability | What it provides |
|---:|---|---|
| ⚡ | **Responsive scanning** | Directory and file I/O run in a worker thread while results appear in live UI batches. |
| 🔎 | **Content-based detection** | File formats are identified from configurable signatures, not trusted filename extensions. |
| ☑️ | **Precise selection** | Repair individual files or check all currently visible repair candidates. |
| 🛡️ | **Safe renaming** | Existing paths are never overwritten; conflicts follow one of three explicit strategies. |
| 📦 | **Optional backups** | Originals can be copied into timestamped backup directories before their names change. |
| ↩️ | **Previewable undo** | Inspect and restore the latest batch or all recorded operations. |
| 📊 | **CSV reporting** | Export the complete scan result with paths, sizes, extensions, status, and errors. |
| ⚙️ | **Editable configuration** | General settings and every supported magic-number rule remain external and portable. |

## How it works

```mermaid
flowchart LR
    A[Select a folder] --> B[Scan in background]
    B --> C[Read first 16 bytes]
    C --> D[Match configured signatures]
    D --> E[Review and check candidates]
    E --> F[Preview rename plan]
    F --> G[Confirm safe repair]
    G --> H[Record operation for undo]
```

Files without a matching configured signature—including ordinary text files—are
reported as unidentifiable and are never guessed from their names.

## Quick start

### Download the portable Windows build

1. Open [**Actions → Build Windows application**](https://github.com/Steven-w65/ExtensionFixer/actions/workflows/build-windows.yml).
2. Select **Run workflow**.
3. When the run completes, download the `ExtensionFixer-Windows-x64` artifact.
4. Extract `ExtensionFixer-Windows-x64.zip` and run `ExtensionFixer.exe`.

No separate Python installation is required for the packaged application.

```text
ExtensionFixer-Windows-x64.zip
├── ExtensionFixer.exe
├── _internal/
├── settings.json
├── custom_magic_formats.json
├── app.ico
├── README.md
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── SOURCE_COMMIT.txt
├── licenses/
└── source/
```

> [!NOTE]
> Keep `_internal/`, `settings.json`, and `custom_magic_formats.json` beside
> `ExtensionFixer.exe`. Extract the complete ZIP before running the app. The
> portable folder must be writable if you want settings and undo history to be
> saved.

The manual build runs the regression suite, creates a Windows x64 one-folder
application, performs an offscreen startup smoke test, and uploads one artifact.
It does not create or modify a GitHub Release. Artifacts are retained for 14
days.

### Run from source

Requirements:

- Python 3.10 or newer
- Windows, Linux, or macOS with a PyQt6-supported desktop environment

```powershell
git clone https://github.com/Steven-w65/ExtensionFixer.git
cd ExtensionFixer
python -m pip install -r requirements.txt
python main.py
```

## Using the application

1. Choose the folder that contains the files you want to inspect.
2. Adjust recursive scanning, repair-only filtering, and backup behavior.
3. Select **Scan Files**. The button becomes **Stop** until the worker exits.
4. Review the detected extensions and status of each result.
5. Check the files you want to repair.
6. Use **Preview Repairs** to inspect the planned destination names.
7. Select **Execute Repair** and approve the confirmation dialog.
8. Use **Undo Recorded Changes** if you need to restore previous names.

The list is intentionally not rescanned after repair or undo unless the matching
automatic-scan option is enabled in Settings.

## Supported formats

The included configuration provides 22 signatures covering 19 extensions.

| Category | Extensions |
|---|---|
| Images | `png`, `jpg`, `gif`, `bmp`, `ico`, `webp` |
| Documents and archives | `pdf`, `zip`, `rar`, `7z`, `gz` |
| Audio and video | `mp3` (ID3), `flac`, `wav`, `avi`, `mp4` |
| System and design | `exe`, `psd` |

Detection rules are loaded from `custom_magic_formats.json`; the program has no
hidden hard-coded format list. Rules can be added, edited, or removed through
**Settings → File Formats**.

## Configuration

### Application settings

All software preferences live in `settings.json`.

| Setting | Default | Purpose |
|---|---:|---|
| `recursive_scan` | `true` | Include files in subdirectories. |
| `show_only_repair_items` | `false` | Hide normal and unidentifiable results. |
| `enable_backup` | `true` | Back up originals before renaming. |
| `automatic_scan_after_repair` | `false` | Refresh the list after a successful repair. |
| `automatic_scan_after_undo` | `false` | Refresh the list after undo. |
| `duplicate_strategy` | `1` | Choose how destination-name conflicts are handled. |
| `max_size_mb` | `1024` | Skip files larger than this value; `0` disables the limit. |
| `suffix_blacklist` | `.exe, .dll` | Skip files whose current suffix is blacklisted. |

Duplicate strategies use compact numeric values:

| Value | Strategy | Behavior |
|---:|---|---|
| `1` | Auto append serial number | Tries names such as `photo_1.png`, `photo_2.png`, and so on. |
| `2` | Skip when duplicate exists | Leaves only the conflicting file unchanged. |
| `3` | Safe mode | Cancels the operation if any planned destination already exists. |

The Settings window validates and saves these values. Invalid configuration is
rejected without replacing the last valid settings.

### Custom magic-number rules

A rule may contain one signature:

```json
{
  "extension": "png",
  "offset": 0,
  "signature_hex": "89504E470D0A1A0A"
}
```

Formats such as WebP, AVI, and WAV can require multiple signature fragments:

```json
{
  "extension": "webp",
  "signatures": [
    {"offset": 0, "signature_hex": "52494646"},
    {"offset": 8, "signature_hex": "57454250"}
  ]
}
```

Every offset and signature must fit entirely within bytes **0–15**. Hex strings
must contain complete byte pairs. When several rules could match, their order in
the configuration determines which rule is considered first.

## Safety by design

Extension Fixer treats every rename as a recoverable operation:

- Reads at most 16 bytes for format detection, regardless of total file size.
- Rechecks the magic number and current blacklist immediately before renaming.
- Refuses symbolic-link files and validates resolved parent directories.
- Handles Windows long paths and 8.3 short-path aliases without weakening root
  containment checks.
- Never replaces an existing file, directory, or broken link.
- Completes an enabled backup before the corresponding rename begins.
- Writes operation history atomically before changing the filename.
- Records file size and scan root for safer undo validation.
- Blocks undo when a path is malformed, missing, linked outside the scan root,
  conflicting, or unexpectedly changed.
- Prevents new scans and file operations until the active worker has terminated.
- Contains individual file errors so one inaccessible file cannot crash a scan.

Rename history is stored in `operation_log.json` beside the application. Undo
offers a preview before restoring either the latest batch or every recorded
change.

## Performance model

- Scanning runs outside the Qt GUI thread.
- Worker-to-GUI communication uses queued Qt signals.
- Results are inserted incrementally in batches rather than rebuilding the
  complete table.
- Selection counts and repair lookups use indexed sets for large lists.
- Cancellation is cooperative and waits for confirmed worker shutdown.
- Only file metadata and the first 16 bytes are read; large-file content is not
  loaded into memory.

## Development

### Run the tests

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -v
python -m compileall -q main.py extension_fixer tests
python -m pip check
```

The test suite covers configuration validation, all included signatures,
streaming scans, cancellation, Windows path aliases, blacklist and size limits,
large-list model behavior, checkbox input, conflict strategies, backups, repair
integrity checks, protected operation logs, latest/all undo, CSV export, worker
shutdown, and the complete main-window lifecycle.

The regular [**Test ExtensionFixer**](https://github.com/Steven-w65/ExtensionFixer/actions/workflows/build.yml)
workflow runs automatically on pushes and pull requests. It tests the source but
does not build or publish an executable.

### Project layout

```text
ExtensionFixer/
├── main.py                       Application entry point
├── extension_fixer/
│   ├── main_window.py            Main UI and operation coordination
│   ├── dialogs.py                Settings and undo-preview dialogs
│   ├── models.py                 Result model, filters, and checkboxes
│   ├── styles.py                 Responsive visual styling
│   ├── workers.py                Scan and file-operation workers
│   └── core/
│       ├── detector.py           Magic-number rule loading and detection
│       ├── scanner.py            Streaming directory scanner
│       ├── operations.py         Backup, rename, history, and undo
│       ├── reporting.py          CSV report export
│       └── settings.py           Settings loading and validation
├── tests/                        Automated regression suite
├── legacy/                       Archived Tkinter edition
├── settings.json                 Portable application settings
├── custom_magic_formats.json     Editable signature database
├── requirements.txt              Runtime dependency pins
└── requirements-build.txt        Windows packaging dependency pins
```

## Legacy Tkinter edition

The previous standard-library Tkinter application is preserved in
[`legacy/`](legacy/README.md). It has its own icon, settings, format rules, undo
history, and MIT license, so it can run independently without affecting version
2.0.

## Limitations

- Text formats and binaries without a configured signature cannot be identified.
- A 16-byte signature window intentionally favors fast, predictable detection
  over deep file parsing.
- Magic numbers identify a container or family, not necessarily every codec or
  subtype stored inside it.
- Renaming a file does not repair corrupt binary content.

## License

Extension Fixer 2.0 and repository files outside `legacy/` are distributed under
the **GNU General Public License version 3 only** (`GPL-3.0-only`). See
[`LICENSE`](LICENSE).

The archived Tkinter edition remains under the MIT License. See
[`legacy/LICENSE`](legacy/LICENSE).

PyQt6 is GPLv3 software, the pinned Qt runtime is LGPLv3, and PyQt6-sip is
BSD-2-Clause. Complete attribution and bundled license information are available
in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and [`licenses/`](licenses/).

---

<p align="center">
  <strong>Inspect first. Preview every change. Rename safely.</strong>
</p>
