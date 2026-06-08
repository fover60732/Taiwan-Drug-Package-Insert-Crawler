import json
import urllib.request
import urllib.parse  
from bs4 import BeautifulSoup  

# =====================================================================
# ⚡ 1. 前端極速初始化設定（先吃本地快取，達成 0.05 秒瞬間開機！）
# =====================================================================
print("📦 正在初始化本地藥品許可證資料庫...")
try:
    # 💡 核心優化：直接讀取電腦裡現有的舊檔案，完全不用等網路，秒速開機！
    with open('39_5.json', 'r', encoding='utf-8') as f:
        brand_dict = json.load(f)
    print("✨ 本地資料庫載入成功！已準備好進行高效模糊查詢。")
except FileNotFoundError:
    # 萬一真的是第一次用、連本地檔都沒有，才需要在這裡強制等雲端下載
    print("⚠️ 本地找不到資料庫，正在嘗試首次雲端應急下載...")
    try:
        FILE_ID = '1ip_lP0Jard142l7Si9xHvXsma2V-1QfW' 
        gov_json_url = f'https://docs.google.com/uc?export=download&id={FILE_ID}'
        headers = {'User-Agent': 'Mozilla/5.0'}
        req_gov = urllib.request.Request(gov_json_url, headers=headers)
        with urllib.request.urlopen(req_gov, timeout=20) as response:
            brand_dict = json.loads(response.read().decode('utf-8', errors='ignore'))
        with open('39_5.json', 'w', encoding='utf-8') as f:
            json.dump(brand_dict, f, ensure_ascii=False, indent=4)
        print("✨ 首次雲端下載成功並已建立本地資料庫！")
    except Exception as e:
        print(f"❌ 嚴重錯誤：雲端下載失敗且本地無檔案（原因：{e}）")
        exit()

# 補回食藥署仿單查詢系統的核心網址與帽子
serviceurl = 'https://mcp.fda.gov.tw/im_detail_1/'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

print("-" * 65)

# =====================================================================
# 2. 主程式無限循環區（商品名查詢）- 這裡執行速度極快，因為資料早就在記憶體裡了
# =====================================================================
while True:
    user_input = input('請輸入藥品【英文品名】或【片段】(輸入 Enter 結束): ').strip()
    if len(user_input) < 1:
        break

    matched_results = [] 
    for item in brand_dict:
        if '英文品名' in item and item['英文品名'] is not None:
            brand_name = item['英文品名']
            if user_input.lower() in brand_name.lower():
                if brand_name not in matched_results:
                    matched_results.append(brand_name)

    address = None
    chosen_brand = None
    
    if len(matched_results) == 0:
        print(f"❌ 找不到包含【{user_input}】的任何英文品名，請重新輸入！\n")
        continue
        
    elif len(matched_results) == 1:
        chosen_brand = matched_results[0]
        for item in brand_dict:
            if item.get('英文品名') == chosen_brand:
                address = item.get('許可證字號') 
                break
        print(f"🎯 自動辨識唯一英文品名：【{chosen_brand}】")
        print(f"📄 對應許可證字號：{address}")
        
    else:
        print(f"🔍 找到了 {len(matched_results)} 個相似的藥品，請問您是指哪一個？")
        for i, name in enumerate(matched_results, start=1):
            print(f"   [{i}] {name}")
            
        choice = input("👉 請輸入對應號碼 (輸入其他任意字放棄本次查詢): ").strip()
        try:
            chosen_index = int(choice) - 1
            if 0 <= chosen_index < len(matched_results):
                chosen_brand = matched_results[chosen_index]
                for item in brand_dict:
                    if item.get('英文品名') == chosen_brand:
                        address = item.get('許可證字號')
                        break
                print(f"🚀 已選定【{chosen_brand}】，準備連線撈取仿單...")
            else:
                print("❌ 號碼超出範圍，回到主查詢。\n")
                continue
        except:
            print("↩️ 已取消，回到主查詢。\n")
            continue

    if not address:
        print("⚠️ 系統提示：找不到該藥品的許可證字號欄位資料。\n")
        continue

    # =====================================================================
    # 3. 聯網抓取與解析雲端仿單 (HTML)
    # =====================================================================
    url = serviceurl + urllib.parse.quote(address)
    print("🌐 正在連線至食藥署電子仿單系統...")
    
    req = urllib.request.Request(url, headers=headers)

    try:
        data = urllib.request.urlopen(req).read()
        soup = BeautifulSoup(data, 'html.parser')
        
        all_portions = soup.find_all('div', class_='toggle')
        valid_chapters = {} 
        
        temp_menu_lines = []
        for idx, x in enumerate(all_portions[1:14], start=1):
            title_tag = x.find('span', class_='title-name')
            if title_tag:
                title_text = title_tag.text.strip()
                temp_menu_lines.append(f" [{idx}] {title_text}")
                valid_chapters[str(idx)] = x 
        
        if len(valid_chapters) == 0:
            print("\n❌ 提示：電子仿單尚未完成建置，請重新查詢！\n")
            continue  
            
        print("\n" + "="*20 + " 🪐 藥品仿單章節選單 🪐 " + "="*20)
        for menu_line in temp_menu_lines:
            print(menu_line)
        print("=" * 61)

        # =====================================================================
        # 4. 內層互動區：重複看不同章節
        # =====================================================================
        while True:
            print(f"\n💡 [提示] 當前可選擇的章節號碼為 [1] ~ [{len(valid_chapters)}]。")
            print("   看完了？可以輸入新的數字繼續看其他章節，或輸入 q 返回主選單換查別顆藥。")
            
            chap = input("💬 請選擇要查詢的章節號碼: ").strip()
            if chap.lower() == 'q':
                print("↩️ 已返回藥品主查詢選單。\n")
                break
                
            if chap in valid_chapters:
                selected_node = valid_chapters[chap]
                title_tag = selected_node.find('span', class_='title-name')
                content_tag = selected_node.find('div', class_='inner')
                
                if title_tag and content_tag:
                    print("\n" + "📖 " + "-"*20 + f" {title_tag.text.strip()} " + "-"*20)
                    clean_lines = [line.strip() for line in content_tag.text.splitlines() if line.strip()]
                    clean_content = "\n".join(clean_lines)
                    
                    print(clean_content)
                    print("-" * (45 + len(title_tag.text.strip())) + "\n")
            else:
                print("❌ 輸入錯誤！請輸入畫面上有的數字編號。")
                
    except urllib.error.HTTPError as e:
        print(f"⚠️ 連線失敗！食藥署伺服器拒絕連線，錯誤代碼：{e.code}")
    except Exception as e:
        print(f"💥 發生非預期系統錯誤：{e}")
        
    print("\n" + "*"*23 + f" 【{chosen_brand}】查詢結束 " + "*"*23 + "\n")


# =====================================================================
# 🔄 5. 背景悄悄更新機制（當使用者輸入 Enter 結束程式時，才觸發這段）
# =====================================================================
print("\n👋 正在關閉主程式...")
print("🔄 系統正在背景與您的 Google 雲端硬碟同步，檢查是否有最新藥物對照表...")

try:
    FILE_ID = '1ip_lP0Jard142l7Si9xHvXsma2V-1QfW' 
    gov_json_url = f'https://docs.google.com/uc?export=download&id={FILE_ID}'
    
    req_gov = urllib.request.Request(gov_json_url, headers=headers)
    with urllib.request.urlopen(req_gov, timeout=10) as response:
        remote_data = response.read()
        decoded_text = remote_data.decode('utf-8', errors='ignore')
        json_test = json.loads(decoded_text)
        
        # 將最新下載到的資料蓋寫進硬碟，作為明天的開機快取
        with open('39_5.json', 'w', encoding='utf-8') as f:
            json.dump(json_test, f, ensure_ascii=False, indent=4)
    print("✨ 雲端資料同步完成！本地快取已更新至最新版本，下次開機將自動生效。")
except Exception as e:
    print(f"⚠️ 本次雲端背景同步未成功（原因：{e}），將於下次關機時再次嘗試。")

print("✨ 謝謝使用，系統已安全關閉。")