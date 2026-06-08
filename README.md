# 💊 Taiwan-Drug-Package-Insert-Crawler (台灣西藥電子仿單即時查詢系統)

A lightweight, robust Command-Line Interface (CLI) tool designed for pharmaceutical and healthcare professionals in Taiwan to look up up-to-date drug information and packaging inserts efficiently. 

By bridging **Taiwan TFDA open data** with **dynamic text scraping**, this tool eliminates the need for entering precise license numbers, allowing for case-insensitive, partial keyword searches on English drug brand names.

---

## 🚀 Key Features

- **Dynamic HTML Parsing**: Scrapes and extracts structural data from TFDA's drug information systems, neatly segmenting medical package insert sections (e.g., Indications, Dosage, Contraindications) into readable terminal text while flushing out redundant HTML tag spaces.
- **Pure Text CLI Layout**: Optimized for high-speed administrative use, displaying pure clinical data without any dynamic front-end layout distractions.
- **Fault-Tolerant Input Routing**: Features a dynamic routing mechanism that automatically auto-completes unique queries, provides multi-choice menus for ambiguous search terms, and safely traps empty fields to prevent script crashes.

---

## ⚡ Data Architecture & Performance Optimizations

To overcome the common limitations of querying unstable government nodes directly (such as severe rate-limiting, layout updates, and large compressed `.zip` downloads), this project implements a highly optimized **Mirror Cache Workflow**:

1. **0.05s Instant Boot (Lazy Loading)**: On startup, the system opens the local data dictionary (`39_5.json`) instantly. The local search engine runs completely offline with **zero loading latency**, avoiding any API handshakes during user queries.
2. **Silent Background Synchronization**: To keep the data fresh without penalizing the user's workflow, the program automatically spawns a silent data sync thread **only when the user gracefully exits the program (by pressing Enter on an empty query)**. 
3. **Google Drive API Mirror**: It checks and mirrors the latest drug registry data from a pre-configured Google Drive cloud endpoint, overwriting the local JSON cache for the next seamless launch. It also gracefully falls back to the previous local backup if network connectivity is compromised.

---

## 🛠️ Tech Stack & Prerequisites

- **Language**: Python 3.x
- **Core Dependencies**: 
  - `BeautifulSoup4` (HTML parsing and DOM traversal)
  - `json`, `urllib` (Standard libraries for cloud fetching and dictionary storage)

To get started, clone the repository and install the text-parsing library via pip:

```bash
pip install beautifulsoup4