# 🛠️ Extension Fixer

<p align="center">
  <strong>A safe, lightweight desktop tool for detecting and repairing incorrect file extensions using binary magic numbers.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/GUI-Tkinter-4A90A4">
  <img src="https://img.shields.io/badge/Dependencies-None-2E8B57">
  <img src="https://img.shields.io/badge/Scanner-Threaded-success">
  <img src="https://img.shields.io/badge/Results-Live%20Updates-blue">
  <img src="https://img.shields.io/badge/Repair-Safe%20Rename-orange">
</p>

---

## ✨ Overview

Files can lose their correct extensions because of accidental renaming, failed transfers, or software issues.

A file named:

```
photo.tmp
```

may actually be:

```
photo.png
```

Extension Fixer identifies the real file type by analyzing binary signatures (**magic numbers**) instead of trusting the filename.

It then allows you to safely repair the filename extension while keeping the original file content untouched.

---

# 🚀 Highlights

| | Feature |
|-|-|
| 🔍 | Magic-number based file detection |
| ⚡ | Background threaded scanning |
| 📋 | Live scan result updates |
| ☑️ | Stable checkbox selection |
| 👀 | Preview before repair |
| 🛡️ | Backup and undo support |
| 📄 | CSV reporting |
| 🖥️ | DPI-aware interface |
| 📦 | No external dependencies |

---

# 🔄 How It Works

```
Select Folder
      │
      ▼
Scan Files
      │
      ▼
Read Magic Number
(first 16 bytes)
      │
      ▼
Compare Extension
      │
      ▼
Review Results
      │
      ▼
Select Files
      │
      ▼
Preview Repair
      │
      ▼
Rename Safely
```

---

# ⭐ Key Features

## ⚡ Responsive Large Folder Scanning

Extension Fixer uses a background worker thread to keep the interface responsive.

Benefits:

- Scan large folders without freezing the UI
- View results while scanning continues
- Stop and restart scans safely
- Incrementally update results

---

## ☑️ Reliable File Selection

The result table uses file-path based selection tracking.

This prevents common issues:

✅ Selection lost after refresh  
✅ Wrong files selected after sorting/filtering  
✅ Long-list selection instability  

Selecting files only updates the affected row instead of rebuilding the entire table.

---

## 🛡️ Safe Repair Workflow

Repairs are designed to minimize risk:

- File contents are never modified
- Only filenames are changed
- Conflicts are checked before renaming
- Optional backups are available
- Undo history is recorded

---

# 📸 Interface

Main workflow:

```
┌──────────────────────────────┐
│ Folder Selection              │
│ [Select Folder] [Scan Files]  │
└──────────────────────────────┘

┌──────────────────────────────┐
│ Scan Results                  │
│ ☑ File   Current   Detected   │
│                              │
└──────────────────────────────┘

┌──────────────┐ ┌────────────┐
│ Operation Log│ │  Actions   │
│              │ │ Preview    │
│              │ │ Repair     │
│              │ │ Undo       │
└──────────────┘ └────────────┘
```

---

# 📦 Installation

## Requirements

- Python 3.9+
- Tkinter enabled

## Run

```bash
python main.py
```

No package installation required.

---

# 📝 Workflow

1. Select a target folder.
2. Configure scan settings.
3. Click **Scan Files**.
4. Review detected problems.
5. Select files using checkboxes.
6. Click **Preview Repairs**.
7. Confirm **Execute Repair**.
8. Restore changes with **Undo Recorded Changes** if required.

---

# ⚙️ Configuration

| File | Purpose |
|-|-|
| `settings.json` | Application preferences |
| `custom_magic_formats.json` | File signature definitions |
| `operation_log.json` | Undo history |

---

# 📊 CSV Reports

Reports are exported as:

```
extensionfixer_report.csv
```

Includes:

- File path
- Current extension
- Detected extension
- File size
- Status
- Repair information

---

# 🔧 Performance Design

Large scans are optimized through:

- Threaded scanning
- Queue-based UI communication
- Streaming directory traversal
- Incremental table updates
- Reduced unnecessary refresh operations

---

# 📁 Project Structure

```text
.
├── main.py
├── settings.json
├── custom_magic_formats.json
├── operation_log.json
└── README.md
```

---

# 🧪 Development Guidelines

When contributing:

- Keep the project dependency-free
- Preserve rename-only repairs
- Never modify file contents
- Maintain threaded scanning behavior
- Keep selection tracking path-based
- Test scan, stop, restart, repair, undo, and export workflows

---

# 📜 License

MIT
