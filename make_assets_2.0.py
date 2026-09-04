import cv2
import numpy as np
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# ==========================================
# 🚀 請在這裡填入你從小畫家量到的 御主技能 CD 座標！
# ==========================================
INPUT_FILENAME = 'skip.png' 
INPUT_SCREENSHOT = os.path.join(BASE_DIR, INPUT_FILENAME)

# 範例座標 (請改成你實際量到的數字)
CROP_X = 1715
CROP_Y = 40 
CROP_W = 166
CROP_H = 43  
# ==========================================

OUTPUT_DIR = os.path.join(BASE_DIR, 'assets_system')
os.makedirs(OUTPUT_DIR, exist_ok=True)

if not os.path.exists(INPUT_SCREENSHOT):
    print(f"❌ 找不到 {INPUT_SCREENSHOT}！")
    exit()

img_raw = cv2.imread(INPUT_SCREENSHOT, cv2.IMREAD_GRAYSCALE)
h_raw, w_raw = img_raw.shape
if (w_raw, h_raw) != (1920, 1080):
    img = cv2.resize(img_raw, (1920, 1080))
else:
    img = img_raw

roi = img[CROP_Y:CROP_Y+CROP_H, CROP_X:CROP_X+CROP_W]
_, mask_raw = cv2.threshold(roi, 220, 255, cv2.THRESH_BINARY)
kernel = np.ones((2,2), np.uint8)
skip_mask = cv2.dilate(mask_raw, kernel, iterations=1)
skip_tpl = cv2.bitwise_and(roi, roi, mask=mask_raw)

# 注意這裡存的檔名不一樣喔！
cv2.imwrite(os.path.join(OUTPUT_DIR, 'skip_btn_tpl.png'), skip_tpl)
cv2.imwrite(os.path.join(OUTPUT_DIR, 'skip_btn_mask.png'), skip_mask)

print(f"✅ 御主專屬聖遺物生成完畢！")