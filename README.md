# 💊 Taiwan Drug Package Insert & NHI Reimbursement Lookup System
### 台灣西藥健保藥品與電子仿單即時查詢系統 (Streamlit Web App)

A modern, high-performance Web application designed for pharmacists, healthcare professionals, and regulatory personnel in Taiwan to search, cross-reference, and analyze drug package inserts, ingredients, ATC codes, and National Health Insurance (NHI) reimbursement prices in real time.

---

## 🚀 Key Features

* ** Modern Streamlit Web UI**: Upgraded from legacy CLI to an intuitive, responsive Web interface built with Streamlit for enhanced user experience.
* ** Dual-Database Hash Indexing**: Integrates TFDA Open Data (`39_5.json`) and NHI Drug Registry (`A21030000I-E41001-001.csv`) into memory using fast hash maps for 0.01s lightning-speed searches.
* ** Multi-Target & Ingredient-Specific Filtering**: Flexible search scope configuration allowing users to toggle between **Ingredient-Only Search** and **Global Multi-Field Search** (Brand Name, License ID, ATC Code, Indications).
* ** Real-Time TFDA Package Insert Web Scraper**: Dynamically fetches online clinical package inserts (Indications, Dosage & Administration) directly from TFDA MCP systems upon request.
* ** Dual-Track Offline Fallback Protection**: Automatically falls back to local TFDA JSON indication data if remote government servers experience timeouts or rate-limiting.
* ** Direct Source Web Navigation**: Includes convenient deep-link buttons (`🌐 前往食藥署仿單詳細網頁`) for quick access to official TFDA package insert web pages.

---

## ⚡ Data Architecture & Cross-Matching

| Data Field | Source Database | Matching Mechanism |
| :--- | :--- | :--- |
| **Brand Name (ZH/EN)** | `39_5.json` (TFDA) | Direct Field Mapping |
| **License ID** | `39_5.json` (TFDA) | Normalized Digit Normalization |
| **Ingredient Name** | `A21030000I-E41001-001.csv` (NHI) | Dual-Key Hash Indexing (License ID / English Name) |
| **ATC Code & Price** | `A21030000I-E41001-001.csv` (NHI) | Normalized Key Lookup |
| **Indications & Dosage**| Real-Time Web Scraping / Offline Backup | Dynamic HTML Parsing + Local Fallback |

---

## 🛠️ Tech Stack & Dependencies

* **Frontend & Web Framework**: [Streamlit](https://streamlit.io/)
* **Data Processing**: [Pandas](https://pandas.pydata.org/)
* **HTML Scraping & Parsing**: [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
* **Runtime**: Python 3.9+

---

## ⚙️ Installation & Local Setup

1. **Clone the Repository**:
   ```bash
   git clone [https://github.com/fover60732/Taiwan-Drug-Package-Insert-Crawler.git](https://github.com/fover60732/Taiwan-Drug-Package-Insert-Crawler.git)
   cd Taiwan-Drug-Package-Insert-Crawler