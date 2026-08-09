# 💊 Taiwan Drug Package Insert & NHI Reimbursement Lookup System
### 台灣西藥健保藥品與電子仿單即時查詢系統 (Streamlit Web App)

A modern, high-performance Web application designed for pharmacists, healthcare professionals, and regulatory personnel in Taiwan to search, cross-reference, and analyze drug package inserts, ingredients, ATC codes, and National Health Insurance (NHI) reimbursement prices in real time.

---

## 🚀 Key Features

* **Modern Streamlit Web UI**: Upgraded from legacy CLI to an intuitive, responsive Web interface built with Streamlit for enhanced user experience.
* **Dual-Database Hash Indexing**: Integrates TFDA Open Data (`39_5.json`) and NHI Drug Registry (`A21030000I-E41001-001.csv`) into memory using fast hash maps for 0.01s lightning-speed searches.
* **Multi-Target & Ingredient-Specific Filtering**: Flexible search scope configuration allowing users to toggle between **Ingredient-Only Search** and **Global Multi-Field Search** (Brand Name, License ID, ATC Code, Indications).
* **Real-Time TFDA Package Insert Web Scraper**: Dynamically fetches online clinical package inserts (Indications, Dosage & Administration) directly from TFDA MCP systems upon request.
* **Dual-Track Offline Fallback Protection**: Automatically falls back to local TFDA JSON indication data if remote government servers experience timeouts or rate-limiting.
* **Direct Source Web Navigation**: Includes convenient deep-link buttons (`🌐 前往食藥署仿單詳細網頁`) for quick access to official TFDA package insert web pages.

---

## ⚡ Data Architecture & Cross-Matching

| Data Field | Source Database | Matching Mechanism |
| :--- | :--- | :--- |
| **Brand Name (ZH/EN)** | `39_5.json` (TFDA) | Direct Field Mapping |
| **License ID** | `39_5.json` (TFDA) | Digit Normalization |
| **Ingredient Name** | `A21030000I-E41001-001.csv` (NHI) | Dual-Key Hash Indexing (License ID / English Name) |
| **ATC Code & Price** | `A21030000I-E41001-001.csv` (NHI) | Normalized Key Lookup |
| **Indications & Dosage**| Real-Time Web Scraping / Offline Backup | Dynamic HTML Parsing + Local Fallback |

---

## 📂 Data Sources & Local Development (資料來源與本機開發)

若你想在自己的電腦本機 (Local) 運行此專案，請注意：
本專案使用之大型資料庫檔案未直接上傳至 Github（以節省空間）。

* **藥品主資料庫 (`39_5.json`)**：[點此至雲端硬碟下載](https://drive.google.com/file/d/1ip_lP0Jard142l7Si9xHvXsma2V-1QfW/view?usp=sharing)
* **健保支付價資料庫 (`A21030000I-E41001-001.csv`)**：[點此至雲端硬碟下載](https://drive.google.com/file/d/1vhIX7aKWPqz3Ty-vpYH9076cnQEINCX8/view?usp=sharing)

---

## 🌐 線上系統與資料更新說明

本系統已部署至 Streamlit Community Cloud，為邀請制。
受邀者可直接透過瀏覽器開啟使用：  
👉 **[臺灣健保藥品與電子仿單查詢系統](https://taiwan-biotech-stock-tfda-license-automation-matcher-kxpbgagmn.streamlit.app/)**

> 💡 **資料同步小撇步 (Clear Cache)**：  
> 本系統設有雲端自動同步機制，且背景資料庫會不定期更新。**為確保您使用的是最新版本的藥品與支付價資料，建議每次使用前按一下鍵盤的字母 `C` 鍵（或點擊右上角 `⋮` ➔ `Clear cache`）**，即可強制系統清除舊快取並重新載入最新的 Data Sheet！

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
