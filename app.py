import json
import os
import re
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup
import gdown
import pandas as pd
import streamlit as st

# =====================================================================
# 1. 頁面配置
# =====================================================================
st.set_page_config(
    page_title="臺灣健保藥品與電子仿單查詢系統", page_icon="💊", layout="wide"
)

st.title("💊 臺灣健保藥品與電子仿單查詢系統")
st.caption("🔒 雲端自動同步版：雙資料庫自動下載與快取機制")

SERVICEURL = "https://mcp.fda.gov.tw/im_detail_1/"
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,'
        ' like Gecko) Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    ),
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
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
  return f'<span style="background-color: #1e3a8a; color: #ffffff; padding: 4px 8px; border-radius: 4px; font-weight: 500; display: inline-block;">{text}</span>'


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


with st.spinner("📥 首次啟動：正在從雲端下載資料庫並建立索引 (約需 5-10 秒)..."):
  json_database, lic_index, ename_index = load_and_index_databases()

if not json_database:
  st.error("❌ 錯誤：無法載入資料庫！")
  st.stop()


def get_field_from_dict(item, target_keys):
  cleaned = {
      str(k).replace(" ", "").replace("\u3000", "").strip(): v
      for k, v in item.items()
      if k is not None
  }

  # 1. 精確匹配
  for tk in target_keys:
    clean_tk = tk.replace(" ", "").strip()
    if clean_tk in cleaned:
      val = cleaned[clean_tk]
      if (
          val is not None
          and str(val).strip() != ""
          and str(val).strip().lower() not in ["none", "null"]
      ):
        if isinstance(val, list):
          return " ; ".join([str(x).strip() for x in val])
        return str(val).strip()

  # 2. 模糊匹配 (防止 Key 名稱有些微落差)
  for tk in target_keys:
    clean_tk = tk.replace(" ", "").strip()
    for k, v in cleaned.items():
      if clean_tk in k or k in clean_tk:
        if (
            v is not None
            and str(v).strip() != ""
            and str(v).strip().lower() not in ["none", "null"]
        ):
          if isinstance(v, list):
            return " ; ".join([str(x).strip() for x in v])
          return str(v).strip()

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
# 4. 前端搜尋介面
# =====================================================================
st.markdown("---")

with st.form(key="search_form"):
  col1, col2 = st.columns([1, 3])

  with col1:
    search_mode = st.selectbox(
        "🎯 請選擇搜尋範圍：",
        [
            "僅限成分 (Ingredient)",
            "全域搜尋 (中文/英文/字號/適應症/ATC)",
        ],
    )

  with col2:
    keyword = st.text_input(
        "🔍 請輸入搜尋關鍵字：",
        placeholder="例如：DURVALUMAB、CHLORPROMAZINE、AMITRIPTYLINE...",
    )

  submit_button = st.form_submit_button(
      label="🔍 立即查詢 (按下 Enter 即可發送)"
  )

# 已補齊「申請商名稱」等精確欄位 Key
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
        })
        if clean_lic:
          seen_lics.add(clean_lic)

    if not matched_results:
      st.warning(f"❌ 找不到包含關鍵字【{kw_clean}】的藥品資料！")
    else:
      st.success(f"🎉 共找到 {len(matched_results)} 筆藥品資料！")

      for idx, drug in enumerate(matched_results[:20], start=1):
        c_name = drug["中文名稱"]
        e_name = drug["英文名稱"]
        lic_num = drug["許可證字號"]

        with st.expander(
            f"【{idx}】{c_name} | {e_name} (許可證: {lic_num})", expanded=True
        ):
          st.markdown(f"**藥品中文名稱：** {c_name}")
          st.markdown(f"**藥品英文名稱：** {e_name}")
          st.markdown(f"**許可證字號：** `{lic_num}`")

          # 排列順序：成分 ➔ 劑型 ➔ 申請商 ➔ ATC代碼 ➔ 健保支付價
          st.markdown(f"**成分：** `{drug['成分']}`")
          st.markdown(f"**劑型：** `{drug['劑型']}`")
          st.markdown(f"**申請商：** `{drug['申請商']}`")

          st.markdown(f"**ATC代碼：** `{drug['ATC代碼']}`")
          st.markdown(f"**健保支付價：** `{drug['支付價']}`")

          with st.spinner("⚡ 正在對接食藥署線上系統..."):
            online_ind, online_dos, err = fetch_fda_online_details(lic_num)

            # 適應症
            final_ind = online_ind if online_ind else drug["本地適應症"]
            if final_ind != "無紀錄":
              st.markdown(
                  f"**適應症：** {render_blue_badge(final_ind)}",
                  unsafe_allow_html=True,
              )
            else:
              st.markdown("**適應症：** 無紀錄")

            # 用法用量
            if online_dos:
              st.markdown(
                  f"**用法用量：** {render_blue_badge(online_dos)}",
                  unsafe_allow_html=True,
              )
            else:
              fallback_err = err if err else "無紀錄"
              st.markdown(
                  f"**用法用量：** {render_blue_badge(fallback_err)}",
                  unsafe_allow_html=True,
              )

          st.markdown(" ")
          target_fda_url = f"https://mcp.fda.gov.tw/im_detail_1/{urllib.parse.quote(lic_num)}"
          st.link_button(
              "🌐 前往食藥署仿單詳細網頁",
              target_fda_url,
              use_container_width=False,
          )
