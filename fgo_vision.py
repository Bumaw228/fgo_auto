import cv2
import numpy as np
import os

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
        
        role_str = "御主" if is_master else "從者"
        print(f"🔍 [視覺 2.0] 座標({x},{y}) {role_str} CD 得分: {max_val:.3f}")
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
                if max_val >= 0.75:
                    available_list.append(False)
                    continue
            
            available_list.append(True)
        return available_list