import io
import json
import os
import re
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup
import gdown
from openai import OpenAI
import pandas as pd
from playwright.sync_api import sync_playwright
import pypdf
import streamlit as st

# =====================================================================
# 1. 頁面配置
# =====================================================================
st.set_page_config(
    page_title="臺灣健保藥品與電子仿單查詢系統",
    page_icon="💊",
    layout="wide",
)

st.title("💊 臺灣健保藥品與電子仿單查詢系統")
st.caption("🔒 雲端自動同步版：雙資料庫自動下載與快取機制")

# ---------------------------------------------------------------------
# 側邊欄：OpenAI API 設定
# ---------------------------------------------------------------------
with st.sidebar:
  st.header("⚙️ AI 與系統設定")
  openai_api_key = st.text_input(
      "OpenAI API Key",
      type="password",
      value=os.getenv("OPENAI_API_KEY", ""),
      help="請輸入 sk-... 開頭的金鑰。若系統環境變數已有則會自動帶入。",
  )
  target_model = st.selectbox(
      "AI 模型選擇", ["gpt-4o", "gpt-4o-mini"], index=0
  )
  st.caption("提示：若長篇 PDF 遇 429 TPM 限制，可切換為 gpt-4o-mini。")

SERVICEURL = "https://mcp.fda.gov.tw/im_detail_1/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}

CSV_FILE = "A21030000I-E41001-001.csv"
JSON_FILE = "39_5.json"

CSV_GDRIVE_ID = "1vhIX7aKWPqz3Ty-vpYH9076cnQEINCX8"
JSON_GDRIVE_ID = "1ip_lP0Jard142l7Si9xHvXsma2V-1QfW"


def clean_lic_num(text):
  if not text or text == "無紀錄":
    return ""
  nums = re.findall(r"\d+", str(text))
  return "".join(nums) if nums else str(text).strip().upper()


def normalize_ename(name):
  if not name or name == "無紀錄":
    return ""
  clean = re.sub(r"[^A-Za-z0-9]", "", str(name)).upper()
  return clean


def render_blue_badge(text):
  if not text or text == "無紀錄":
    return "無紀錄"
  return (
      '<span style="background-color: #f0f9ff; color: #1e3a8a; border: 1px'
      " solid #e0f2fe; padding: 4px 8px; border-radius: 4px; font-weight: 500;"
      f' display: inline-block;">{text}</span>'
  )


def remove_markdown_decorations(text: str) -> str:
  """將文字中的 #、*、` 移除，轉成乾淨的公文純文字格式。"""
  if not text:
    return ""
  text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
  text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
  text = re.sub(r"\*([^*]+)\*", r"\1", text)
  text = text.replace("`", "")
  return text


# =====================================================================
# 2. 自動下載與快取載入
# =====================================================================
@st.cache_data(show_spinner=False)
def load_and_index_databases():
  if not os.path.exists(JSON_FILE):
    try:
      url = f"https://drive.google.com/uc?id={JSON_GDRIVE_ID}"
      gdown.download(url, JSON_FILE, quiet=True)
    except Exception as e:
      st.error(f"❌ 下載 JSON 失敗: {e}")

  if not os.path.exists(CSV_FILE):
    try:
      url = f"https://drive.google.com/uc?id={CSV_GDRIVE_ID}"
      gdown.download(url, CSV_FILE, quiet=True)
    except Exception as e:
      st.error(f"❌ 下載 CSV 失敗: {e}")

  json_data = []
  if os.path.exists(JSON_FILE):
    try:
      with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict):
          for key in data:
            if isinstance(data[key], list):
              json_data = data[key]
              break
        elif isinstance(data, list):
          json_data = data
    except Exception:
      pass

  lic_index = {}
  ename_index = {}

  if os.path.exists(CSV_FILE):
    df = None
    for enc in ["cp950", "big5", "utf-8"]:
      try:
        df = pd.read_csv(CSV_FILE, encoding=enc, low_memory=False)
        break
      except Exception:
        continue

    if df is not None:
      df.columns = df.columns.astype(str).str.strip()
      df = df.fillna("")

      lic_col = next(
          (
              c
              for c in ["許可證字號", "藥品代號", "字號", "證號"]
              if c in df.columns
          ),
          None,
      )
      ename_col = next(
          (
              c
              for c in ["藥品英文名稱", "藥品英文", "英文品名", "英文名稱"]
              if c in df.columns
          ),
          None,
      )
      ing_col = next(
          (
              c
              for c in ["成分", "主成分", "成分名稱", "主要成分"]
              if c in df.columns
          ),
          None,
      )
      atc_col = next(
          (
              c
              for c in ["ATC代碼", "ATC 代碼", "ATC", "ATC_CODE"]
              if c in df.columns
          ),
          None,
      )
      price_col = next(
          (
              c
              for c in ["支付價", "參考價", "健保支付價", "價格"]
              if c in df.columns
          ),
          None,
      )

      for _, row in df.iterrows():
        raw_lic = (
            str(row[lic_col]).strip() if lic_col else str(row.iloc[1]).strip()
        )
        raw_ename = str(row[ename_col]).strip() if ename_col else ""
        ing_val = str(row[ing_col]).strip() if ing_col else "無紀錄"
        atc_val = str(row[atc_col]).strip() if atc_col else "無紀錄"
        price_val = str(row[price_col]).strip() if price_col else "無紀錄"

        if price_val and price_val != "無紀錄":
          try:
            price_val = f"${float(price_val):,.2f} 元"
          except ValueError:
            pass

        record = {
            "ingredient": ing_val if ing_val else "無紀錄",
            "atc": atc_val if atc_val else "無紀錄",
            "price": price_val if price_val else "無紀錄",
        }

        c_lic = clean_lic_num(raw_lic)
        if c_lic:
          lic_index[c_lic] = record

        c_ename = normalize_ename(raw_ename)
        if c_ename:
          ename_index[c_ename] = record

  return json_data, lic_index, ename_index


with st.spinner(
    "📥 首次啟動：正在從雲端下載資料庫並建立索引 (約需 5-10 秒)..."
):
  json_database, lic_index, ename_index = load_and_index_databases()

if not json_database:
  st.error("❌ 錯誤：無法載入資料庫！")
  st.stop()


def get_field_from_dict(item, target_keys):
  if not isinstance(item, dict):
    return "無紀錄"

  for tk in target_keys:
    target_clean = (
        str(tk)
        .replace(" ", "")
        .replace("\u3000", "")
        .replace("_", "")
        .strip()
        .lower()
    )

    for k, v in item.items():
      if k is None or v is None:
        continue

      key_clean = (
          str(k)
          .replace(" ", "")
          .replace("\u3000", "")
          .replace("_", "")
          .strip()
          .lower()
      )

      if target_clean == key_clean or target_clean in key_clean:
        if isinstance(v, (str, int, float)):
          val_str = str(v).strip()
          if val_str and val_str.lower() not in ["none", "null", "nan"]:
            return val_str
        elif isinstance(v, list):
          clean_list = []
          for sub_item in v:
            if isinstance(sub_item, dict):
              clean_list.extend(
                  [str(x).strip() for x in sub_item.values() if x]
              )
            elif sub_item:
              clean_list.append(str(sub_item).strip())
          if clean_list:
            return " ; ".join(clean_list)
        elif isinstance(v, dict):
          clean_dict_vals = [str(x).strip() for x in v.values() if x]
          if clean_dict_vals:
            return " ; ".join(clean_dict_vals)

  return "無紀錄"


# =====================================================================
# 3. 直連爬蟲
# =====================================================================
@st.cache_data(show_spinner=False, ttl=7200)
def fetch_fda_online_details(address):
  if not address or address == "無紀錄":
    return None, None, "無有效許可證字號"

  url = SERVICEURL + urllib.parse.quote(str(address).strip())
  req = urllib.request.Request(url, headers=HEADERS)

  try:
    data = urllib.request.urlopen(req, timeout=3.5).read()
    soup = BeautifulSoup(data, "html.parser")

    all_portions = soup.find_all("div", class_="toggle")

    if len(all_portions) == 0:
      return None, None, "電子仿單尚未完成建置或查無資料"

    indication_content = None
    dosage_content = None

    for x in all_portions:
      title_tag = x.find("span", class_="title-name") or x.find(
          class_=re.compile(r"title", re.I)
      )
      content_tag = x.find("div", class_="inner") or x.find(
          class_=re.compile(r"inner|content", re.I)
      )

      if title_tag and content_tag:
        title_text = title_tag.text.strip()

        clean_lines = [
            line.strip()
            for line in content_tag.text.splitlines()
            if line.strip()
        ]
        clean_content = "\n".join(clean_lines)

        if "適應症" in title_text and indication_content is None:
          indication_content = clean_content

        if (
            "用法用量" in title_text
            or "用法及用量" in title_text
            or "用法" in title_text
            or "用量" in title_text
        ) and dosage_content is None:
          dosage_content = clean_content

    return indication_content, dosage_content, None

  except urllib.error.HTTPError as e:
    return None, None, f"食藥署伺服器拒絕連線，錯誤代碼：{e.code}"
  except Exception as e:
    return None, None, f"食藥署連線逾時 ({e})"


# =====================================================================
# 4. 定義各國 HTA 專屬 6 段式 AI 詳盡編譯函式 (純文字排版，去除 # 與 *)
# =====================================================================

# ----------------- 1. 加拿大 CDA-AMC 摘要函式 -----------------
def summarize_cda_report(raw_text: str, api_key: str, model_name: str):
  client = OpenAI(api_key=api_key)

  system_prompt = """你是一位任職於台灣醫藥品查驗中心 (CDE) 與健保藥品給付審查會議的資深健康科技評估 (HTA) 專責研究員。
你的任務是將加拿大 CDA-AMC 之藥品評估報告 (Reimbursement Recommendation)，轉譯為乾淨純文字之技術審查素材。

【格式禁令與原則】：
1. 【嚴禁使用 Markdown 標記符號】：絕對禁止輸出任何「#」、「##」、「###」、「**」或「`」符號！所有標題與內文均採用純文字排版，以供一鍵複製到公文 Word 檔案。
2. 【篇幅必須詳盡充分】：內容必須深入且完整，保留各項審查條件與數據，切勿只用簡短兩三句帶過。
3. 【給付條件照翻】：第 1 項給付條件依據 Recommendation 與 Table 1: Conditions for Reimbursement 進行忠實照翻，依序分為：(A) 起始治療、續用、(B) 終止治療條件、(C) 財務條件。
4. 【決策理由照翻】：第 2 項以 Rationale for the Recommendation 原文為主進行深入照翻。
5. 【相對療效指標必須完整】：清楚列出 HR、OR、95% CI 與 p-value，但不要列出各組絕對存活月份或人數等流水帳數字。
6. 語氣採用臺灣官方審查報告專用筆觸。"""

  user_prompt = f"""請詳讀以下加拿大 CDA-AMC 評估報告全文，依據下列 6 個指定段落維度，撰寫一份長篇、深入且細節極為詳盡的純文字技術審查報告（請勿使用 # 或 *）：

CDA-AMC於[報告發布年份]年[報告發布月份]月公告一份與本案相關之評估報告，摘要說明如下：

1. 給付建議 (Recommendation & Conditions for Reimbursement)
以報告中 Recommendation 與 Table 1: Conditions for Reimbursement 章節進行忠實全文照翻，詳列：
- 完整適應症及給付族群定義。
- (A) 起始治療條件：包含病患臨床特徵、疾病分期、先前治療條件限制、生物標記檢測要求。
- 續用條件：治療效益評估指標與週期。
- (B) 終止治療條件：疾病惡化、不可耐受毒性或最大用藥期限（如 2 年或直到疾病進展）之提前停藥標準。
- 處方條件：專科醫師資格或處方環境限制。
- (C) 財務條件：廠商降價要求 (Price reduction) 以符合成本效益標準之具體財務條件規範。

2. 建議/不建議給付決策的主要理由 (Rationale for the Recommendation)
以報告中 Rationale for the Recommendation 章節全文照翻為主，深入展開委員會決策邏輯：
- 臨床試驗證據是否具說服力？在延緩疾病進展與存活獲益方面的實證評價。
- 經濟評估結果：增額成本效果比 (ICER) 狀況，降價幅度要求與經濟學評估依據。

3. 參考品 (Comparators)
- 以 Clinical Expert Input 及現行臨床常規為主。
- 詳述目前加拿大省級公費醫療體系之現行常規治療方案 (Standard of Care) 為何？委員會認定何種方案為最適當之參考品（對照組）及其依據。

4. 實證考量 (Clinical Evidence & Effectiveness)
- 列出主要關鍵試驗名稱與設計（例如隨機對照試驗 Phase 3）。
- 療效數據分析：請勿列出各組絕對存活月份或人數；但必須完整列出相對療效指標（HR、95% CI、p-value 等）。
- 次族群與生物標記分析：不同亞群之療效差異與專家疑慮。
- 安全性考量：常見嚴重不良反應 (AEs)、特定關注毒性與臨床耐受性。

5. 其他臨床或實務相關考量點 (Discussion Points & Implementation Considerations)
以報告中 Discussion Points 章節為主進行詳實展開：
- 檢測方式與量能衝擊：是否需要特定伴隨診斷或生物標記檢測（如 MMR/MSI、PD-L1 等）？現行檢測方式為何？是否會大幅增加檢測人數與被診斷人數負擔？
- 給付後資料收集：給付後是否需要進一步進行資料收集（如真實世界資料 RWD、登錄系統 Registry）？若有，資料收集來源及追蹤指標為何？
- 預算衝擊 (Budget Impact Analysis) 與跨省給付實施挑戰。

6. 病人團體意見或倫理相關議題 (Patient Group Input & Ethical Considerations)
以報告中 Recommendation and Reasons 所引述之 Patient Group Input 與倫理議題為主：
- 疾病對病患與照護者日常生活的衝擊與負擔。
- 現有治療之未滿足醫療需求 (unmet medical need)。
- 病人對新治療之期望與價值（如多一項治療選擇、生活品質改善、維持日常生活能力等）。

-------------------------------------------------------
【CDA-AMC 報告全文內容】：
-------------------------------------------------------
{raw_text[:65000]}
"""

  response = client.chat.completions.create(
      model=model_name,
      messages=[
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": user_prompt},
      ],
      temperature=0.3,
      max_tokens=4000,
  )

  usage_info = response.usage
  summary_text = remove_markdown_decorations(
      response.choices[0].message.content
  )
  return summary_text, usage_info


# ----------------- 2. 澳洲 PBAC 摘要函式 -----------------
def summarize_pbac_report(raw_text: str, api_key: str, model_name: str):
  client = OpenAI(api_key=api_key)

  system_prompt = """你是一位任職於台灣醫藥品查驗中心 (CDE) 與健保藥品給付審查會議的資深健康科技評估 (HTA) 專責研究員。
你的任務是將澳洲 PBAC 之公共摘要文件 (Public Summary Document, PSD)，轉譯為乾淨純文字之技術審查素材。

【格式禁令與原則】：
1. 【嚴禁使用 Markdown 標記符號】：絕對禁止輸出任何「#」、「##」、「###」、「**」或「`」符號！所有標題與內文均採用純文字排版，以供一鍵複製到公文 Word 檔案。
2. 【篇幅必須詳盡充分】：全文深入展開，完整保留委員會各項給付限制細節與數據。
3. 【給付建議照翻】：第 1 項必須以報告中的「PBAC Outcome」章節為主進行忠實全文照翻，包含起始、續用、停用及價格/合約條件。
4. 【決策理由照翻】：第 2 項必須以「Clinical Claim」為主進行深入忠實照翻。
5. 【參考品】：第 3 項依據報告「5. Comparator」章節詳實說明。
6. 【相對療效指標必須完整】：臨床證據以「Clinical Trials」展開；不要列出各組絕對存活月份或人數，但在「Consideration of the evidence」中的「Comparative effectiveness」部分，必須清楚列出相對療效具體數字（HR, 95% CI, p-value 等）。
7. 語氣採用臺灣官方審查報告專用筆觸。"""

  safe_pbac_text = raw_text[:60000]

  user_prompt = f"""請詳讀以下澳洲 PBAC 評估報告全文 (Public Summary Document)，嚴格依據下列 6 個指定段落維度，撰寫一份長篇、深入且細節極為詳盡的純文字技術審查報告（請勿使用 # 或 *）：

PBAC於[會議年份]年[會議月份]月會議評估報告，摘要說明如下：

1. 給付建議 (PBAC Outcome)
以報告中 PBAC Outcome 章節進行忠實全文照翻，完整條列推薦決議與限制條件：
- 完整適應症及給付族群定義。
- 起始條件：疾病分期、先前治療限制、特定生物標記檢驗。
- 續用條件：治療評估週期與療效維持標準。
- 停用標準：最大療程上限、疾病惡化或不可接受之毒性停藥標準。
- 價格與財務協議：特別價格協議 (SPA) 或風險分攤協議 (RSA) 等財務條件。

2. 建議/不建議給付決策的主要理由 (Clinical Claim)
以報告中 Clinical Claim 章節全文照翻為主，深入展開決策邏輯：
- 申請廠商所宣稱之臨床定位與療效訴求（如 superiority 優越性或 non-inferiority 非劣性）。
- PBAC 委員會對該臨床主張之接受度與評語。

3. 參考品 (Comparator)
以報告第 5 節 5. Comparator 為主展開：
- 目前澳洲 PBS 現行常規治療方案為何？
- PBAC 是否認可廠商提出之對照品為適當的參考品？若有替代對照品爭議，其考量原因為何？

4. 實證考量 (Clinical Trials & Comparative Effectiveness)
- 臨床證據以 Clinical Trials 章節為主：列出關鍵試驗名稱與設計（如 Phase 3 隨機對照）。
- 請勿列出各組絕對存活月份或人數等流水帳數字。
- 相對療效指標：以 Consideration of the evidence 中有關 Comparative effectiveness 的比較為主，清楚列出相對療效指標數值（HR、95% CI、p-value 等）。
- 安全性評估：依據 Comparative Harms 說明嚴重不良事件 (AEs)、免疫相關毒性與耐受性評價。

5. 其他臨床或實務相關考量點 (Discussion Points & Implementation Considerations)
以報告中 Discussion Points / Consideration of the evidence 為主進行詳實展開：
- 檢測方式與量能衝擊：是否需要特定伴隨診斷或生物標記檢測（如 MMR/MSI、PD-L1 等）？現行檢測方式為何？是否會大幅增加檢測人數與被診斷人數負擔？
- 給付後資料收集：給付後是否需要進一步進行資料收集（如真實世界資料 RWD、登錄系統 Registry）？若有，資料收集來源及追蹤指標為何？
- 財務估計與預算衝擊 (Financial Estimates) 討論。

6. 病人團體意見或倫理相關議題 (Consumer Comments)
以報告中 Consumer Comments 章節為主展開：
- 病患與照顧者針對目標疾病日常負擔、生活品質衝擊之反饋。
- 現有治療之未滿足醫療需求 (unmet medical need)。
- 病患對於新療法的期待（如口服使用增加方便性、多一項重要治療選擇、維持生活自理能力等）。

-------------------------------------------------------
【PBAC 報告全文內容】：
-------------------------------------------------------
{safe_pbac_text}
"""

  response = client.chat.completions.create(
      model=model_name,
      messages=[
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": user_prompt},
      ],
      temperature=0.3,
      max_tokens=4000,
  )

  usage_info = response.usage
  summary_text = remove_markdown_decorations(
      response.choices[0].message.content
  )
  return summary_text, usage_info


# ----------------- 3. 英國 NICE 摘要函式 -----------------
def summarize_nice_report(raw_text: str, api_key: str, model_name: str):
  client = OpenAI(api_key=api_key)

  system_prompt = """你是一位任職於台灣醫藥品查驗中心 (CDE) 與健保藥品給付審查會議的資深健康科技評估 (HTA) 專責研究員。
你的任務是將英國 NICE Technology Appraisal (TA) 評估報告全文，轉譯為乾淨純文字之技術審查素材。

【格式禁令與原則】：
1. 【嚴禁使用 Markdown 標記符號】：絕對禁止輸出任何「#」、「##」、「###」、「**」或「`」符號！所有標題與內文均採用純文字排版，以供一鍵複製到公文 Word 檔案。
2. 【篇幅必須詳盡充分】：全文深入展開，包含各項細節與完整語境。
3. 【第 1、2 點逐條照翻】：請對照報告第 1 章 (Recommendations) 與「Why the committee made these recommendations」進行逐句忠實全文翻譯。
4. 【相對療效指標必須完整】：清楚列出 HR、95% CI 與 p-value，但不要列出各組絕對存活月份或人數等流水帳數字。
5. 語氣採用臺灣官方審查報告專用筆觸。"""

  user_prompt = f"""請詳讀以下英國 NICE 評估報告全文，依據下列 6 個指定段落維度，撰寫一份長篇、深入且細節極為詳盡的純文字技術審查報告（請勿使用 # 或 *）：

NICE於[報告發布年份]年[報告發布月份]月公告一份與本案相關之評估報告，摘要說明如下：

1. 給付建議 (Recommendations)
全文照翻 1. Recommendations 章節：
- 完整寫出核准給付之完整適應症、病患條件、疾病分期（如原發性晚期、復發性、先前治療史、生物標記條件等）。
- 完整寫出所有用藥條件規定：起始條件、續用評估方式、最長治療上限（如 2 年或疾病惡化）、提前停藥標準（如疾病進展或不可接受之毒性）。
- 商業與價格協議：廠商與 NHS 之間的商業協議 (Commercial arrangement / Patient Access Scheme, PAS) 之給付前提條款。

2. 建議/不建議給付決策的主要理由 (Why the committee made these recommendations)
全文照翻 Why the committee made these recommendations 章節，展開為完整長段落：
- 臨床證據評估：試驗展現了哪些療效？委員會如何評價其延緩疾病惡化的效果？為何委員會認為長期整體存活期 (OS) 仍具有高度不確定性？
- 經濟評估與資源配置：經濟評估模型中，增額成本效益比 (ICER) 落在何種數值區間？委員會考量了哪些未確定因素後，判定該成本效益估計值落於 NHS 資源合理使用與可接受的範圍之內？

3. 參考品 (Comparators)
- 深入說明目前英國 NHS 的現行常規臨床治療 (Standard of Care, SoC) 為何？目前臨床指引推薦哪些化療或標靶藥物？
- 委員會為何認定該方案為最適當之參考品（對照組）？在臨床實務定位上，新藥是取代現有療法還是合併使用？

4. 實證考量 (Clinical Evidence & Effectiveness)
- 主要關鍵試驗：詳細列出樞紐臨床試驗名稱（如 KEYNOTE 系列）、試驗設計（隨機對照、雙盲等）。
- 療效數據分析：請勿列出各組絕對存活月份或人數；但必須完整列出相對療效指標（HR、95% CI、p-value 等）。
- 次族群與生物標記爭議：若有分群（如 dMMR vs pMMR）或廠商進行事後合併（整體病人族群 all-comer population）之分析，詳述外部評估小組 (EAG) 與臨床專家對該分析之質疑、兩者預後差異及委員會之最終看法。
- 停藥合理性：臨床專家針對 2 年停止治療之生理機轉與臨床經驗說明。
- 安全性與耐受性：常見嚴重不良反應 (AEs)、免疫相關副作用及處置考量。

5. 其他臨床或實務相關考量點 (Economic Model & Implementation Assumptions)
- 檢測需求：是否需要特定生物標記檢測或伴隨診斷（如 MMR/MSI、PD-L1 等）？現行檢測方式普及度為何？是否會增加檢測人數與被診斷人數負擔？
- 給付後資料收集：是否需要給付後真實世界資料 (RWD) 收集或登錄系統 (Registry)？追蹤之指標與來源為何？
- 經濟模型結構與不確定性：說明存活外推曲線 (Survival extrapolation) 之選擇合理性、治療效果遞減 (Treatment waning effect) 假設等重大參數討論。

6. 病人團體意見或倫理相關議題 (Patient & Ethical Perspectives)
- 疾病對病患與照護者生活品質造成之實質衝擊，現有化療之毒性副作用與生活限制，說明未滿足醫療需求 (unmet medical need)。
- 新治療帶來之具體改變（如維持自理能力、維持工作、多一項重要治療選擇、減少疲憊等）。
- 平等性或倫理考量 (Equality considerations)。

-------------------------------------------------------
【NICE 報告全文內容】：
-------------------------------------------------------
{raw_text[:65000]}
"""

  response = client.chat.completions.create(
      model=model_name,
      messages=[
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": user_prompt},
      ],
      temperature=0.3,
      max_tokens=4000,
  )

  usage_info = response.usage
  summary_text = remove_markdown_decorations(
      response.choices[0].message.content
  )
  return summary_text, usage_info


# ----------------- 4. 蘇格蘭 SMC 摘要函式 -----------------
def summarize_smc_report(raw_text: str, api_key: str, model_name: str):
  client = OpenAI(api_key=api_key)

  system_prompt = """你是一位任職於台灣醫藥品查驗中心 (CDE) 與健保藥品給付審查會議的資深健康科技評估 (HTA) 專責研究員。
你的任務是將蘇格蘭 SMC 之藥品評估建議書 (Detailed Advice Document)，轉譯為乾淨純文字之技術審查素材。

【格式禁令與原則】：
1. 【嚴禁使用 Markdown 標記符號】：絕對禁止輸出任何「#」、「##」、「###」、「**」或「`」符號！所有標題與內文均採用純文字排版，以供一鍵複製到公文 Word 檔案。
2. 【篇幅必須詳盡充分】：內容必須深入且完整，保留各項審查條件與數據，切勿簡短概括。
3. 【第 1、2 點照翻】：第 1 點給付建議與第 2 點決策理由，必須以 SMC 報告封面方格內文字 (Front Page Advice Box) 進行忠實全文照翻。
4. 【參考品】：第 3 點以「1.3. Treatment pathway and relevant comparators」章節為主進行說明。
5. 【實證考量】：第 4 點以「4. Summary of Clinical Effectiveness Considerations」為主；不要列出臨床試驗絕對數字，但相對療效比較（HR, 95% CI, p-value）必須精準列出。
6. 【其他臨床或實務考量】：第 5 點以「Other assumptions in the economic model」為主，說明伴隨檢測、量能負擔與 RWD 資料收集。
7. 【病人團體意見】：第 6 點以「Patient and clinician engagement (PACE)」為主。
8. 語氣採用臺灣官方審查報告專用筆觸。"""

  user_prompt = f"""請詳讀以下蘇格蘭 SMC 評估報告全文，依據下列 6 個指定段落維度，撰寫一份長篇、深入且細節極為詳盡的純文字技術審查報告（請勿使用 # 或 *）：

SMC於[報告發布年份]年[報告發布月份]月公告一份與本案相關之評估報告，摘要說明如下：

1. 給付建議 (SMC Advice)
以 SMC 報告封面方格內文字 (Front page Advice box) 進行忠實全文照翻，詳列：
- 完整核准給付之適應症與限制條件。
- 給付條件包含：起始條件、續用標準、停用條件（如最大療程期或疾病惡化）。
- 價格或商業協議：是否受限於病患近用協議 (Patient Access Scheme, PAS) 折扣提供供藥。

2. 建議/不建議給付決策的主要理由 (Rationale for the Decision)
以 SMC 報告封面方格內文字 (Front page Advice box / Rationale) 進行忠實全文照翻，深入展開委員會決策邏輯：
- 臨床療效獲益評價與存活期不確定性。
- 經濟評估模型中，考量 PAS 折扣後之成本效果性 (Cost-effectiveness) 是否符合 NHS Scotland 資源合理使用標準。

3. 參考品 (Treatment pathway and relevant comparators)
以報告第 1.3 節「1.3. Treatment pathway and relevant comparators」為主：
- 目前 NHS Scotland 現行常規治療處置 (Standard of Care) 為何？
- SMC 委員會認定何種方案為最適當之參考品（對照組）及其臨床定位依據。

4. 實證考量 (Summary of Clinical Effectiveness Considerations)
以報告第 4 節「4. Summary of Clinical Effectiveness Considerations」為主深入展開：
- 列出主要關鍵樞紐臨床試驗名稱與設計（如 Phase 3 隨機對照試驗）。
- 請勿列出各組絕對存活月份或人數等流水帳數字。
- 相對療效指標：以該節中提及之相對療效指標數值為主，清楚列出主要終點（如 PFS、OS、ORR）之 HR、95% CI 與統計顯著性。
- 安全性評估：常見重要嚴重不良事件 (AEs) 與耐受性說明。

5. 其他臨床或實務相關考量點 (Other assumptions in the economic model)
以報告中「Other assumptions in the economic model」及討論為主進行展開：
- 檢測方式與量能衝擊：是否需要特定伴隨診斷或生物標記檢測（如 MMR/MSI、PD-L1 等）？現行檢測方式普及度為何？是否會大幅增加檢測人數與被診斷人數負擔？
- 給付後資料收集：給付後是否需要進一步進行資料收集（如真實世界資料 RWD、登錄系統 Registry）？若有，資料收集來源及追蹤指標為何？
- 經濟模型結構中之存活外推假設與治療效果遞減 (waning effect) 討論。

6. 病人團體意見或倫理相關議題 (Patient and clinician engagement, PACE)
以報告中「Patient and clinician engagement (PACE)」章節陳述為主：
- 病人與臨床專家所表達之未滿足醫療需求 (unmet medical need)。
- 現行治療之毒性痛苦與生活衝擊。
- 新治療帶來之實質獲益（如口服使用增加方便性、多一項重要治療選擇、維持日常生活能力與減輕照護者負擔等）。

-------------------------------------------------------
【SMC 報告全文內容】：
-------------------------------------------------------
{raw_text[:65000]}
"""

  response = client.chat.completions.create(
      model=model_name,
      messages=[
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": user_prompt},
      ],
      temperature=0.3,
      max_tokens=4000,
  )

  usage_info = response.usage
  summary_text = remove_markdown_decorations(
      response.choices[0].message.content
  )
  return summary_text, usage_info


# =====================================================================
# 5. 頁籤配置 (基本資料 / 常用連結 / 療效評估報告)
# =====================================================================
tab1, tab2, tab3 = st.tabs(
    ["📋 基本資料", "🔗 常用連結", "📑 療效評估報告（含文獻回顧摘要）"]
)

# ---------------------------------------------------------------------
# 頁籤 1：基本資料 (主查詢介面)
# ---------------------------------------------------------------------
with tab1:
  st.markdown("---")

  with st.form(key="search_form"):
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
      search_mode = st.selectbox(
          "🎯 請選擇搜尋範圍：",
          [
              "僅限成分 (Ingredient)",
              "全域搜尋 (中文/英文/字號/適應症/ATC)",
          ],
      )

    with col2:
      status_filter = st.selectbox(
          "📌 許可證狀態：",
          [
              "未註銷",
              "已註銷",
              "已廢止",
              "全部 (含已註銷/已廢止/未註銷)",
          ],
      )

    with col3:
      keyword = st.text_input(
          "🔍 請輸入搜尋關鍵字：",
          placeholder="例如：DURVALUMAB、CHLORPROMAZINE、AMITRIPTYLINE...",
      )

    submit_button = st.form_submit_button(
        label="🔍 立即查詢 (按下 Enter 即可發送)"
    )

  KEY_MAP = {
      "中文名稱": [
          "中文品名",
          "藥品中文",
          "藥品中文名稱",
          "中文藥名",
          "中文名稱",
      ],
      "英文名稱": [
          "英文品名",
          "藥品英文",
          "藥品英文名稱",
          "英文藥名",
          "英文名稱",
      ],
      "許可證字號": [
          "許可證字號",
          "字號",
          "許可證號",
          "藥品代號",
          "證號",
          "許可證",
      ],
      "適應症": ["適應症", "主要適應症", "效能"],
      "劑型": [
          "劑型",
          "劑型名稱",
          "藥品劑型",
          "劑型代碼",
          "Dosage Form",
          "DOSAGE_FORM",
      ],
      "申請商": [
          "申請商名稱",
          "申請商",
          "藥商名稱",
          "藥商",
          "申請人",
          "申請人名稱",
          "許可證持有者",
      ],
      "註銷狀態": [
          "註銷狀態",
          "註銷狀態描述",
          "註銷註記",
          "許可證狀態",
          "註銷日期",
      ],
  }

  if submit_button or keyword:
    kw_clean = keyword.strip()
    if kw_clean:
      kw_lower = kw_clean.lower()
      matched_results = []
      seen_lics = set()

      for item in json_database:
        lic_num = get_field_from_dict(item, KEY_MAP["許可證字號"])
        clean_lic = clean_lic_num(lic_num)

        if clean_lic and clean_lic in seen_lics:
          continue

        cancel_status = get_field_from_dict(item, KEY_MAP["註銷狀態"])
        is_empty_status = (
            cancel_status == "無紀錄" or cancel_status.strip() == ""
        )

        if status_filter == "未註銷":
          if not is_empty_status:
            continue
        elif status_filter == "已註銷":
          if "註銷" not in cancel_status:
            continue
        elif status_filter == "已廢止":
          if "廢止" not in cancel_status:
            continue

        c_name = get_field_from_dict(item, KEY_MAP["中文名稱"])
        e_name = get_field_from_dict(item, KEY_MAP["英文名稱"])
        local_ind = get_field_from_dict(item, KEY_MAP["適應症"])
        dosage_form = get_field_from_dict(item, KEY_MAP["劑型"])
        applicant = get_field_from_dict(item, KEY_MAP["申請商"])

        clean_en = normalize_ename(e_name)

        csv_info = {"ingredient": "無紀錄", "atc": "無紀錄", "price": "無紀錄"}
        if clean_lic in lic_index:
          csv_info = lic_index[clean_lic]
        elif clean_en in ename_index:
          csv_info = ename_index[clean_en]
        else:
          for k_en, val in ename_index.items():
            if clean_en and (clean_en in k_en or k_en in clean_en):
              csv_info = val
              break

        ingredient_from_csv = csv_info["ingredient"]
        atc_code = csv_info["atc"]
        price_val = csv_info["price"]

        is_matched = False

        if "僅限成分" in search_mode:
          if kw_lower in ingredient_from_csv.lower():
            is_matched = True
        else:
          if (
              kw_lower in c_name.lower()
              or kw_lower in e_name.lower()
              or kw_lower in lic_num.lower()
              or kw_lower in local_ind.lower()
              or kw_lower in ingredient_from_csv.lower()
              or kw_lower in atc_code.lower()
              or kw_lower in dosage_form.lower()
              or kw_lower in applicant.lower()
          ):
            is_matched = True

        if is_matched:
          display_status = (
              "未註銷 (有效)" if is_empty_status else cancel_status
          )
          matched_results.append({
              "中文名稱": c_name,
              "英文名稱": e_name,
              "許可證字號": lic_num,
              "成分": ingredient_from_csv,
              "ATC代碼": atc_code,
              "支付價": price_val,
              "本地適應症": local_ind,
              "劑型": dosage_form,
              "申請商": applicant,
              "註銷狀態": display_status,
          })
          if clean_lic:
            seen_lics.add(clean_lic)

      if not matched_results:
        st.warning(
            f"❌ 找不到符合條件（關鍵字：【{kw_clean}】/ 狀態：{status_filter}）的藥品資料！"
        )
      else:
        st.success(
            f"🎉 共找到 {len(matched_results)} 筆藥品資料（篩選：{status_filter}）！"
        )

        for idx, drug in enumerate(matched_results, start=1):
          c_name = drug["中文名稱"]
          e_name = drug["英文名稱"]
          lic_num = drug["許可證字號"]

          with st.expander(
              f"【{idx}】{c_name} | {e_name} (許可證: {lic_num})",
              expanded=True,
          ):
            st.markdown(f"**藥品中文名稱：** {c_name}")
            st.markdown(f"**藥品英文名稱：** {e_name}")
            st.markdown(
                f"**許可證字號：** {lic_num} （狀態：`{drug['註銷狀態']}`）"
            )
            st.markdown(f"**成分：** {drug['成分']}")
            st.markdown(f"**劑型：** {drug['劑型']}")
            st.markdown(f"**申請商：** {drug['申請商']}")
            st.markdown(f"**ATC代碼：** {drug['ATC代碼']}")
            st.markdown(f"**健保支付價：** {drug['支付價']}")

            with st.spinner("⚡ 正在對接食藥署線上系統..."):
              online_ind, online_dos, err = fetch_fda_online_details(lic_num)

              final_ind = online_ind if online_ind else drug["本地適應症"]
              if final_ind != "無紀錄":
                st.markdown(f"**適應症：** {final_ind}")
              else:
                st.markdown("**適應症：** 無紀錄")

              if online_dos:
                st.markdown(f"**用法用量：** {online_dos}")
              else:
                fallback_err = err if err else "無紀錄"
                st.markdown(f"**用法用量：** {fallback_err}")

            st.markdown(" ")
            target_fda_url = f"https://mcp.fda.gov.tw/im_detail_1/{urllib.parse.quote(lic_num)}"
            st.link_button(
                "🌐 前往食藥署仿單詳細網頁",
                target_fda_url,
                use_container_width=False,
            )

# ---------------------------------------------------------------------
# 頁籤 2：常用連結 (國際藥政、指引、資料庫與文書工具)
# ---------------------------------------------------------------------
with tab2:
  st.markdown("---")

  st.subheader("🌐 WHO ATC/DDD 分類系統")
  st.link_button(
      "🔗 WHO ATC/DDD Index 官方查詢系統",
      "https://atcddd.fhi.no/atc_ddd_index/",
  )

  st.markdown("---")

  st.subheader("📄 各國藥政主管機關 (FDA / 仿單查詢)")
  col1, col2, col3 = st.columns(3)

  with col1:
    st.link_button(
        "🇺🇸 US FDA Drugs@FDA",
        "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm",
    )
    st.link_button(
        "🇦🇺 Australia TGA (ARTG)", "https://www.tga.gov.au/resources/artg"
    )

  with col2:
    st.link_button(
        "🇪🇺 Europe EMA Medicines", "https://www.ema.europa.eu/en/medicines"
    )
    st.link_button("🇬🇧 UK MHRA Products", "https://products.mhra.gov.uk/")

  with col3:
    st.link_button(
        "🇨🇦 Health Canada Drug Product Database",
        "https://health-products.canada.ca/dpd-bdpp/",
    )

  st.markdown("---")

  # 各國 HTA 查詢 (4 國：CDA-AMC, PBAC, NICE, SMC 精準 PDF/HTML 擷取版)
  st.subheader("🏛️ 各國 HTA 查詢")

  hta_col1, hta_col2, hta_col3, hta_col4 = st.columns(4)

  with hta_col1:
    st.link_button(
        "CA CDA-AMC Reports",
        "https://www.cda-amc.ca/find-reports",
        use_container_width=True,
    )

  with hta_col2:
    st.link_button(
        "AU PBAC Public Summary Documents",
        "https://www.pbs.gov.au/industry/pbac/psd",
        use_container_width=True,
    )

  with hta_col3:
    st.link_button(
        "GB NICE Guidelines & Guidance",
        "https://www.nice.org.uk/guidance",
        use_container_width=True,
    )

  with hta_col4:
    st.link_button(
        "SCO SMC Medicines Advice",
        "https://scottishmedicines.org.uk/medicines-advice/",
        use_container_width=True,
    )

  st.markdown(" ")
  with st.expander(
      "📋 各國 HTA 引用資訊自動擷取工具 (Title / Published Date / URL)",
      expanded=True,
  ):
    st.caption(
        "點擊下方機構按鈕啟動 Chrome。在跳出視窗中挑選報告（支援在原分頁點擊、新分頁開啟或直接開啟"
        " PDF），進入詳細頁面後程式自動帶回資訊。"
    )

    if "hta_records" not in st.session_state:
      st.session_state.hta_records = []

    def run_hta_scraper(target_type, target_url):
      status_box = st.empty()
      status_box.info(f"正在開啟 Chrome 前往 {target_type}...")

      user_data_dir = os.path.abspath("./chrome_temp_profile")
      is_cloud = "/mount/src" in os.path.abspath(__file__)

      launch_args = [
          "--disable-blink-features=AutomationControlled",
          "--no-sandbox",
          "--disable-setuid-sandbox",
          "--disable-dev-shm-usage",
      ]
      if not is_cloud:
        launch_args.append("--start-maximized")

      try:
        with sync_playwright() as p:
          try:
            # 優先嘗試啟動本機 Chrome（若為雲端環境則自動略過）
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel="chrome" if not is_cloud else None,
                headless=is_cloud,
                no_viewport=not is_cloud,
                args=launch_args,
                ignore_default_args=["--enable-automation"],
            )
          except Exception:
            # 備援啟動標準 Chromium
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=is_cloud,
                no_viewport=not is_cloud,
                args=launch_args,
                ignore_default_args=["--enable-automation"],
            )

          init_page = context.pages[0] if context.pages else context.new_page()

          init_page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            });
          """)

          init_page.goto(target_url, timeout=60000)

          status_box.warning(
              "💡 請在 Chrome 中搜尋並點進「目標報告詳細頁面或 PDF"
              " 預覽」（系統提供最長 10 分鐘充裕時間）。"
          )

          active_page = None

          for _ in range(300):
            init_page.wait_for_timeout(2000)

            open_pages = [pg for pg in context.pages if not pg.is_closed()]
            if not open_pages:
              break

            for candidate_page in reversed(open_pages):
              try:
                curr_url = candidate_page.url
                if not curr_url or curr_url.startswith("about:"):
                  continue

                hit = False

                if target_type == "CDA-AMC":
                  page_text_check = candidate_page.inner_text("body")
                  if "/find-reports" not in curr_url and (
                      "Project Number" in page_text_check
                      or "Project Status" in page_text_check
                      or "Reimbursement Review" in page_text_check
                  ):
                    hit = True

                elif target_type == "PBAC":
                  if curr_url.lower().endswith(".pdf") or (
                      "/psd/20" in curr_url
                      and "Meeting Date" in candidate_page.inner_text("body")
                  ):
                    hit = True

                elif target_type == "NICE":
                  if any(
                      code in curr_url for code in ["/ta", "/ng", "/hst", "/cg"]
                  ) and "Overview" in candidate_page.inner_text("body"):
                    hit = True

                elif target_type == "SMC":
                  if curr_url.lower().endswith(".pdf") or (
                      curr_url.rstrip("/") != target_url.rstrip("/")
                      and any(
                          term in candidate_page.inner_text("body")
                          for term in ["Advice:", "Indication:", "Product:"]
                      )
                  ):
                    hit = True

                if hit:
                  active_page = candidate_page
                  break
              except Exception:
                continue

            if active_page:
              active_page.wait_for_timeout(1500)
              break

          if active_page and not active_page.is_closed():
            current_url = active_page.url
            page_body = ""
            try:
              page_body = active_page.inner_text("body")
            except Exception:
              pass

            # 1. CDA-AMC
            if target_type == "CDA-AMC":
              gen_match = re.search(
                  r"Generic Name[:\s\n]+([^\n\r]+)", page_body, re.IGNORECASE
              )
              generic_name = (
                  gen_match.group(1).strip().capitalize()
                  if gen_match
                  else ""
              )
              if not generic_name:
                h1_elem = active_page.locator("h1")
                generic_name = (
                    h1_elem.first.inner_text().strip().capitalize()
                    if h1_elem.count() > 0
                    else "Medicine"
                )

              brand_match = re.search(
                  r"Brand Name[:\s\n]+([^\n\r]+)", page_body, re.IGNORECASE
              )
              brand_name = brand_match.group(1).strip() if brand_match else ""
              brand_str = f" ({brand_name})" if brand_name else ""

              proj_match = re.search(
                  r"Project Number[:\s\n]+([A-Z0-9]+)(?:-\d+)?",
                  page_body,
                  re.IGNORECASE,
              )
              proj_code = (
                  f" [{proj_match.group(1).strip()}]" if proj_match else ""
              )

              full_title = f'"Reimbursement Recommendation-{generic_name}{brand_str}{proj_code}"'

              date_match = re.search(
                  r"Final Recommendation/Report[:\s\n]+([A-Za-z]+\s+\d{1,2},\s+202\d)",
                  page_body,
                  re.IGNORECASE,
              )
              if not date_match:
                date_match = re.search(
                    r"([A-Za-z]+\s+\d{1,2},\s+202\d)", page_body
                )
              published_date = (
                  date_match.group(1).strip() if date_match else "Unknown"
              )

            # 2. PBAC
            elif target_type == "PBAC":
              full_title = ""
              published_date = "Unknown"

              if current_url.lower().endswith(".pdf"):
                try:
                  req = urllib.request.Request(
                      current_url, headers={"User-Agent": "Mozilla/5.0"}
                  )
                  pdf_data = urllib.request.urlopen(req).read()
                  reader = pypdf.PdfReader(io.BytesIO(pdf_data))
                  first_page_text = reader.pages[0].extract_text()

                  meeting_match = re.search(
                      r"Public Summary Document\s*[-–]\s*([A-Za-z]+\s+202\d)\s+PBAC"
                      r" Meeting",
                      first_page_text,
                      re.IGNORECASE,
                  )
                  if meeting_match:
                    published_date = meeting_match.group(1).strip()

                  drug_match = re.search(
                      r"\d+\.\d+\s+([A-Z\s\-]+),", first_page_text
                  )
                  drug_name = (
                      drug_match.group(1).strip().capitalize()
                      if drug_match
                      else "Medicine"
                  )

                  brand_match = re.search(r"([A-Za-z0-9]+®)", first_page_text)
                  brand_str = (
                      f" ({brand_match.group(1).strip()})"
                      if brand_match
                      else ""
                  )

                  full_title = f'"Public Summary Document - {drug_name}{brand_str} - {published_date} PBAC Meeting"'
                except Exception:
                  pass

              if not full_title:
                date_match = re.search(
                    r"Meeting Date[:\s]+([A-Za-z]+\s+202\d)", page_body
                )
                if not date_match:
                  date_match = re.search(
                      r"Last updated[:\s]+([0-9]{1,2}\s+[A-Za-z]+\s+202\d)",
                      page_body,
                  )
                published_date = (
                    date_match.group(1).strip() if date_match else "Unknown"
                )

                brand_match = re.search(
                    r"Brand names?[:\s]+([^\n\r]+)", page_body
                )
                brand_name = (
                    f" ({brand_match.group(1).strip()})" if brand_match else ""
                )

                h1_elem = active_page.locator("h1")
                raw_h1 = (
                    h1_elem.first.inner_text().strip()
                    if h1_elem.count() > 0
                    else ""
                )
                drug_name = (
                    raw_h1.split("–")[0].split("-")[0].strip()
                    if raw_h1
                    else "Medicine"
                )
                full_title = f'"Public Summary Document - {drug_name}{brand_name} - {published_date} PBAC Meeting"'

            # 3. NICE
            elif target_type == "NICE":
              h1_elem = active_page.locator("h1")
              title_text = (
                  h1_elem.first.inner_text().strip()
                  if h1_elem.count() > 0
                  else active_page.title()
              )
              ta_match = re.search(r"\b(TA\d+|HST\d+|NG\d+|CG\d+)\b", page_body)
              ta_code = f" [{ta_match.group(1)}]" if ta_match else ""
              full_title = f'"{title_text}{ta_code}"'

              published_date = "Unknown"
              time_elements = active_page.locator("time").all()
              for t in time_elements:
                t_text = t.inner_text().strip()
                if re.search(r"202\d", t_text):
                  published_date = t_text
                  break
                t_dt = t.get_attribute("datetime")
                if t_dt and re.search(r"202\d", t_dt):
                  published_date = t_dt.split("T")[0]
                  break

              if published_date == "Unknown":
                date_match = re.search(
                    r"Published(?:\s+date)?[:\s]+([0-9]{1,2}\s+[A-Za-z]+\s+202\d)",
                    page_body,
                    re.IGNORECASE,
                )
                if date_match:
                  published_date = date_match.group(1).strip()

            # 4. SMC
            else:
              smc_code = ""
              published_date = "Unknown"
              med_title = ""

              if current_url.lower().endswith(".pdf"):
                try:
                  req = urllib.request.Request(
                      current_url, headers={"User-Agent": "Mozilla/5.0"}
                  )
                  pdf_data = urllib.request.urlopen(req).read()
                  reader = pypdf.PdfReader(io.BytesIO(pdf_data))
                  first_page_text = reader.pages[0].extract_text()

                  smc_match = re.search(r"\b(SMC\d{4,5})\b", first_page_text)
                  if smc_match:
                    smc_code = f" [{smc_match.group(1)}]"

                  title_match = re.search(
                      r"([a-z0-9\s\-]+concentrate for solution for"
                      r" infusion\s*\([^\)]+\))",
                      first_page_text,
                      re.IGNORECASE,
                  )
                  if not title_match:
                    title_match = re.search(
                        r"([a-z0-9\s\-]+\([A-Za-z0-9®\s]+\))\s*\n\s*Merck",
                        first_page_text,
                        re.IGNORECASE,
                    )
                  if title_match:
                    med_title = title_match.group(1).strip()

                  pub_date_match = re.search(
                      r"Published\s+(\d{1,2}\s+[A-Za-z]+\s+202\d)",
                      first_page_text,
                      re.IGNORECASE,
                  )
                  if pub_date_match:
                    published_date = pub_date_match.group(1).strip()
                  else:
                    date_match = re.search(
                        r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+202\d)",
                        first_page_text,
                    )
                    if date_match:
                      published_date = date_match.group(1).strip()
                except Exception:
                  pass

              if not med_title:
                h1_elem = active_page.locator("h1")
                h1_text = (
                    h1_elem.first.inner_text().strip()
                    if h1_elem.count() > 0
                    else ""
                )
                if not smc_code:
                  smc_match = re.search(
                      r"\b(SMC\d{4,5}|SMC\s+\d{4,5})\b",
                      page_body,
                      re.IGNORECASE,
                  )
                  smc_code = (
                      f" [{smc_match.group(1).replace(' ', '')}]"
                      if smc_match
                      else ""
                  )

                desc_match = re.search(
                    r"(?:Product|Medicine)[:\s\n]+([^\n\r]+)",
                    page_body,
                    re.IGNORECASE,
                )
                med_title = (
                    desc_match.group(1).strip() if desc_match else h1_text
                )

                if published_date == "Unknown":
                  date_match = re.search(
                      r"(?:Published|Date|Issued)[:\s]+([0-9]{1,2}\s+[A-Za-z]+\s+202\d|[A-Za-z]+\s+[0-9]{1,2},\s+202\d)",
                      page_body,
                      re.IGNORECASE,
                  )
                  if date_match:
                    published_date = date_match.group(1).strip()

              clean_title = re.sub(
                  r"^Medicines advice\s*[-–:]\s*",
                  "",
                  med_title,
                  flags=re.IGNORECASE,
              ).strip()
              full_title = f'"Medicines advice - {clean_title}{smc_code}"'

            context.close()

            record = {
                "source": target_type,
                "title": full_title,
                "date": published_date,
                "url": current_url,
            }
            if not any(
                r["url"] == current_url for r in st.session_state.hta_records
            ):
              st.session_state.hta_records.append(record)

            status_box.success(f"🎉 成功擷取 {target_type} 報告資訊！")

          else:
            status_box.info("瀏覽器視窗已關閉。")

      except Exception as e:
        status_box.error(f"❌ 擷取失敗或發生例外：{str(e)}")

    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

    with btn_col1:
      if st.button("🚀 啟動 CDA 自動擷取", key="btn_cda", use_container_width=True):
        run_hta_scraper("CDA-AMC", "https://www.cda-amc.ca/find-reports")

    with btn_col2:
      if st.button("🚀 啟動 PBAC 自動擷取", key="btn_pbac", use_container_width=True):
        run_hta_scraper("PBAC", "https://www.pbs.gov.au/industry/pbac/psd")

    with btn_col3:
      if st.button("🚀 啟動 NICE 自動擷取", key="btn_nice", use_container_width=True):
        run_hta_scraper("NICE", "https://www.nice.org.uk/guidance")

    with btn_col4:
      if st.button("🚀 啟動 SMC 自動擷取", key="btn_smc", use_container_width=True):
        run_hta_scraper(
            "SMC", "https://scottishmedicines.org.uk/medicines-advice/"
        )

    # 呈現累積成果清單
    if st.session_state.hta_records:
      st.markdown("---")
      res_head_col, clear_btn_col = st.columns([4, 1])
      with res_head_col:
        st.markdown(
            f"### 📌 已擷取報告清單（共 {len(st.session_state.hta_records)} 筆）"
        )
      with clear_btn_col:
        if st.button(
            "🗑️ 清空所有紀錄", key="clear_hta_records", use_container_width=True
        ):
          st.session_state.hta_records = []
          st.rerun()

      all_combined_text = []
      for item in st.session_state.hta_records:
        record_block = (
            f"# [{item['source']}]\n"
            f"Title: {item['title']}\n"
            f'Published Date: "{item["date"]}"\n'
            f'URL: "{item["url"]}"'
        )
        all_combined_text.append(record_block)

      st.caption(
          "以下區塊彙整了本次查詢的所有機構資料，可直接點擊右上角一次複製："
      )
      st.code("\n\n".join(all_combined_text), language="yaml")

  # 4. 醫學與文獻資料庫
  st.markdown("---")
  st.subheader("📚 資料庫")
  db_col1, db_col2, db_col3 = st.columns(3)

  with db_col1:
    st.link_button(
        "🔬 PubMed 生物醫學文獻資料庫",
        "https://pubmed.ncbi.nlm.nih.gov/",
    )

  with db_col2:
    st.link_button(
        "🧪 Embase 生物醫學與藥學資料庫",
        "https://www.embase.com",
    )

  with db_col3:
    st.link_button(
        "🩺 Amboss 臨床醫學知識平台",
        "https://www.amboss.com/int",
    )

  st.markdown("---")

  # 5. 癌症 Guideline 查詢
  st.subheader("🩺 臨床指引 (Guidelines)")
  st.link_button(
      "📖 NCCN Clinical Practice Guidelines in Oncology",
      "https://www.nccn.org/guidelines/category_1",
  )

  st.markdown("---")

  # 6. 文書處理與學術工具
  st.subheader("📝 文書處理與排版教學工具")
  st.link_button(
      "📄 Word文件排版應用教學指南 (PDF)",
      "https://lib.ntut.edu.tw/public/images/20214201667.pdf",
  )

# ---------------------------------------------------------------------
# 頁籤 3：療效評估報告（含文獻回顧摘要）
# 呈現順序：CDA-AMC -> PBAC -> NICE -> SMC (純上傳模式)
# ---------------------------------------------------------------------
with tab3:
  st.subheader("📑 國際 HTA 評估報告 6 段式結構化 AI 編譯")
  st.caption(
      "支援「加拿大 CDA-AMC」、「澳洲 PBAC」、「英國 NICE」與「蘇格蘭"
      " SMC」報告 PDF 全文解析。依據官方 6 大審查維度產出繁體中文技術審查素材。"
  )

  # 機構選擇：CDA-AMC -> PBAC -> NICE -> SMC
  target_agency = st.radio(
      "🏛️ 請選擇 HTA 評估機構：",
      [
          "🇨🇦 加拿大 CDA-AMC (Reimbursement Review)",
          "🇦🇺 澳洲 PBAC (Public Summary Document)",
          "🇬🇧 英國 NICE (Technology Appraisal)",
          "🏴󠁧󠁢󠁳󠁣󠁴󠁿 蘇格蘭 SMC (Detailed Advice Document)",
      ],
      horizontal=True,
  )

  agency_tag = "CDA-AMC"
  if "PBAC" in target_agency:
    agency_tag = "PBAC"
  elif "NICE" in target_agency:
    agency_tag = "NICE"
  elif "SMC" in target_agency:
    agency_tag = "SMC"

  uploaded_pdf = st.file_uploader(
      f"請選擇或拖曳 {agency_tag} 評估報告 PDF 檔案：",
      type=["pdf"],
      help=f"支援直接解析本機的 {agency_tag} 官方評估報告 PDF",
  )

  button_label = f"🚀 開始產生 {agency_tag} 結構化審查編譯"

  if st.button(button_label, key="btn_run_hta_ai", use_container_width=True):
    if not openai_api_key:
      st.error("⚠️ 請先在畫面左側側邊欄 (Sidebar) 輸入 OpenAI API Key！")
    elif not uploaded_pdf:
      st.error(f"⚠️ 請先選擇或上傳一份 {agency_tag} 的 PDF 檔案！")
    else:
      report_full_text = ""
      with st.spinner(f"📄 正在解析上傳的 {agency_tag} PDF 檔案文字..."):
        try:
          reader = pypdf.PdfReader(uploaded_pdf)
          extracted_pages = []
          # 讀取最多前 45 頁（精準保留核心審查決議，並防範 TPM 429 超限）
          for page_idx in range(min(len(reader.pages), 45)):
            page_text = reader.pages[page_idx].extract_text()
            if page_text:
              extracted_pages.append(page_text)
          report_full_text = "\n\n".join(extracted_pages)
        except Exception as e:
          st.error(f"❌ 讀取 PDF 失敗：{str(e)}")

      if not report_full_text.strip():
        st.error("❌ 無法擷取到任何文字內容，請確認檔案是否為文字型 PDF。")
      else:
        with st.spinner(
            f"🤖 AI 正在精讀 {agency_tag} 報告並依照 6 大維度深度編撰中..."
        ):
          try:
            if "CDA-AMC" in target_agency:
              summary_res, usage = summarize_cda_report(
                  report_full_text, openai_api_key, target_model
              )
              out_filename = "CDA_AMC_Structured_Summary.txt"
            elif "PBAC" in target_agency:
              summary_res, usage = summarize_pbac_report(
                  report_full_text, openai_api_key, target_model
              )
              out_filename = "PBAC_Structured_Summary.txt"
            elif "NICE" in target_agency:
              summary_res, usage = summarize_nice_report(
                  report_full_text, openai_api_key, target_model
              )
              out_filename = "NICE_Structured_Summary.txt"
            else:
              summary_res, usage = summarize_smc_report(
                  report_full_text, openai_api_key, target_model
              )
              out_filename = "SMC_Structured_Summary.txt"

            st.success("🎉 成功生成結構化審查素材！")

            st.info(
                f"🤖 **模型**：`{target_model}` | 輸入: {usage.prompt_tokens:,}"
                f" tokens | 輸出: {usage.completion_tokens:,} tokens"
            )

            st.markdown(
                "### 📋 結構化審查摘要 (純文字版，點擊右上角一鍵複製)"
            )
            st.code(summary_res, language=None)

            st.download_button(
                label="📥 下載為純文字檔案 (.txt)",
                data=summary_res,
                file_name=out_filename,
                mime="text/plain",
            )
          except Exception as e:
            st.error(f"❌ 摘要生成失敗：{str(e)}")
