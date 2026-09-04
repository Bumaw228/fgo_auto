import os
import subprocess
import cv2
import sys  # 🚀 新增 sys 模組
import numpy as np
import re


def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

class FGOBot:
    def __init__(self, device_id="127.0.0.1:5555"):
        self.device_id = device_id
        
        # 🚀 關鍵修復：這裡原本是 __file__，現在換成 get_base_dir()
        self.base_dir = get_base_dir()
        #self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.sys_path = os.path.join(self.base_dir, "assets_system")
        self.friend_path = os.path.join(self.base_dir, "assets_friends")
        
        self.current_screen = None
        self.current_screen_gray = None
        self.template_cache = {}

        # 🌟 融合 ChatGPT 的神級架構：三層座標系
        self.raw_w = 1920
        self.raw_h = 1080
        self.tap_w = 1920
        self.tap_h = 1080
        
        os.makedirs(self.sys_path, exist_ok=True)
        os.makedirs(os.path.join(self.friend_path, "servants"), exist_ok=True)
        os.makedirs(os.path.join(self.friend_path, "craft_essences"), exist_ok=True)

        self.init_device()

    def adb_shell(self, command):
        cmd = f"adb -s {self.device_id} {command}"
        return subprocess.run(cmd, shell=True, capture_output=True)

    def init_device(self):
        """⭐ 獲取設備真實的觸控解析度 (防禦 MuMu 等模擬器顯示與觸控不一)"""
        result = self.adb_shell("shell wm size")
        out = result.stdout.decode()
        m = re.search(r'(\d+)x(\d+)', out)
        if m:
            w = int(m.group(1))
            h = int(m.group(2))
            # 強制轉成橫向
            if h > w:
                w, h = h, w
            self.tap_w = w
            self.tap_h = h
            print(f"[INIT] 觸控真實解析度 (Tap Resolution): {self.tap_w}x{self.tap_h}")

    def capture_screen(self):
        result = self.adb_shell("shell screencap -p")
        if not result.stdout:
            self.current_screen = None
            self.current_screen_gray = None
            return False
            
        img_data = result.stdout.replace(b'\r\n', b'\n')
        raw_img = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
        if raw_img is None: return False
        
        self.raw_h, self.raw_w = raw_img.shape[:2]
        
        # 畫布歸一化：永遠縮放回 1920x1080 給邏輯判斷
        if (self.raw_w, self.raw_h) != (1920, 1080):
            self.current_screen = cv2.resize(raw_img, (1920, 1080))
        else:
            self.current_screen = raw_img
            
        self.current_screen_gray = cv2.cvtColor(self.current_screen, cv2.COLOR_BGR2GRAY)
        return True

    def smart_click(self, x, y, duration=150):
        """🌟 融合版：三層虛擬座標轉譯器"""
        if self.raw_w == 0 or self.raw_h == 0: return

        # 1. 1080p 座標 -> 截圖相對座標
        rx = int((x / 1920.0) * self.raw_w)
        ry = int((y / 1080.0) * self.raw_h)
        
        # 2. 截圖座標 -> 設備觸控座標
        tx = int((rx / self.raw_w) * self.tap_w)
        ty = int((ry / self.raw_h) * self.tap_h)

        self.adb_shell(f"shell input swipe {tx} {ty} {tx} {ty} {duration}")

    def smart_swipe(self, x1, y1, x2, y2, duration=400):
        def convert(x, y):
            rx = int((x / 1920.0) * self.raw_w)
            ry = int((y / 1080.0) * self.raw_h)
            tx = int((rx / self.raw_w) * self.tap_w)
            ty = int((ry / self.raw_h) * self.tap_h)
            return tx, ty

        tx1, ty1 = convert(x1, y1)
        tx2, ty2 = convert(x2, y2)
        self.adb_shell(f"shell input swipe {tx1} {ty1} {tx2} {ty2} {duration}")

    #def _get_template_gray(self, full_path):
    #    if full_path not in self.template_cache:
    #        template_color = cv2.imdecode(np.fromfile(full_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    #        if template_color is None: return None
    #        self.template_cache[full_path] = cv2.cvtColor(template_color, cv2.COLOR_BGR2GRAY)
    #    return self.template_cache[full_path]
    
    def _get_template_gray(self, full_path):
        # 🚀 效能保護：如果快取超過 50 張圖片，自動清空釋放記憶體，避免 24H 掛機閃退
        if len(self.template_cache) > 50:
            self.template_cache.clear()
            print("♻️ [系統] 影像快取已滿，自動釋放記憶體！")

        if full_path not in self.template_cache:
            template_color = cv2.imdecode(np.fromfile(full_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if template_color is None: return None
            self.template_cache[full_path] = cv2.cvtColor(template_color, cv2.COLOR_BGR2GRAY)
        return self.template_cache[full_path]

    def find_in_folder(self, folder_type, filename, threshold=0.8, click_it=True):
        base_dir = self.sys_path if folder_type == 'system' else self.friend_path
        full_path = os.path.join(base_dir, filename)
        if not os.path.exists(full_path): return False
        return self.find_by_abspath(full_path, threshold, click_it)

    def find_by_abspath(self, full_path, threshold=0.8, click_it=True):
        if self.current_screen_gray is None: return None 
        template_gray = self._get_template_gray(full_path)
        if template_gray is None: return None

        res = cv2.matchTemplate(self.current_screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        # 🚀 救回我們的 Debug 監控器！(已加入幕間物語與自動編成的所有新圖片)
        filename = os.path.basename(full_path)
        if filename in [
            'ap_recovery_check.png', 'attack.png', 'battle_start.png', 'blue_apple.png', 
            'bond_ce_close.png', 'bond_screen.png', 'bronze_apple.png', 'close_btn.png', 
            'close_x.png', 'continue_battle.png', 'decide_btn.png', 'drop_screen.png', 
            'exp_screen.png', 'friend_request.png', 'gold_apple.png', 'menu_button.png', 
            'network_retry.png', 'next_btn.png', 'quest_start.png', 'refresh_btn.png', 
            'refresh_yes.png', 'reject_friend.png', 'silver_apple.png', 'sp_no_star.png', 
            'sp_use_star.png', 'sp_use_star_disabled.png', 'support_check.png', 
            'support_update.png', 'team_confirm.png', 'turn_1.png', 'turn_2.png', 'turn_3.png', 
            'select_target_text.png', 'order_change_btn.png', 'order_change_confirm_btn.png', 
            'retreat_btn.png', 'retreat_decide_btn.png', 'servant_detail_close_x.png',
            'mission_start.png', 'inventory_full_close.png', 'back_btn.png', 'fgo_icon.png',
            'class_all.png', 'class_saber.png', 'class_archer.png', 'class_lancer.png', 
            'class_rider.png', 'class_caster.png', 'class_assassin.png', 'class_berserker.png', 
            'class_extra.png', 'class_mix.png',
            # 👇 以下為新加入的圖片群
            'auto_form_btn1.png', 'auto_form_btn2.png', 'auto_form_btn3.png',
            'skip_confirm.png', 'go_to_story_stage.png', 'interlude_active.png', 
            'go_to_interlude_list.png', 'formation_limit.png', 'mandatory_slot.png', 
            'select_from_support.png'
        ]:
            print(f"🔍 正在掃描 [{filename}] | 目前相似度: {max_val:.3f} (門檻: {threshold})")
            # 🚀 效能優化：不再無腦狂印！只有找到，或相似度大於 0.7 時才顯示，避免 I/O 阻塞延遲！
            #if max_val >= threshold:
            #    print(f"✅ 發現目標 [{filename}] | 相似度: {max_val:.3f} (門檻: {threshold})")
            #elif max_val >= 0.7:
            #    print(f"👀 接近中 [{filename}] | 相似度: {max_val:.3f}")

        if max_val >= threshold:
            h, w = template_gray.shape[:2]
            tx = max_loc[0] + w // 2
            ty = max_loc[1] + h // 2
            if click_it:
                self.smart_click(tx, ty)
            return (tx, ty)
        return None 

    # 🚀 救回被 ChatGPT 誤刪的陣列核心！這支不見 3x3 助戰就死定了！
    def find_all_by_abspath(self, full_path, threshold=0.8):
        if self.current_screen_gray is None: return [] 
        template_gray = self._get_template_gray(full_path)
        if template_gray is None: return []

        res = cv2.matchTemplate(self.current_screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= threshold)
        
        h, w = template_gray.shape[:2]
        points = []
        for pt in zip(*loc[::-1]):
            tx = pt[0] + w // 2
            ty = pt[1] + h // 2
            if not any(abs(tx - px) < 20 and abs(ty - py) < 20 for px, py in points):
                points.append((tx, ty))
        return points