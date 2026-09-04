import os
from PIL import Image

# ==============================
# 🔧 設定區 (絕對路徑版)
# ==============================
# 自動取得這個 Python 檔所在的資料夾路徑 (你的 fgoautogpt3.0 資料夾)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 組合出正確的路徑
INPUT_FOLDER = os.path.join(BASE_DIR, "assets_system", "orig_ui")
# 直接輸出到 assets_ui 給 main.py 用
OUTPUT_FOLDER = os.path.join(BASE_DIR, "assets_ui") 

os.makedirs(INPUT_FOLDER, exist_ok=True) # 如果你還沒建資料夾，幫你建起來免得報錯
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 🚀 定義你的按鈕清單與目標寬度 (檔名, 寬度)
BUTTON_LIST = [
    ("btn_start_n.png", 160), ("btn_start_p.png", 160), ("btn_start_d.png", 160),
    ("btn_stop_n.png", 160),  ("btn_stop_p.png", 160),  ("btn_stop_d.png", 160),
    ("btn_save_n.png", 120),  ("btn_save_p.png", 120),  ("btn_save_d.png", 120),
    ("btn_load_n.png", 120),  ("btn_load_p.png", 120),  ("btn_load_d.png", 120)
]

def resize_images():
    print(f"📂 正在從這裡尋找原圖: {INPUT_FOLDER}")
    for filename, target_w in BUTTON_LIST:
        in_p = os.path.join(INPUT_FOLDER, filename)
        if not os.path.exists(in_p):
            print(f"⚠️ 找不到: {filename}")
            continue
            
        try:
            img = Image.open(in_p).convert("RGBA")
            # 計算比例縮小
            w_per = (target_w / float(img.size[0]))
            h_size = int((float(img.size[1]) * float(w_per)))
            img_res = img.resize((target_w, h_size), Image.Resampling.LANCZOS)
            
            img_res.save(os.path.join(OUTPUT_FOLDER, filename), "PNG")
            print(f"✅ 已完成縮小: {filename} (寬度: {target_w})")
        except Exception as e:
            print(f"❌ 處理 {filename} 時發生錯誤: {e}")

if __name__ == "__main__":
    resize_images()