import cv2
import numpy as np
import os
import time

# 🔬 開發用：把每次 CD 判斷的 ROI 存成圖片並印出各項指標，
#    用來釐清判斷失準的原因。正式發布請改回 False。
CD_DEBUG = False

from coords import SKILLS, MASTER_SKILLS, ROI_SKIP_BTN, CD_ROI_OFFSET_X, CD_ROI_OFFSET_Y

class FGOVision:
    def __init__(self, context):
        self.ctx = context  # 取得 FGOLogic 的參考
        self.cooldown_tpl = None
        self.cooldown_mask = None
        self.master_cooldown_tpl = None
        self.master_cooldown_mask = None
        self.weak_tpl = None
        self.resist_tpl = None
        self.skip_tpl = None
        self.skip_mask = None
        
        self._load_cooldown_assets()

    def _imread_gray_unicode(self, path):
        """🚀 破解 OpenCV 讀取中文路徑報錯的底層神技"""
        if not os.path.exists(path): return None
        try:
            img_data = np.fromfile(path, dtype=np.uint8)
            return cv2.imdecode(img_data, cv2.IMREAD_GRAYSCALE)
        except Exception as e:
            print(f"⚠️ 讀取圖片失敗: {path}, 錯誤: {e}")
            return None

    def _load_cooldown_assets(self):
        sys_path = self.ctx.bot.sys_path
        
        self.cooldown_tpl = self._imread_gray_unicode(os.path.join(sys_path, 'cooldown_text_tpl.png'))
        self.cooldown_mask = self._imread_gray_unicode(os.path.join(sys_path, 'cooldown_text_mask.png'))
        
        self.master_cooldown_tpl = self._imread_gray_unicode(os.path.join(sys_path, 'master_cooldown_text_tpl.png'))
        self.master_cooldown_mask = self._imread_gray_unicode(os.path.join(sys_path, 'master_cooldown_text_mask.png'))

        self.weak_tpl = self._imread_gray_unicode(os.path.join(sys_path, 'weak_text.png'))
        self.resist_tpl = self._imread_gray_unicode(os.path.join(sys_path, 'resist_text.png'))

        self.skip_tpl = self._imread_gray_unicode(os.path.join(sys_path, 'skip_btn_tpl.png'))
        self.skip_mask = self._imread_gray_unicode(os.path.join(sys_path, 'skip_btn_mask.png'))

        # 🔬 素材完整性檢查：尺寸不符或遮罩覆蓋率異常都會讓比對分數失準
        for label, tpl, mask in (("從者 CD", self.cooldown_tpl, self.cooldown_mask),
                                 ("御主 CD", self.master_cooldown_tpl, self.master_cooldown_mask)):
            if tpl is None or mask is None:
                print(f"⚠️ [素材] {label} 模板或遮罩缺失，CD 判斷將永遠回報「未在 CD」")
                continue
            if tpl.shape != mask.shape:
                print(f"⚠️ [素材] {label} 模板 {tpl.shape} 與遮罩 {mask.shape} 尺寸不符，比對會失準")
            cover = float(np.mean(mask > 128)) * 100
            print(f"🔬 [素材] {label} 模板 {tpl.shape[1]}x{tpl.shape[0]}，遮罩覆蓋率 {cover:.1f}%")
            if cover < 3 or cover > 70:
                print(f"   ⚠️ 覆蓋率異常（正常約 10~40%），遮罩可能製作有誤")

    def check_skip_button(self):
        if self.skip_tpl is None or self.skip_mask is None: 
            return "NONE"
            
        if self.ctx.bot.current_screen_gray is None: return "NONE" 
        
        screen_gray = self.ctx.bot.current_screen_gray
        h, w = screen_gray.shape
        sx1, sy1, sx2, sy2 = ROI_SKIP_BTN
        roi = screen_gray[sy1:sy2, sx1:min(sx2, w)]
        
        if roi.shape[0] < self.skip_tpl.shape[0] or roi.shape[1] < self.skip_tpl.shape[1]:
            return "NONE"
            
        # 🚀 終極解法：改用 TM_CCOEFF_NORMED (不帶遮罩) 來尋找座標。
        # 它的數學特性會「自動過濾掉純黑或純白的無聊背景」，完美解決黑空氣偷分數的問題！
        res = cv2.matchTemplate(roi, self.skip_tpl, cv2.TM_CCOEFF_NORMED)
        
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        # 因為沒戴遮罩，背景顏色會影響一點分數，所以相似度門檻降到安全的 0.70
        if np.isnan(max_val) or max_val < 0.70: 
            return "NONE"
            
        real_x = sx1 + max_loc[0]
        real_y = max_loc[1]
        th, tw = self.skip_tpl.shape
        
        if real_y + th > h or real_x + tw > w: return "NONE"
            
        # 🚀 找到 100% 正確的按鈕位置後，我們再戴上 skip_mask「濾光眼鏡」來精準測量字體亮度！
        patch = self.ctx.bot.current_screen[real_y:real_y+th, real_x:real_x+tw]
        v_channel = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[:, :, 2]
        
        # 只提取字體部分 (白色區域 > 128) 的像素亮度
        text_pixels = v_channel[self.skip_mask > 128]
        v_val = np.mean(text_pixels) if text_pixels.size > 0 else 0
            
        print(f"👀 [SKIP 雷達] 最佳目標相似度: {max_val:.3f} | 純字體平均亮度: {v_val:.0f}")
        
        if v_val > 150: 
            return "READY"
        elif v_val > 80: 
            print("⚠️ SKIP 處於暗化狀態，將執行選項連點。")
            return "DARK"
            
        return "NONE"

    def get_skill_color_stats(self, x, y):
        if self.ctx.bot.current_screen is None: return 255, 255
        img = self.ctx.bot.current_screen
        roi = img[y-20:y+20, x-20:x+20]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        return np.mean(hsv[:, :, 1]), np.mean(hsv[:, :, 2])

    def _dump_cd_debug(self, x, y, roi, tpl, mask, score, is_master):
        """把判斷用的 ROI 存檔並印出各項指標，供人工比對真實狀態。"""
        try:
            out_dir = os.path.join(self.ctx.bot.base_dir, "cd_debug")
            os.makedirs(out_dir, exist_ok=True)

            # 亮白像素比例：CD 時疊在圖示上的「剩餘」字樣是高亮低飽和
            colour = self.ctx.bot.current_screen
            h, w = colour.shape[:2]
            y1, y2 = max(0, y), min(h, y + CD_ROI_OFFSET_Y)
            x1, x2 = max(0, x - CD_ROI_OFFSET_X), min(w, x + CD_ROI_OFFSET_X)
            patch = colour[y1:y2, x1:x2]
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
            bright_white = np.mean((hsv[:, :, 2] > 180) & (hsv[:, :, 1] < 60)) * 100
            mean_v = float(np.mean(hsv[:, :, 2]))

            role = "master" if is_master else "servant"
            print(f"🔬 [CD 診斷] {role} ({x},{y}) | 模板分數 {score:.3f} "
                  f"| 平均亮度 {mean_v:.0f} | 亮白像素 {bright_white:.1f}% "
                  f"| ROI {roi.shape[1]}x{roi.shape[0]} | 模板 {tpl.shape[1]}x{tpl.shape[0]}")

            name = f"{time.strftime('%H%M%S')}_{role}_{x}_{y}_s{score:.3f}_w{bright_white:.0f}.png"
            cv2.imencode('.png', patch)[1].tofile(os.path.join(out_dir, name))
        except Exception as e:
            print(f"⚠️ [CD 診斷] 輸出失敗: {e}")

    def check_skill_cooldown_visual(self, x, y, is_master=False):
        if self.ctx.bot.current_screen_gray is None: return False
        tpl = self.master_cooldown_tpl if is_master else self.cooldown_tpl
        mask = self.master_cooldown_mask if is_master else self.cooldown_mask

        if tpl is None or mask is None: return False 
        
        screen_gray = self.ctx.bot.current_screen_gray
        h, w = screen_gray.shape
        
        roi_startY, roi_endY = max(0, y), min(h, y + CD_ROI_OFFSET_Y)
        roi_startX, roi_endX = max(0, x - CD_ROI_OFFSET_X), min(w, x + CD_ROI_OFFSET_X)
        roi = screen_gray[roi_startY:roi_endY, roi_startX:roi_endX]
        
        if roi.shape[0] < tpl.shape[0] or roi.shape[1] < tpl.shape[1]: return False

        res = cv2.matchTemplate(roi, tpl, cv2.TM_CCORR_NORMED, mask=mask)
        _, max_val, _, _ = cv2.minMaxLoc(res)

        # 🚀 TM_CCORR_NORMED 搭配遮罩有機會算出 NaN/inf。
        #    若不處理，NaN >= 0.75 會是 False，等於誤判成「沒有 CD」，
        #    然後去點一個根本放不出來的技能。
        if np.isnan(max_val) or np.isinf(max_val):
            print(f"⚠️ [視覺] 座標({x},{y}) CD 比對結果異常 (NaN)，保守視為未在 CD")
            return False

        role_str = "御主" if is_master else "從者"
        print(f"🔍 [視覺 2.0] 座標({x},{y}) {role_str} CD 得分: {max_val:.3f}")

        if CD_DEBUG:
            self._dump_cd_debug(x, y, roi, tpl, mask, max_val, is_master)

        return max_val >= 0.75

    def check_skill_available_batch(self, is_master=False):
        if self.ctx.bot.current_screen_gray is None:
            return [False] * (len(MASTER_SKILLS) - 1 if is_master else len(SKILLS) - 1)
        
        screen_gray = self.ctx.bot.current_screen_gray
        h, w = screen_gray.shape
        
        # 🚀 統一由 coords.py 提供。切掉索引 0 的 None，讓這裡維持從 0 開始的清單
        skill_coords = MASTER_SKILLS[1:] if is_master else SKILLS[1:]

        available_list = []
        tpl = self.master_cooldown_tpl if is_master else self.cooldown_tpl
        mask = self.master_cooldown_mask if is_master else self.cooldown_mask

        for x, y in skill_coords:
            roi_v = self.ctx.bot.current_screen[y-10:y+10, x-10:x+10]
            if roi_v.size > 0:
                v_val = np.mean(cv2.cvtColor(roi_v, cv2.COLOR_BGR2HSV)[:, :, 2])
                if v_val < 60:
                    available_list.append(False)
                    continue
            
            roi_startY, roi_endY = max(0, y), min(h, y + CD_ROI_OFFSET_Y)
            roi_startX, roi_endX = max(0, x - CD_ROI_OFFSET_X), min(w, x + CD_ROI_OFFSET_X)
            roi = screen_gray[roi_startY:roi_endY, roi_startX:roi_endX]
            
            if tpl is not None and roi.shape[0] >= tpl.shape[0] and roi.shape[1] >= tpl.shape[1]:
                res = cv2.matchTemplate(roi, tpl, cv2.TM_CCORR_NORMED, mask=mask)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if np.isnan(max_val) or np.isinf(max_val):
                    max_val = 0.0
                if max_val >= 0.75:
                    available_list.append(False)
                    continue
            
            available_list.append(True)
        return available_list