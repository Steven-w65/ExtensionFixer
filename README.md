# Extension Fixer 2.0

Extension Fixer identifies a file's real format from its binary signature and
safely repairs an incorrect filename extension. Its responsive PyQt6 interface
streams scan results into the table while a worker thread handles directory and
file I/O.

## Highlights

- Reads no more than the first 16 bytes of each file.
- Scans one folder or a complete subdirectory tree without following links.
- Shows results continuously in efficient UI batches.
- Stops cooperatively and waits for confirmed worker termination.
- Filters repair candidates and supports reliable per-file or visible-row checks.
- Offers preview and confirmed repair workflows.
- Never overwrites an existing target name.
- Supports optional timestamped backups and three duplicate-name strategies.
- Exports complete scan results to CSV.
- Previews and restores either the latest rename batch or all recorded changes.
- Stores all application preferences in `settings.json` and all detection rules
  in `custom_magic_formats.json`.

## Configured formats

The included configuration recognizes PNG, JPEG, GIF, BMP, ICO, WebP, ZIP, PDF,
RAR, 7-Zip, Windows executables, MP4, AVI, WAV, PSD, GZip, ID3-tagged MP3, and
FLAC files. Formats can be added, changed, or removed in **Settings → File
Formats**. Every signature and offset must fit within bytes 0–15.

Text files and any binary format without a configured matching signature are
reported as unidentifiable.

## Run from source

Python 3.10 or newer is required.

```powershell
python -m pip install -r requirements.txt
python main.py
```

This is a portable source layout. Keep `app.ico`, `settings.json`, and
`custom_magic_formats.json` beside `main.py`. Runtime settings and
`operation_log.json` are stored in the same folder.

## Legacy Tkinter version

The previous standard-library Tkinter application is preserved in
[`legacy/`](legacy/README.md). It has its own settings, format configuration,
icon, and undo log, so it can be run independently without affecting version
2.0.

## Test

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -v
python -m compileall -q main.py extension_fixer tests
python -m pip check
```

The suite covers configuration parsing, every included signature, streaming
scans, blacklist and size limits, cancellation, large-list model behavior,
checkbox input, duplicate strategies, backups, repair integrity rechecks,
protected operation logs, latest/all undo, CSV export, Qt worker shutdown, and
the complete main-window lifecycle.

## Build the Windows package

Open **Actions → Build Windows application → Run workflow** in the GitHub
repository. The manual workflow tests the checked-out commit, builds the x64
one-folder application, runs a startup smoke test, and uploads
`ExtensionFixer-Windows-x64.zip` together with its SHA-256 checksum. The
artifact is retained for 14 days. The workflow does not create a GitHub Release.

## Safety model

- Scanning, filtering, preview, and export do not modify scanned files.
- Repairs change file names only; binary content is never rewritten.
- A file's signature and current blacklist are checked again immediately before
  repair.
- Backups complete before their corresponding rename.
- Existing paths are never replaced, including broken links.
- Operation history is written atomically before renaming so interrupted work
  remains recoverable.
- Undo blocks malformed paths, linked paths, conflicts, missing files, and files
  whose size changed after repair.
- New scans and operations remain locked until the active worker thread exits.

## License

Extension Fixer 2.0 and all repository files outside `legacy/` are licensed
under the **GNU General Public License version 3 only** (`GPL-3.0-only`). See
[`LICENSE`](LICENSE).

The archived Tkinter application in `legacy/` remains available under the MIT
License. See [`legacy/LICENSE`](legacy/LICENSE).

PyQt6 is GPLv3 software, the Qt runtime installed by the pinned PyQt6 wheel is
LGPLv3, and PyQt6-sip is BSD-2-Clause. Copyright and license details are listed
in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and [`licenses/`](licenses/).

The regular GitHub workflow tests source code without publishing a frozen
binary. The separate `build-windows.yml` workflow is manual-only and creates a
one-folder Windows x64 ZIP plus a SHA-256 checksum. Its package includes the
runtime configuration, applicable license texts, application source, and a
source-commit record. It uploads an Actions artifact but does not create or
modify a GitHub Release.
