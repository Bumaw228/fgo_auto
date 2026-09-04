import time
import random
import cv2            
import numpy as np    
import os
from fgo_core import FGOBot

class FGOLogic:
    def __init__(self, config, status_callback, stop_callback):
        self.config = config
        self.update_status_cb = status_callback
        self.stop_cb = stop_callback
        
        self.running = True
        self.current_loop = 0
        self.bot = FGOBot(self.config['device_id'])
        
        # 視覺資產載入
        self.cooldown_tpl = None
        self.cooldown_mask = None
        self.master_cooldown_tpl = None
        self.master_cooldown_mask = None
        self.weak_tpl = None
        self.resist_tpl = None
        
        self._load_cooldown_assets()

    def _load_cooldown_assets(self):
        tpl_path = os.path.join(self.bot.sys_path, 'cooldown_text_tpl.png')
        mask_path = os.path.join(self.bot.sys_path, 'cooldown_text_mask.png')
        if os.path.exists(tpl_path) and os.path.exists(mask_path):
            self.cooldown_tpl = cv2.imread(tpl_path, cv2.IMREAD_GRAYSCALE)
            self.cooldown_mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        
        m_tpl_path = os.path.join(self.bot.sys_path, 'master_cooldown_text_tpl.png')
        m_mask_path = os.path.join(self.bot.sys_path, 'master_cooldown_text_mask.png')
        if os.path.exists(m_tpl_path) and os.path.exists(m_mask_path):
            self.master_cooldown_tpl = cv2.imread(m_tpl_path, cv2.IMREAD_GRAYSCALE)
            self.master_cooldown_mask = cv2.imread(m_mask_path, cv2.IMREAD_GRAYSCALE)

        # 預載入 AI 選卡模板
        weak_path = os.path.join(self.bot.sys_path, 'weak_text.png')
        resist_path = os.path.join(self.bot.sys_path, 'resist_text.png')
        if os.path.exists(weak_path): self.weak_tpl = cv2.imread(weak_path, cv2.IMREAD_GRAYSCALE)
        if os.path.exists(resist_path): self.resist_tpl = cv2.imread(resist_path, cv2.IMREAD_GRAYSCALE)

        # 🚀 載入 Skip 遮罩圖片
        skip_path = os.path.join(self.bot.sys_path, 'skip_btn_tpl.png')
        skip_mask_path = os.path.join(self.bot.sys_path, 'skip_btn_mask.png')
        if os.path.exists(skip_path) and os.path.exists(skip_mask_path):
            self.skip_tpl = cv2.imread(skip_path, cv2.IMREAD_GRAYSCALE)
            self.skip_mask = cv2.imread(skip_mask_path, cv2.IMREAD_GRAYSCALE)

    # 🚀 專屬的遮罩 Skip 按鈕偵測 (電影黑邊免疫版)
    def check_skip_button(self):
        if self.skip_tpl is None or self.skip_mask is None: return "NONE"
        if not self.bot.capture_screen(): return "NONE"
        
        screen_gray = self.bot.current_screen_gray
        h, w = screen_gray.shape
        roi = screen_gray[0:150, 1500:w] # 只切出右上角
        
        if roi.shape[0] < self.skip_tpl.shape[0] or roi.shape[1] < self.skip_tpl.shape[1]:
            return "NONE"
            
        # ==========================================
        # 🚀 升級防禦：不要依賴 OpenCV 的 max_val 來判斷黑屏，改用標準差！
        # 如果整個右上角的像素幾乎沒有變化 (純黑)，才直接放棄掃描
        # ==========================================
        if np.std(roi) < 3.0: 
            return "NONE"
            
        # 安全確認不是純黑轉場後，才執行模板匹配
        res = cv2.matchTemplate(roi, self.skip_tpl, cv2.TM_CCORR_NORMED, mask=self.skip_mask)
        _, max_val, max_loc, _ = cv2.minMaxLoc(res)

        # 避免極端數學異常
        if np.isnan(max_val): 
            return "NONE"
            
        # ==========================================
        # 🚀 拔除 max_val > 1.1 的限制！
        # 因為在黑底白字的情況下，CCORR_NORMED 演算法有時候會因為遮罩而稍微大於 1.0
        # 既然我們上面已經用 np.std 防禦了全黑畫面，這裡就不需要再卡死分數上限了！
        # ==========================================
        
        real_x = 1500 + max_loc[0]
        real_y = max_loc[1]
        th, tw = self.skip_tpl.shape
        
        # 確保不要切出畫面外
        if real_y + th > h or real_x + tw > w:
            return "NONE"
            
        patch = self.bot.current_screen[real_y:real_y+th, real_x:real_x+tw]
        
        v_val = 0
        if patch.size > 0:
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
            v_val = np.max(hsv[:, :, 2])
            
        # 👀 全天候雷達
        print(f"👀 [SKIP 雷達] 相似度: {max_val} | 最高亮度: {v_val:.0f}")
        
        # ==========================================
        # 🚀 最終防線破解：擁抱 inf！
        # 在電影黑邊模式下，黑底白字會算出 inf。
        # 所以只要分數大於 0.935「或者是 inf」，我們都交給亮度來做最後裁決！
        # ==========================================
        is_high_score = (max_val >= 0.921) or np.isinf(max_val)
        
        if is_high_score:
            if v_val > 180: 
                return "READY"
            elif v_val > 110:
                print("⚠️ SKIP 處於暗化狀態，將執行選項連點。")
                return "DARK"
            else:
                return "NONE"
                
        return "NONE"

    def click(self, x, y, times=1, duration=120):
        for _ in range(times): self.bot.smart_click(x, y, duration)

    def swipe(self, x1, y1, x2, y2, duration=400):
        self.bot.smart_swipe(x1, y1, x2, y2, duration)

    def update_status(self, text, fg="blue"):
        self.update_status_cb(text, fg)

    def smart_sleep(self, seconds):
        end_time = time.time() + seconds
        while time.time() < end_time:
            if not self.running: return False 
            time.sleep(0.1)
        return True

    def reset_battle_state_if_needed(self):
        print("🔄 [系統初始化] 執行戰鬥狀態重置 (確保御主選單與目標視窗皆為關閉)...")
        self.bot.capture_screen()
        if self.bot.find_in_folder('system', 'servant_detail_close_x.png', click_it=True):
            print("✅ 偵測到角色詳情已在開啟狀態，直接關閉洗白 UI！")
            self.smart_sleep(1.0)
            return

        self.click(705, 670, times=3, duration=50) 
        self.smart_sleep(1.5) 
        
        timeout = time.time() + 3.0
        while time.time() < timeout and self.running:
            self.bot.capture_screen()
            if self.bot.find_in_folder('system', 'servant_detail_close_x.png', click_it=True):
                print("✅ 成功關閉角色詳情，戰鬥 UI 已重置為乾淨狀態！")
                self.smart_sleep(1.0)
                return
            self.smart_sleep(0.2)
        print("⚠️ 未偵測到角色詳情專屬叉叉，假設畫面已是乾淨狀態。")

    def get_skill_color_stats(self, x, y):
        if not self.bot.capture_screen(): return 255, 255
        img = self.bot.current_screen
        roi = img[y-20:y+20, x-20:x+20]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        return np.mean(hsv[:, :, 1]), np.mean(hsv[:, :, 2])

    def check_skill_cooldown_visual(self, x, y, is_master=False):
        if is_master:
            tpl, mask = self.master_cooldown_tpl, self.master_cooldown_mask
        else:
            tpl, mask = self.cooldown_tpl, self.cooldown_mask

        if tpl is None or mask is None: return False 
        if not self.bot.capture_screen(): return False
        
        screen_gray = self.bot.current_screen_gray
        h, w = screen_gray.shape
        
        roi_startY = max(0, y)
        roi_endY = min(h, y + 60)
        roi_startX = max(0, x - 55)
        roi_endX = min(w, x + 55)
        roi = screen_gray[roi_startY:roi_endY, roi_startX:roi_endX]
        
        if roi.shape[0] < tpl.shape[0] or roi.shape[1] < tpl.shape[1]: return False

        res = cv2.matchTemplate(roi, tpl, cv2.TM_CCORR_NORMED, mask=mask)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        
        role_str = "御主" if is_master else "從者"
        print(f"🔍 [視覺 2.0] 座標({x},{y}) {role_str} CD 得分: {max_val:.3f}")
        
        if max_val >= 0.75:
            return True
        return False

    def handle_ap_recovery(self):
        apple_type = self.config['apple_mode']
        if apple_type == "不自動回體":
            self.update_status("狀態：AP 不足，停止運行", fg="red")
            self.running = False
            return False

        apple_map = {"銅蘋果": "bronze_apple.png", "青銅蘋果": "blue_apple.png", "銀蘋果": "silver_apple.png", "金蘋果": "gold_apple.png"}
        target_apple = apple_map.get(apple_type)

        if apple_type in ["銅蘋果", "青銅蘋果"]:
            self.swipe(960, 800, 960, 300, 500)
            if not self.smart_sleep(1.5): return False
            self.bot.capture_screen() 

        if self.bot.find_in_folder('system', target_apple):
            print(f"✅ 已點擊蘋果: {target_apple}")
            self.smart_sleep(1.5) 
            
            # 🚀 升級：給予 15 秒的耐心等待伺服器回應
            timeout = time.time() + 15.0
            while time.time() < timeout and self.running:
                self.bot.capture_screen() 
                if self.bot.find_in_folder('system', 'decide_btn.png', click_it=True):
                    print("✅ 確認吃蘋果！")
                    self.smart_sleep(2.5) 
                    return True
                self.click(1280, 830, duration=50)
                self.smart_sleep(1.5)
                self.bot.capture_screen() 
                if not self.bot.find_in_folder('system', 'ap_recovery_check.png', click_it=False):
                    return True
            self.update_status("狀態：吃蘋果卡住，停止運行", fg="red")
            self.running = False
            return False
        return False

    def wait_for_target_window(self, timeout_sec=3.0):
        timeout = time.time() + timeout_sec
        while time.time() < timeout and self.running:
            self.bot.capture_screen()
            if self.bot.find_in_folder('system', 'select_target_text.png', click_it=False):
                return True
            self.smart_sleep(0.1)
        print("⚠️ 警告：等待目標視窗超時，強制放行盲點！")
        return False
            
    def wait_attack_and_skip(self, timeout_sec=15.0, do_click=True):
        if not self.running: return
        timeout = time.time() + timeout_sec
        while time.time() < timeout and self.running:
            if do_click:
                self.click(1750, 150, duration=50) 
            
            self.bot.capture_screen()
            if self.bot.find_in_folder('system', 'attack.png', click_it=False):
                self.smart_sleep(0.2 if not do_click else 0.1) 
                return
            self.smart_sleep(0.05)

    def smart_cast_skill(self, x, y, modifier=None, target_pos=None, is_master_skill=False):
        skill_mode = self.config.get('skill_mode', '智慧安全')
        extreme_sleep = float(self.config.get('extreme_sleep', 2.5))
        role_str = "御主" if is_master_skill else "從者"
        mod_msg = f" (修飾符: {modifier})" if modifier else ""
        print(f"📊 [技能執行] 準備點擊 {role_str} 座標 ({x}, {y}){mod_msg} | 模式: {skill_mode}")
        
        if skill_mode == "智慧安全":
            s_before, v_before = self.get_skill_color_stats(x, y)
            print(f"📊 [{role_str}技能檢測] 亮度: {v_before:.1f}, 飽和度: {s_before:.1f}")
            
            is_cd = False
            if self.check_skill_cooldown_visual(x, y, is_master_skill):
                is_cd = True
                print(f"⏩ [視覺 2.0] 🎉 精準攔截！確定{role_str}技能有「剩餘」二字，CD 中！")
            
            if not is_cd and v_before < 60:
                is_cd = True
                print(f"⏩ [HSV 輔助] 技能極度灰暗 (V={v_before:.1f})，判定為空殼！")

            if is_cd:
                print(f"⏩ 偵測到{role_str}技能處於 CD 狀態，自動跳過！")
                if is_master_skill:
                    self.click(1792, 472) 
                    self.smart_sleep(0.4) 
                else:
                    self.click(1750, 150, times=2, duration=50)
                return
        else:
            print(f"⚡ [{skill_mode}] 已關閉 CD 偵測，強制點擊{role_str}技能！")

        max_retries = 2 if skill_mode != "極限盲操" else 1
        
        for attempt in range(max_retries):
            if not self.running: return
            self.click(x, y)
            
            if modifier:
                self.smart_sleep(0.4) 
                timeout = time.time() + 1.5 
                while time.time() < timeout and self.running:
                    self.bot.capture_screen() 
                    if modifier == "star":
                        pos = self.bot.find_in_folder('system', 'sp_use_star.png', click_it=False)
                        if pos:
                            s, v = self.get_skill_color_stats(pos[0], pos[1])
                            print(f"📊 [耗星按鈕檢測] 亮度: {v:.1f}, 飽和度: {s:.1f}")
                            if v > 120:
                                print("✅ 星星充足 (亮度達標)，執行耗星！")
                                self.click(pos[0], pos[1])
                                self.smart_sleep(0.2)
                                break
                            else:
                                print("⚠️ 耗星按鈕反灰 (星星不足)，啟動降級：改點不耗星！")
                                if self.bot.find_in_folder('system', 'sp_no_star.png', click_it=True):
                                    self.smart_sleep(0.2)
                                    break
                    elif modifier == "nostar":
                        if self.bot.find_in_folder('system', 'sp_no_star.png', click_it=True):
                            self.smart_sleep(0.2); break
                    self.smart_sleep(0.1)

            if target_pos:
                target_ready = False
                if skill_mode == "智慧安全":
                    target_ready = self.wait_for_target_window(timeout_sec=2.5)
                else:
                    self.smart_sleep(0.3) 
                    target_ready = True
                
                if target_ready:
                    tx, ty = target_pos
                    self.click(tx, ty)
                    self.smart_sleep(0.25)
                    
                    if skill_mode == "極限盲操":
                        print(f"⏩ [極限盲操] 執行完畢，狂點加速字卡並盲等 {extreme_sleep} 秒...")
                        end_time = time.time() + extreme_sleep
                        while time.time() < end_time and self.running:
                            self.click(1750, 150, duration=50) 
                        return 

                    timeout = time.time() + 2.0
                    skill_activated = False
                    while time.time() < timeout and self.running:
                        self.click(1750, 150, duration=50) 
                        self.bot.capture_screen()
                        if not self.bot.find_in_folder('system', 'attack.png', click_it=False):
                            skill_activated = True
                            break
                        self.smart_sleep(0.05)
                        
                    if skill_activated:
                        print(f"✅ Attack 消失，確認{role_str}技能已施放！啟動連點加速...")
                        self.wait_attack_and_skip(do_click=True) 
                        return
                    else:
                        print(f"⚠️ Attack 未消失 (可能吞 Tap)，重試 {attempt+1}/{max_retries}...")
                else:
                    print(f"⚠️ 未偵測到目標視窗 (可能在 CD 或吞 Tap)，重試 {attempt+1}/{max_retries}...")
            else:
                self.smart_sleep(0.15)
                
                if skill_mode == "極限盲操":
                    print(f"⏩ [極限盲操] 無對象執行完畢，狂點加速字卡並盲等 {extreme_sleep} 秒...")
                    end_time = time.time() + extreme_sleep
                    while time.time() < end_time and self.running:
                        self.click(1750, 150, duration=50) 
                    return 

                timeout = time.time() + 2.0
                skill_activated = False
                while time.time() < timeout and self.running:
                    self.click(1750, 150, duration=50) 
                    self.bot.capture_screen()
                    if not self.bot.find_in_folder('system', 'attack.png', click_it=False):
                        skill_activated = True
                        break
                    self.smart_sleep(0.05)
                
                if skill_activated:
                    print(f"✅ Attack 消失，確認{role_str}技能已施放！啟動連點加速...")
                    self.wait_attack_and_skip(do_click=True)
                    return
                else:
                    print(f"⚠️ Attack 1.5 秒內未消失 (可能吞 Tap 或卡頓)，重試 {attempt+1}/{max_retries}...")
            self.smart_sleep(0.5)

        if skill_mode != "極限盲操":
            print(f"⏩ {role_str}技能重試達上限，判定為已施放或在CD中，跳過！")
            if is_master_skill:
                self.click(1792, 472) 
                self.smart_sleep(0.6) 
            else:
                self.click(1750, 150, times=2, duration=50)
            self.wait_attack_and_skip(do_click=True)
    
    # ==========================================
    # 🚀 全局技能辨識優化版 (不重複截圖)
    # ==========================================
    def check_skill_available_batch(self, is_master=False):
        """一次回傳所有技能的可點擊狀態 (True/False 列表)"""
        # 🚀 修正：從者技能是 9 個，御主是 3 個
        if not self.bot.capture_screen(): return [False] * (3 if is_master else 9)
        
        screen_gray = self.bot.current_screen_gray
        h, w = screen_gray.shape
        
        # 定義技能座標 (1-9)
        skill_coords = [
            (111, 871), (244, 871), (376, 871),   # 從者1
            (586, 871), (716, 871), (847, 871),   # 從者2
            (1060, 871), (1191, 871), (1324, 871) # 從者3
        ]
        if is_master:
            skill_coords = [(1360, 468), (1493, 468), (1626, 468)] # 御主技能

        available_list = []
        tpl = self.master_cooldown_tpl if is_master else self.cooldown_tpl
        mask = self.master_cooldown_mask if is_master else self.cooldown_mask

        for x, y in skill_coords:
            # 1. 亮度檢查 (HSV 快速排除)
            roi_v = self.bot.current_screen[y-10:y+10, x-10:x+10]
            if roi_v.size > 0:
                v_val = np.mean(cv2.cvtColor(roi_v, cv2.COLOR_BGR2HSV)[:, :, 2])
                if v_val < 60: # 太暗一定是 CD
                    available_list.append(False)
                    continue
            
            # 2. 視覺「剩餘」文字檢查
            roi_startY, roi_endY = max(0, y), min(h, y + 60)
            roi_startX, roi_endX = max(0, x - 55), min(w, x + 55)
            roi = screen_gray[roi_startY:roi_endY, roi_startX:roi_endX]
            
            if tpl is not None and roi.shape[0] >= tpl.shape[0] and roi.shape[1] >= tpl.shape[1]:
                res = cv2.matchTemplate(roi, tpl, cv2.TM_CCORR_NORMED, mask=mask)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val >= 0.75: # 發現「剩餘」
                    available_list.append(False)
                    continue
            
            available_list.append(True) # 通過檢查，可以使用
        return available_list

    # ==========================================
    # 🚀 動態戰鬥同步監控 (取代固定 Sleep)
    # ==========================================
    def wait_for_next_turn_dynamic(self):
        """點擊加速區並監控戰鬥何時結束"""
        self.update_status("狀態：等待攻擊結束 (加速跳過中...)")
        
        # 🚀 這裡修改：從 40.0 改成 150.0 秒
        # 給足夠的時間讓敵我雙方互放寶具跟平A，反正看到 Attack 就會秒退，設長一點沒關係
        timeout = time.time() + 150.0 
        
        while time.time() < timeout and self.running:
            # 點擊右上方加速區 (1750, 150)
            self.click(1750, 150, duration=50)
            
            # 每隔 0.5 秒檢查一次畫面
            self.smart_sleep(0.4)
            self.bot.capture_screen()
            
            # 檢查是否回到選卡主畫面 (Attack 按鈕)
            if self.bot.find_in_folder('system', 'attack.png', click_it=False):
                print("✅ 偵測到 Attack，進入下一回合")
                return "BATTLE"
            
            # 檢查是否進入結算畫面
            if any(self.bot.find_in_folder('system', img) for img in ['bond_screen.png', 'exp_screen.png', 'next_btn.png']):
                print("🎉 偵測到戰鬥結束，進入結算")
                return "RESULT"
            
            # 如果發現防呆返回鍵 (可能發生軟鎖死)
            if self.bot.find_in_folder('system', 'back_btn.png', click_it=False):
                return "BATTLE"

        return "INIT"

    # ==========================================
    # 🚀 AI 智能選卡模組 (RGB 色彩 + 剋制偵錯 + 防當機版)
    # ==========================================
    def select_battle_cards(self, current_wave=99):
        is_ai_mode = self.config.get('ai_card_mode', False)
        is_auto_np = self.config.get('auto_np_mode', True)
        priority_str = self.config.get('card_priority', "無")

        # 🚀 關鍵判斷：只有在「隨機模式」或「劇本已打完的殘局」才允許自動點寶具
        script_len = len(self.config.get('script_data', []))
        can_auto_np = (self.config['battle_mode'] == "random") or (current_wave >= script_len)

        if not is_ai_mode:
            if is_auto_np and can_auto_np:
                for nx, ny in [(605, 300), (960, 300), (1315, 300)]:
                    self.click(nx, ny); self.smart_sleep(0.15)
            cards = [(195, 755), (580, 755), (960, 755), (1345, 755), (1735, 755)]
            random.shuffle(cards)
            for i in range(3): self.click(cards[i][0], cards[i][1]); self.smart_sleep(0.25)
            self.smart_sleep(0.2); self.click(cards[3][0], cards[3][1]) 
            return

        print(f"🧠 [AI 決策] 啟動智能選卡！(戰略: {priority_str})")
        
        # 🚀 視覺 2.0：智能寶具決策 (拒絕盲點)
        if is_auto_np and can_auto_np:
            print("🚀 [智能寶具] 掃描寶具卡是否就緒...")
            np_cards = [(605, 300), (960, 300), (1315, 300)]
            np_clicked = False
            
            # 拍照一次，分析三個寶具位置的亮度
            self.bot.capture_screen()
            img = self.bot.current_screen
            
            for i, (nx, ny) in enumerate(np_cards):
                # 抓取寶具卡片中心的 40x40 像素區域
                roi = img[ny-20:ny+20, nx-20:nx+20]
                if roi.size > 0:
                    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                    v_val = np.mean(hsv[:, :, 2]) # 取得 V (亮度) 平均值
                    
                    # 🚀 這裡升級：將門檻從 100 提高到 140，完美過濾掉 103 這種假性發光！
                    if v_val > 140: 
                        print(f"  ✨ 發現 [從者 {i+1}] 寶具就緒 (亮度: {v_val:.0f})！執行點擊。")
                        self.click(nx, ny)
                        self.smart_sleep(0.15)
                        np_clicked = True
                    else:
                        print(f"  ❌ [從者 {i+1}] 寶具未就緒 (亮度: {v_val:.0f})。")
            
            if not np_clicked:
                print("  ⚠️ 目前無可用寶具，直接進入指令卡決策。")
            
        color_order = [] if priority_str == "無" else [c.strip() for c in priority_str.split('>')]
        cards = [(195, 755), (580, 755), (960, 755), (1345, 755), (1735, 755)]
        card_scores = []
        self.bot.capture_screen()
        screen_color = self.bot.current_screen
        screen_gray = self.bot.current_screen_gray
        h, w = screen_gray.shape

        for idx, (cx, cy) in enumerate(cards):
            score = 0
            
            # ==========================================
            # 🎨 色彩分析 (恢復 Print 報告)
            # ==========================================
            roi_c = screen_color[min(h, cy+50):min(h, cy+120), max(0, cx-60):min(w, cx+60)]
            card_color = "未知"
            if roi_c.size > 0:
                b, g, r = np.mean(roi_c, axis=(0, 1))
                card_color = "紅" if r>b and r>g else "藍" if b>r and b>g else "綠"
                if card_color in color_order: 
                    score += (30 - color_order.index(card_color)*10)
                
                # 🚀 復活的色彩光譜雷達
                print(f"  [Debug-Color] 卡片 {idx+1} | R:{r:.0f}, G:{g:.0f}, B:{b:.0f} => [{card_color}卡]")
            
            # ==========================================
            # ⚔️ 剋制分析 (恢復 Print 報告)
            # ==========================================
            roi_g = screen_gray[max(0, cy-250):max(0, cy+50), max(0, cx-120):min(w, cx+170)]
            weak_score, resist_score = 0.0, 0.0
            
            if self.weak_tpl is not None:
                res_w = cv2.matchTemplate(roi_g, self.weak_tpl, cv2.TM_CCOEFF_NORMED)
                weak_score = np.max(res_w)
            if self.resist_tpl is not None:
                res_r = cv2.matchTemplate(roi_g, self.resist_tpl, cv2.TM_CCOEFF_NORMED)
                resist_score = np.max(res_r)

            # 🚀 復活的計分雷達
            if weak_score > 0.7 and weak_score > resist_score:
                score += 500
                print(f"  👉 卡片 {idx+1} [{card_color}卡]: 發現 WEAK！ (總分: {score})")
            elif resist_score > 0.7 and resist_score > weak_score:
                score -= 500
                print(f"  👉 卡片 {idx+1} [{card_color}卡]: 發現 RESIST... (總分: {score})")
            else:
                print(f"  👉 卡片 {idx+1} [{card_color}卡]: 普通攻擊 (總分: {score})")

            card_scores.append({'score': score, 'pos': (cx, cy)})

        print("🎯 [AI 決策] 算牌完畢，優先打出最強卡片 (1名 -> 2名 -> 3名)")
        card_scores.sort(key=lambda x: x['score'], reverse=True)
        best_3 = card_scores[:3]
        
        # 🚀 修正：移除 reversed，確保有寶具時，最強卡片不會被擠掉
        for card in best_3: 
            self.click(card['pos'][0], card['pos'][1])
            self.smart_sleep(0.25)
            
        self.smart_sleep(0.3)
        self.click(card_scores[3]['pos'][0], card_scores[3]['pos'][1])

    def execute_script_from_list(self, wave_idx):
        cmds = self.config['script_data'][wave_idx]
        if not cmds: return False 
        skill_mode = self.config.get('skill_mode', '智慧安全')
        
        enemies = [None, (65, 65), (440, 65), (815, 65)]
        skills = [None, (111, 871), (244, 871), (376, 871), (586, 871), (716, 871), (847, 871), (1060, 871), (1191, 871), (1324, 871)]
        targets = [None, (485, 590), (965, 590), (1425, 590)]
        nps = [None, (605, 300), (960, 300), (1315, 300)]
        master_btn = (1792, 472) 
        m_skills = [None, (1360, 468), (1493, 468), (1626, 468)]
        o_front = [None, (205, 520), (500, 520), (805, 520)]
        o_back = [None, (1095, 520), (1400, 520), (1695, 520)]
        order_change_confirm_btn = (963, 940) 
        
        attack_opened = False 

        for c in cmds:
            if not self.running: break
            
            if c.startswith('E'):
                idx = int(c[1])
                ex, ey = enemies[idx]
                self.click(ex, ey)
                self.smart_sleep(0.4) 
                self.wait_attack_and_skip(timeout_sec=5.0, do_click=True)

            elif c.startswith('N'):
                if not attack_opened:
                    if skill_mode == "極限盲操":
                        print("🛡️ [極限防撞車] 準備施放寶具，強制同步時間軸 (靜靜掃描不狂點)...")
                        self.wait_attack_and_skip(timeout_sec=8.0, do_click=False)
                        self.smart_sleep(0.2)
                        
                    self.smart_sleep(0.1) 
                    self.click(1650, 920)
                    if not self.smart_sleep(1.0): break 
                    attack_opened = True
                
                idx = int(c[1])
                self.click(nps[idx][0], nps[idx][1])
                self.smart_sleep(0.15) 
                
            elif c.startswith('S'):
                target_pos = None
                modifier = None
                
                parts = c.split('-')
                base_cmd = parts[0]
                if len(parts) > 1:
                    target_pos = targets[int(parts[1])]
                    
                if '_' in base_cmd:
                    s_str, modifier = base_cmd.split('_')
                    s_idx = int(s_str[1:])
                else:
                    s_idx = int(base_cmd[1:])

                self.smart_cast_skill(
                    x = skills[s_idx][0], 
                    y = skills[s_idx][1], 
                    modifier = modifier, 
                    target_pos = target_pos
                )

            elif c.startswith('M'):
                if skill_mode == "極限盲操":
                    print("🛡️ [極限防撞車] 準備開御主選單，強制同步時間軸 (靜靜掃描不狂點)...")
                    self.wait_attack_and_skip(timeout_sec=8.0, do_click=False)
                    self.smart_sleep(0.2)
                    
                self.click(*master_btn)
                if not self.smart_sleep(1.0): break 
                
                if '-' in c:
                    m_idx, t_idx = map(int, c[1:].split('-'))
                    target_pos = targets[t_idx]
                else:
                    m_idx = int(c[1:])
                    target_pos = None
                    
                self.smart_cast_skill(
                    x = m_skills[m_idx][0], 
                    y = m_skills[m_idx][1], 
                    target_pos = target_pos,
                    is_master_skill = True 
                )

            elif c.startswith('O'):
                if skill_mode == "極限盲操":
                    print("🛡️ [極限防撞車] 準備開御主選單(換人)，強制同步時間軸 (靜靜掃描不狂點)...")
                    self.wait_attack_and_skip(timeout_sec=8.0, do_click=False)
                    self.smart_sleep(0.2)

                self.click(*master_btn)
                if not self.smart_sleep(1.0): break 

                is_order_change_cd = False
                s_before, v_before = self.get_skill_color_stats(m_skills[3][0], m_skills[3][1])
                
                if skill_mode == "智慧安全":
                    print(f"📊 [換人技能檢測] 亮度: {v_before:.1f}, 飽和度: {s_before:.1f}")
                    if self.check_skill_cooldown_visual(m_skills[3][0], m_skills[3][1], is_master=True):
                        is_order_change_cd = True
                        print(f"⏩ [視覺 2.0] 🎉 精準攔截！換人技能 CD 中！")
                    elif v_before < 60:
                        is_order_change_cd = True
                        print(f"⏩ [HSV 輔助] 換人技能極度灰暗 (V={v_before:.1f})，判定為空殼！")

                if is_order_change_cd:
                    print("⏩ 偵測到換人技能處於 CD 狀態，自動跳過！")
                    self.click(1792, 472) 
                    self.smart_sleep(0.6) 
                    continue 

                self.click(m_skills[3][0], m_skills[3][1])
                if not self.smart_sleep(1.2): break 
                
                _, f, b = c.split('-')
                front_pos = o_front[int(f)]
                back_pos = o_back[int(b)]
                cx, cy = order_change_confirm_btn 
                
                self.click(front_pos[0], front_pos[1])
                if not self.smart_sleep(0.3): break
                self.click(back_pos[0], back_pos[1])
                if not self.smart_sleep(0.3): break
                self.click(cx, cy) 
                
                self.smart_sleep(1.0) 
                
                if self.bot.find_in_folder('system', 'order_change_confirm_btn.png', click_it=False):
                    print("⚠️ 換人失敗，啟動階段 1 搶救...")
                    self.click(front_pos[0], front_pos[1])
                    self.smart_sleep(0.3)
                    self.click(cx, cy)
                    self.smart_sleep(1.0)
                    if self.bot.find_in_folder('system', 'order_change_confirm_btn.png', click_it=False):
                        self.click(front_pos[0], front_pos[1]) 
                        self.smart_sleep(0.3)
                        self.click(back_pos[0], back_pos[1]) 
                        self.smart_sleep(0.3)
                        self.click(cx, cy)
                        self.smart_sleep(1.0)
                        if self.bot.find_in_folder('system', 'order_change_confirm_btn.png', click_it=False):
                            self.click(back_pos[0], back_pos[1]) 
                            self.smart_sleep(0.3)
                            self.click(front_pos[0], front_pos[1]) 
                            self.smart_sleep(0.3)
                            self.click(back_pos[0], back_pos[1]) 
                            self.smart_sleep(0.3)
                            self.click(cx, cy)
                            self.smart_sleep(1.0)
                            if self.bot.find_in_folder('system', 'order_change_confirm_btn.png', click_it=False):
                                print("❌ 嚴重錯誤：換人模組徹底卡死！")
                
                if not self.smart_sleep(3.0): break 
                self.wait_attack_and_skip(timeout_sec=20.0, do_click=True)

            self.smart_sleep(0.1)
            
        return attack_opened

    def run_logic(self):
        bot = self.bot
        self.update_status("狀態：腳本啟動，進行全局畫面掃描...")
        self.current_state = "INIT"  
        self.current_loop = 1
        current_wave = 0
        swipe_count = 0  
        class_images = {
            "ALL": "class_all.png", "Saber": "class_saber.png", 
            "Archer": "class_archer.png", "Lancer": "class_lancer.png", 
            "Rider": "class_rider.png", "Caster": "class_caster.png", 
            "Assassin": "class_assassin.png", "Berserker": "class_berserker.png", 
            "Extra": "class_extra.png", "Mix": "class_mix.png"
        }
        team_dot_y = 75
        team_dot_start_x = 790
        team_dot_gap = 37

        while self.running:
            try:
                if not bot.capture_screen():
                    self.smart_sleep(0.5)
                    continue

                if bot.find_in_folder('system', 'inventory_full_close.png', click_it=True):
                    print("⚠️ 偵測到「倉庫已滿」警告彈窗！為求安全，已點擊關閉並強制停止腳本！")
                    self.update_status("⛔ 狀態：倉庫已滿，腳本已停止！", fg="red")
                    self.running = False
                    break

                if bot.find_in_folder('system', 'network_retry.png', click_it=False) or \
                   bot.find_in_folder('system', 'close_x.png', click_it=False) or \
                   bot.find_in_folder('system', 'fgo_icon.png', click_it=False):
                    print("⚠️ 觸發全域異常防護 (斷線/閃退)，腳本緊急停止。")
                    self.update_status("⚠️ 狀態：發生異常，已停止！", fg="red")
                    break

                if self.current_state == "INIT":
                    self.update_status("狀態：全局掃描，判斷當前畫面...")
                    
                    # 🚀 第一步：全域判斷 SKIP (改完 A 之後，這裡會變得很靈敏)
                    skip_status = self.check_skip_button()
                    if self.config.get('interlude_mode', False) and skip_status in ["READY", "DARK"]:
                        self.current_state = "STORY"
                        continue
                        
                    if bot.find_in_folder('system', 'attack.png', click_it=False) or \
                       bot.find_in_folder('system', 'select_target_text.png', click_it=False) or \
                       bot.find_in_folder('system', 'order_change_btn.png', click_it=False) or \
                       bot.find_in_folder('system', 'servant_detail_close_x.png', click_it=False):
                        self.current_state = "BATTLE"
                        self.reset_battle_state_if_needed() 
                    elif bot.find_in_folder('system', 'back_btn.png', click_it=True):
                        print("✅ [防呆] 啟動時卡在選卡畫面，已自動點擊返回洗白狀態！")
                        self.current_state = "BATTLE"
                        self.smart_sleep(1.0)
                    # ==========================================
                    # 🚀 萬用獎勵畫面攔截 (請點擊畫面)
                    # ==========================================
                    elif bot.find_in_folder('system', 'reward_screen.png', click_it=False):
                        print("💎 [INIT] 偵測到通關報酬/強化畫面！執行關閉...")
                        self.click(65, 65, duration=50) # 點擊左上角安全區關閉
                        self.smart_sleep(1.5)
                        continue
                    # 🚀 加入 new_interlude_unlocked.png 聯合判斷
                    elif bot.find_in_folder('system', 'servant_data_update.png', threshold=0.85, click_it=False) or \
                         bot.find_in_folder('system', 'new_interlude_unlocked.png', threshold=0.85, click_it=False):
                        print("💎 [INIT] 偵測到資料更新或新幕間開放！尋找並點擊關閉按鈕...")
                        if bot.find_in_folder('system', 'close_btn.png', click_it=True):
                            self.smart_sleep(1.5)
                        else:
                            self.smart_sleep(0.5) 
                        continue
                    elif bot.find_in_folder('system', 'support_check.png', click_it=False):
                        self.current_state = "SUPPORT"
                        swipe_count = 0
                    elif bot.find_in_folder('system', 'quest_start.png', click_it=False) or \
                         bot.find_in_folder('system', 'battle_start.png', click_it=False) or \
                         bot.find_in_folder('system', 'mission_start.png', click_it=False) or \
                         bot.find_in_folder('system', 'team_confirm.png', click_it=False) or \
                         bot.find_in_folder('system', 'auto_form_btn1.png', click_it=False): # 🚀 新增防呆：看到自動編隊按鈕，代表在 TEAM_SELECT
                        self.current_state = "TEAM_SELECT"
                    elif bot.find_in_folder('system', 'bond_screen.png', click_it=False) or \
                         bot.find_in_folder('system', 'exp_screen.png', click_it=False) or \
                         bot.find_in_folder('system', 'drop_screen.png', click_it=False) or \
                         bot.find_in_folder('system', 'next_btn.png', click_it=False) or \
                         bot.find_in_folder('system', 'bond_ce_close.png', click_it=False) or \
                         bot.find_in_folder('system', 'continue_battle.png', click_it=False):
                        self.current_state = "RESULT"
                    elif bot.find_in_folder('system', 'retreat_btn.png', click_it=False):
                        self.current_state = "DEFEAT"
                    elif bot.find_in_folder('system', 'menu_button.png', click_it=False) or \
                         bot.find_in_folder('system', 'ap_recovery_check.png', click_it=False) or \
                         bot.find_in_folder('system', 'interlude_active.png', click_it=False) or \
                         bot.find_in_folder('system', 'go_to_interlude_list.png', click_it=False): 
                        self.current_state = "IDLE"
                    else:
                        if self.config.get('interlude_mode', False) and np.std(bot.current_screen_gray) >= 5:
                            # ❌ 絕對不要點 (65, 65)，會點到對話紀錄！
                            # ✅ 改點 (960, 50) 安全區喚醒 SKIP 按鈕
                            print("🌙 [INIT] 畫面無已知 UI，點擊天花板喚醒 UI...")
                            self.click(65, 65, duration=50)
                            self.smart_sleep(0.5)
                        else:
                            self.smart_sleep(0.5)
                        
                    if self.current_state != "INIT":
                        print(f"✅ 全局掃描完畢，精準切入狀態：{self.current_state}")
                    continue

                elif self.current_state == "STORY":
                    self.update_status("狀態：劇情播放中...")
                    
                    skip_status = self.check_skip_button()
                    
                    if skip_status == "READY":
                        print("✨ 偵測到 SKIP 鈕亮起，執行跳過...")
                        self.click(1798, 61, duration=50) 
                        
                        confirm_found = False
                        timeout = time.time() + 2.5
                        while time.time() < timeout and self.running:
                            self.smart_sleep(0.3)
                            bot.capture_screen()
                            if bot.find_in_folder('system', 'skip_confirm.png', click_it=True):
                                print("✅ 已確認跳過劇情")
                                self.smart_sleep(3.0)
                                confirm_found = True
                                break
                                
                        if not confirm_found:
                            print("⚠️ 點擊了 SKIP 但沒看到確認視窗 (可能動畫太慢)，下回合重試...")
                            
                    elif skip_status == "DARK":
                        print("🌙 Skip 處於暗化狀態，執行選項連點...")
                        points = [(950, 315), (950, 415), (950, 505)] 
                        for px, py in points:
                            if not self.running: break
                            self.click(px, py, duration=50)
                            self.smart_sleep(0.2)
                            
                    elif skip_status == "NONE":

                        # 🚀 執行推進點擊前的安全鎖
                        bot.capture_screen()
                        if not (bot.find_in_folder('system', 'menu_button.png', click_it=False) or \
                                bot.find_in_folder('system', 'go_to_interlude_list.png', click_it=False)):
                            print("🌙 劇情推進中，點擊 (65, 65) 推進對話...")
                            self.click(65, 65, duration=50)
                        else:
                            print("⚠️ 攔截！畫面處於選單狀態，取消劇情連點以防關閉視窗，並退回 INIT！")
                            self.current_state = "INIT"
                            continue
                            
                    self.smart_sleep(0.5)
                    self.current_state = "INIT" # 點完跳回 INIT 重新掃描畫面
                    continue

                if self.current_state == "IDLE":
                    self.update_status("狀態：待機中 / 尋找關卡或確認體力...")
                    
                    if bot.find_in_folder('system', 'close_btn.png', click_it=True):
                        print("⚠️ 偵測到大廳警告彈窗 (可能是倉庫已滿)，為求安全，強制停止腳本！")
                        self.update_status("⛔ 狀態：大廳出現異常警告(倉庫滿?)，已停止", fg="red")
                        self.running = False
                        break

                    if bot.find_in_folder('system', 'ap_recovery_check.png', click_it=False):
                        if not self.handle_ap_recovery(): break
                        continue
                    elif bot.find_in_folder('system', 'menu_button.png', click_it=False):
                        
                        # ==========================================
                        # 🚀 新增：攔截幕間專屬的「任務開始/戰鬥前編隊」確認彈窗
                        # ==========================================
                        if bot.find_in_folder('system', 'interlude_start_btn.png', click_it=True):
                            print("✨ 偵測到幕間任務確認彈窗，點擊開始進入關卡！")
                            self.smart_sleep(2.5) 
                            
                            # 🚀 終極修復：切換畫面後，立刻退回 INIT 讓全域掃描接手！
                            # 這樣它才能在下一秒抓到 SKIP 按鈕，或是抓到助戰畫面！
                            print("🔄 狀態切換：IDLE -> INIT (進入關卡載入)")
                            self.current_state = "INIT"
                            continue
                        
                        # ==========================================
                        # 🚀 幕間模式：完美層級導航系統
                        # ==========================================
                        if self.config.get('interlude_mode', False):
                            bot.capture_screen()
                            
                            # 1. 如果看到「前往故事的舞台」，這只是子選單按鈕，點擊展開！
                            if bot.find_in_folder('system', 'go_to_story_stage.png', click_it=True):
                                print("✨ 點擊「前往故事的舞台」，展開關卡子選單...")
                                self.smart_sleep(2.0)
                                continue
                                
                            # 2. 廣域雷達：掃描畫面上「所有」幕間箭頭
                            bot.capture_screen()
                            interlude_path = os.path.join(bot.sys_path, 'interlude_active.png')
                            all_interludes = bot.find_all_by_abspath(interlude_path, threshold=0.85)
                            
                            found_bright_one = False
                            if all_interludes:
                                print(f"🔍 [廣域偵測] 發現 {len(all_interludes)} 個幕間箭頭，檢查亮度...")
                                for i, pos in enumerate(all_interludes):
                                    ix, iy = pos
                                    patch = bot.current_screen[iy-10:iy+10, ix-10:ix+10]
                                    v_val = np.mean(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[:, :, 2]) if patch.size > 0 else 0
                                    
                                    if v_val > 120:
                                        print(f"  ✨ 標籤 {i+1} 亮度達標 ({v_val:.0f})！點擊進入關卡。")
                                        self.click(ix, iy)
                                        found_bright_one = True
                                        self.smart_sleep(2.0)
                                        break # 找到亮的就進去了，不用再找
                                    else:
                                        print(f"  ❌ 標籤 {i+1} 亮度不足 ({v_val:.0f})，跳過。")

                            if found_bright_one:
                                continue # 已經點進去了，重新開始大迴圈
                                
                            # 3. 如果沒有「前往故事舞台」，也沒有「亮的箭頭」，代表這個角色的目錄清空了！
                            bot.capture_screen()
                            if bot.find_in_folder('system', 'go_to_interlude_list.png', click_it=True):
                                print("🎉 此目錄已清空，點擊返回上一層總列表！")
                                self.smart_sleep(3.0)
                                
                                # 回到總列表後，再次執行終極安檢
                                bot.capture_screen()
                                list_interludes = bot.find_all_by_abspath(interlude_path, threshold=0.85)
                                has_any_bright = False
                                for pos in list_interludes:
                                    lx, ly = pos
                                    patch = bot.current_screen[ly-10:ly+10, lx-10:lx+10]
                                    v_val = np.mean(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[:, :, 2]) if patch.size > 0 else 0
                                    if v_val > 120:
                                        has_any_bright = True; break
                                
                                if has_any_bright:
                                    print("🔄 總列表還有其他解鎖幕間，繼續運行尋找下一個！")
                                    continue
                                else:
                                    print("🏆 總列表已無解鎖關卡，完美光榮下班！")
                                    self.update_status("🎉 狀態：幕間全部通關完成！", fg="green")
                                    self.running = False
                                    break
                            else:
                                if all_interludes: 
                                    print("🛑 畫面上只有未解鎖的暗標籤，且無返回鍵，為防卡死，腳本停止。")
                                    self.update_status("⛔ 狀態：無可挑戰關卡，已停止", fg="red")
                                    self.running = False
                                    break

                            # ==========================================
                            # 🧱 絕對隔離牆：只要是幕間模式，執行到這裡就強制回頭！
                            # 絕對不准掉下去執行一般周回的 1380, 300 點擊！
                            # ==========================================
                            self.smart_sleep(1.0)
                            continue
                        
                        # ==========================================
                        # 🚀 以下是一般周回模式的專屬邏輯 (非幕間模式才會走到這)
                        # ==========================================
                        self.update_status("狀態：大廳選擇任務中...")
                        self.click(1380, 300)
                        self.smart_sleep(1.5)
                        bot.capture_screen()
                        if bot.find_in_folder('system', 'mission_start.png', click_it=True):
                            print("✅ 偵測到「任務開始」彈窗，已自動點擊確認！")
                            self.smart_sleep(2.0)
                        continue

                    elif bot.find_in_folder('system', 'decide_btn.png', click_it=False):
                        self.update_status("狀態：點擊確認視窗...")
                        bot.find_in_folder('system', 'decide_btn.png') 
                        self.smart_sleep(2.0) 
                        continue
                    elif bot.find_in_folder('system', 'support_check.png', click_it=False):
                        print("🔄 狀態切換：IDLE -> SUPPORT")
                        self.current_state = "SUPPORT"
                        swipe_count = 0
                        continue
                    elif bot.find_in_folder('system', 'attack.png', click_it=False):
                        print("🔄 狀態切換：IDLE -> BATTLE")
                        self.current_state = "BATTLE"
                        continue

                elif self.current_state == "SUPPORT":
                    target_loops = self.config['loop_target']
                    self.update_status(f"狀態：尋找助戰 ({self.config['support_class']}) | 周回: {self.current_loop}/{'無限' if target_loops==0 else target_loops}")
                    target_cls = self.config['support_class']
                    
                    if target_cls in class_images and swipe_count == 0:
                        target_img = class_images[target_cls]
                        cls_pos = bot.find_in_folder('system', target_img, click_it=False)
                        if cls_pos:
                            print(f"✅ 視覺鎖定 [{target_cls}] 職階圖標，執行偏移點擊！")
                            self.click(cls_pos[0], cls_pos[1] - 10)
                            if not self.smart_sleep(0.8): break
                            bot.capture_screen()
                        else:
                            print(f"⚠️ 尚未偵測到 [{target_cls}] 職階圖標，等待載入中...")
                            self.smart_sleep(0.5)
                            continue
                        
                    found = False
                    servant_paths = [p for p in self.config.get('target_servant_paths', []) if p]
                    ce_paths = [p for p in self.config.get('target_ce_paths', []) if p]
                    
                    # ==========================================
                    # 🚀 助戰選擇邏輯 (包含幕間隨機特權)
                    # ==========================================
                    # 幕間模式特權：沒放圖就隨便選第一個助戰！
                    if self.config.get('interlude_mode', False) and not servant_paths and not ce_paths:
                        print("ℹ️ [幕間模式] 未指定助戰與禮裝，直接選擇第一位助戰！")
                        self.click(600, 350)
                        found = True
                    else:
                        # ⚠️ 這裡就是你問的地方！把原本找圖的邏輯全部包進 else 裡面！
                        serv_list = []
                        for p in servant_paths: serv_list.extend(bot.find_all_by_abspath(p))
                            
                        ce_list = []
                        for p in ce_paths: ce_list.extend(bot.find_all_by_abspath(p))

                        if servant_paths and ce_paths:
                            if serv_list and ce_list:
                                for s_pos in serv_list:
                                    for c_pos in ce_list:
                                        if abs(s_pos[0] - c_pos[0]) < 50 and 50 < (c_pos[1] - s_pos[1]) < 250:
                                            self.click(s_pos[0], s_pos[1])
                                            found = True
                                            break 
                                    if found: break 
                        elif servant_paths and not ce_paths:
                            if serv_list:
                                self.click(serv_list[0][0], serv_list[0][1])
                                found = True
                        elif ce_paths and not servant_paths:
                            if ce_list:
                                self.click(ce_list[0][0], ce_list[0][1])
                                found = True
                    # ==========================================

                    if found: 
                        swipe_count = 0
                        print("🔄 狀態切換：SUPPORT -> TEAM_SELECT")
                        self.current_state = "TEAM_SELECT" 
                        self.smart_sleep(3)
                        continue
                    else:
                        if np.std(bot.current_screen_gray) < 5:
                            print("⏳ 畫面載入中，等待刷新...")
                            self.smart_sleep(0.5)
                            continue

                        old_patch = bot.current_screen_gray[400:600, 200:900].copy()

                        print(f"⏬ 未找到助戰，執行第 {swipe_count+1} 次精準滑動...")
                        self.swipe(960, 800, 960, 400, 300)
                        
                        self.smart_sleep(0.5)
                        bot.capture_screen()
                        
                        new_search_area = bot.current_screen_gray[350:650, 200:900]
                        res = cv2.matchTemplate(new_search_area, old_patch, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(res)
                        
                        if max_val > 0.95: 
                            print(f"🛑 [撞牆測試] 發現畫面高度滯留 (相似度 {max_val:.3f} > 0.95)，確定已達列表最底部！")
                            if bot.find_in_folder('system', 'refresh_btn.png', click_it=True):
                                self.smart_sleep(1.0)
                                bot.capture_screen()
                                if bot.find_in_folder('system', 'refresh_yes.png', click_it=True):
                                    print("🔄 列表更新中，等待系統重整...")
                                    swipe_count = 0 
                                    self.smart_sleep(2.5)
                                else:
                                    print("⏳ 更新按鈕冷卻中，持續等待重試...")
                        else:
                            print(f"✅ 滑動成功 (相似度降至 {max_val:.2f})，進行下一輪掃描！")
                            swipe_count += 1
                            
                            if swipe_count > 25:
                                print("⚠️ 助戰列表滑動達安全上限 (25次)，強制執行列表更新！")
                                if bot.find_in_folder('system', 'refresh_btn.png', click_it=True):
                                    self.smart_sleep(1.0)
                                    bot.capture_screen()
                                    if bot.find_in_folder('system', 'refresh_yes.png', click_it=True):
                                        swipe_count = 0
                                        self.smart_sleep(2.5)
                    continue

                elif self.current_state == "TEAM_SELECT":
                    bot.capture_screen() # 確保拿到最新畫面
                    
                    # 🚀 1. 優先攔截：幕間專屬的「編制限制」彈窗
                    if bot.find_in_folder('system', 'formation_limit.png', click_it=False):
                        print("⚠️ 發現「編制限制」彈窗，優先點擊關閉，準備自動編隊！")
                        bot.find_in_folder('system', 'close_btn.png', click_it=True)
                        self.smart_sleep(1.5)
                        bot.capture_screen() # 刷新畫面，讓後續流程繼續
                        
                    # 🚀 2. 致命攔截：如果不是編制限制，卻有 close_btn，那才是真正的異常！
                    elif bot.find_in_folder('system', 'close_btn.png', click_it=True):
                        print("⚠️ 偵測到未知的出擊警告彈窗 (可能是 Cost 超載或倉庫滿)，為求安全強制停止腳本！")
                        self.update_status("⛔ 狀態：出擊警告，已停止", fg="red")
                        self.running = False
                        break

                    if bot.find_in_folder('system', 'attack.png', click_it=False):
                        self.update_status("狀態：連續出擊跳過隊伍選擇，進入戰鬥...")
                        print("🔄 狀態切換：TEAM_SELECT -> BATTLE (連續出擊直達)")
                        self.current_state = "BATTLE"
                        current_wave = 0 
                        continue
                    elif bot.find_in_folder('system', 'quest_start.png', click_it=False) or \
                         bot.find_in_folder('system', 'battle_start.png', click_it=False) or \
                         bot.find_in_folder('system', 'mission_start.png', click_it=False) or \
                         bot.find_in_folder('system', 'team_confirm.png', click_it=False):
                        
                        target_team = self.config['team_index']
                        self.update_status(f"狀態：防呆切換隊伍 -> 目標 {target_team}")
                        dummy_team = 2 if target_team == 1 else 1
                        dummy_x = team_dot_start_x + (dummy_team - 1) * team_dot_gap
                        self.click(dummy_x, team_dot_y)
                        if not self.smart_sleep(0.8): break
                        target_x = team_dot_start_x + (target_team - 1) * team_dot_gap
                        self.click(target_x, team_dot_y)
                        if not self.smart_sleep(1.5): break 
                        bot.capture_screen() 

                        # ==========================================
                        # 🚀 幕間強制編隊與強制助戰處理
                        # ==========================================
                        do_auto_form = self.config.get('auto_formation', False) or self.config.get('interlude_mode', False)
                        if do_auto_form:
                            print("🔄 [自動編成] 啟動！開始執行編隊流程...")
                            
                            # 1. 基本自動編制 (只點外層跟內層，保留決定鍵)
                            formation_steps = [('auto_form_btn1.png', '外層自動編成'), ('auto_form_btn2.png', '視窗內確認編成')]
                            for img_name, step_name in formation_steps:
                                if not self.running: break
                                timeout = time.time() + 4.0
                                while time.time() < timeout and self.running:
                                    bot.capture_screen()
                                    if bot.find_in_folder('system', img_name, click_it=True):
                                        print(f"👉 成功點擊：{step_name}")
                                        self.smart_sleep(1.5); break
                                    self.smart_sleep(0.2)

                            # 2. 檢查「強制出擊位」並從支援補上 (因為前排有3個位置，最多檢查3次)
                            print("🔍 檢查是否有強制出擊角色空位...")
                            for _ in range(3):
                                bot.capture_screen()
                                if bot.find_in_folder('system', 'mandatory_slot.png', click_it=True):
                                    print("⚠️ 發現強制出擊空位！準備從支援中編隊...")
                                    
                                    # 🚀 給予耐心，等待視窗彈出
                                    support_btn_found = False
                                    timeout_support = time.time() + 4.0
                                    while time.time() < timeout_support and self.running:
                                        self.smart_sleep(0.5)
                                        bot.capture_screen()
                                        if bot.find_in_folder('system', 'select_from_support.png', click_it=True):
                                            print("👉 已點擊「從支援中編隊」")
                                            support_btn_found = True
                                            break
                                            
                                    if support_btn_found:
                                        self.smart_sleep(2.5) # 確保畫面切換到了助戰列表
                                        print("👉 選擇第一位支援角色")
                                        self.click(600, 350) 
                                        self.smart_sleep(3.0) # 確保選擇後退回了編隊畫面
                                    else:
                                        print("⚠️ 找不到 [select_from_support.png]，請檢查檔名或截圖！跳出防死迴圈...")
                                        break
                                else:
                                    break # 畫面上沒有強制空位了，跳出迴圈

                            # 3. 最後確認：點擊「決定」
                            bot.capture_screen()
                            if bot.find_in_folder('system', 'auto_form_btn3.png', click_it=True):
                                print("✅ [自動編成] 已點擊「決定」套用隊伍！")
                                self.smart_sleep(2.0)
                        # ==========================================
                        
                        # 重新抓取畫面，準備點擊出擊按鈕
                        bot.capture_screen()
                        pos_quest = bot.find_in_folder('system', 'quest_start.png', click_it=False)
                        pos_battle = bot.find_in_folder('system', 'battle_start.png', click_it=False)
                        pos_mission = bot.find_in_folder('system', 'mission_start.png', click_it=False)
                        
                        if pos_quest:
                            self.click(pos_quest[0], pos_quest[1] + 10, duration=50)
                        elif pos_battle:
                            self.click(pos_battle[0], pos_battle[1] + 10, duration=50)
                        elif pos_mission:
                            self.click(pos_mission[0], pos_mission[1] + 10, duration=50)
                        else:
                            self.click(1750, 1000, duration=50)
                            
                        self.update_status("狀態：出擊讀取中...")
                        print("🔄 狀態切換：TEAM_SELECT -> INIT (退回全域掃描)")
                        
                        # 🚀 出擊後可能進劇情，所以強制退回 INIT 重新掃描！
                        self.current_state = "INIT" 
                        current_wave = 0 
                        if not self.smart_sleep(5): break
                        continue

                elif self.current_state == "BATTLE":
                    if bot.find_in_folder('system', 'attack.png', click_it=False):
                        if self.config.get('smart_turn_mode', False):
                            self.smart_sleep(0.3) 
                            bot.capture_screen()
                            if bot.find_in_folder('system', 'turn_1.png', click_it=False):
                                current_wave = 0
                                self.update_status("狀態：視覺偵測 -> 第一回合 (執行 Wave 1)")
                            elif bot.find_in_folder('system', 'turn_2.png', click_it=False):
                                current_wave = 1
                                self.update_status("狀態：視覺偵測 -> 第二回合 (執行 Wave 2)")
                            elif bot.find_in_folder('system', 'turn_3.png', click_it=False):
                                current_wave = 2
                                self.update_status("狀態：視覺偵測 -> 第三回合 (執行 Wave 3)")
                            else:
                                current_wave = 99 
                                self.update_status("狀態：視覺偵測 -> 超過三回合，啟動極速補刀")
                        else:
                            self.update_status(f"狀態：Wave {current_wave+1} 戰鬥中")
                        
                        # 🚀 1. 劇本執行
                        attack_opened = False
                        is_random_mode = (self.config['battle_mode'] == "random")
                        is_script_mode = (self.config['battle_mode'] == "script")
                        
                        if is_script_mode: 
                            if current_wave < len(self.config['script_data']):
                                attack_opened = self.execute_script_from_list(current_wave)
                            else:
                                print(f"⏩ 劇本執行完畢，進入殘局處理！")
                        
                        # ==========================================
                        # 🚀 2. 全自動 AI / 殘局補招 雙引擎
                        # ==========================================
                        # 啟動條件：Attack 還沒按下去 且 (是隨機模式 OR 劇本模式已經打到殘局)
                        if not attack_opened and (is_random_mode or (is_script_mode and current_wave >= len(self.config['script_data']))):
                            if is_random_mode:
                                print("🤖 [全自動 AI] 啟動技能掃描，自由作戰模式！")
                            else:
                                print("🛡️ [殘局 AI] 啟動技能掃描，保底補強模式！")
                                
                            available_skills = self.check_skill_available_batch(is_master=False)
                            skills_to_use = [i for i, avail in enumerate(available_skills) if avail][:3]
                            skill_coords = [None, (111, 871), (244, 871), (376, 871), (586, 871), (716, 871), (847, 871), (1060, 871), (1191, 871), (1324, 871)]
                            
                            for s_idx in skills_to_use:
                                if not self.running: break
                                print(f"✨ 自動發動：第 {s_idx+1} 號技能")
                                
                                sx, sy = skill_coords[s_idx+1]
                                self.click(sx, sy)
                                self.smart_sleep(0.8)
                                
                                bot.capture_screen()
                                
                                # 🛡️ 庫庫爾坎特殊技能處理
                                if bot.find_in_folder('system', 'sp_use_star.png', click_it=False):
                                    pos = bot.find_in_folder('system', 'sp_use_star.png', click_it=False)
                                    s, v = self.get_skill_color_stats(pos[0], pos[1])
                                    if v > 120:
                                        print("🌟 星星充足，執行特殊耗星！")
                                        self.click(pos[0], pos[1])
                                    else:
                                        print("⚠️ 星星不足，選擇不耗星！")
                                        bot.find_in_folder('system', 'sp_no_star.png', click_it=True)
                                    self.smart_sleep(0.5)
                                    bot.capture_screen() 
                                elif bot.find_in_folder('system', 'sp_no_star.png', click_it=True):
                                    print("⚠️ 選擇不耗星！")
                                    self.smart_sleep(0.5)
                                    bot.capture_screen()
                                
                                # 🛡️ 對象選擇：涵蓋 3人、2人、1人 陣型的全方位掃描
                                if bot.find_in_folder('system', 'select_target_text.png', click_it=False):
                                    
                                    # 🚀 終極對策：涵蓋所有陣型的 5 個可能 X 座標
                                    all_target_positions = [
                                        (485, 590),  # 3人陣型：左側 (通常是一號主打手)
                                        (725, 590),  # 2人陣型：左側
                                        (965, 590),  # 3人陣型：中間 / 1人陣型：居中
                                        (1195, 590), # 2人陣型：右側
                                        (1425, 590)  # 3人陣型：右側
                                    ]
                                    
                                    if is_random_mode:
                                        # 隨機模式：打亂 5 個座標隨機嘗試
                                        try_order = all_target_positions.copy()
                                        random.shuffle(try_order)
                                        print("🎯 技能需要對象，[全自動 AI] 啟動全板位隨機盲掃...")
                                    else:
                                        # 殘局保底模式：永遠優先找「偏左」和「居中」的主打手
                                        try_order = all_target_positions
                                        print("🎯 技能需要對象，[殘局保底] 啟動防偏移掃描，優先尋找左側打手...")
                                        
                                    for tx, ty in try_order:
                                        if not self.running: break
                                        print(f"  👉 嘗試點擊座標 ({tx}, {ty})...")
                                        self.click(tx, ty)
                                        self.smart_sleep(0.6) # 等待系統反應
                                        
                                        # 📸 重新截圖，檢查「請選擇對象」視窗是不是還在
                                        bot.capture_screen()
                                        if not bot.find_in_folder('system', 'select_target_text.png', click_it=False):
                                            print(f"  ✅ 成功！命中目標，技能已接受。")
                                            break # 成功選到人，跳出替補迴圈
                                        else:
                                            print(f"  ⚠️ 該位置是空隙！準備替補下一個位置...")
                                    
                                print("⏳ 等待技能動畫結束...")
                                self.wait_attack_and_skip(timeout_sec=6.0, do_click=True)

                        if not self.running: break
                        
                        self.update_status("狀態：補點剩餘卡片...")
                        
                        # 🚀 3. 進入選卡畫面
                        if not attack_opened:
                            if self.config.get('skill_mode') == '極限盲操':
                                # 注意：這段極限防撞車只會在你沒放任何自動技能，且設定極限盲操時才會觸發
                                print("🛡️ [極限防撞車] 準備進入選卡，強制同步時間軸...")
                                self.wait_attack_and_skip(timeout_sec=8.0, do_click=False)

                            bot.capture_screen() 
                            if bot.find_in_folder('system', 'attack.png', click_it=False):
                                self.click(1650, 920) 
                                if not self.smart_sleep(2.5): break 
                                bot.capture_screen()
                                if bot.find_in_folder('system', 'attack.png', click_it=False):
                                    print("⚠️ 偵測到 Attack 點擊無效 (被吞 Tap)，執行重試...")
                                    self.click(1650, 920) 
                                    self.smart_sleep(2.5) 
                            
                        # 🚀 4. 執行智能選卡
                        self.select_battle_cards(current_wave)
                        
                        # 🚀 5. 返回按鈕防呆機制
                        print("⏳ 等待戰鬥動畫開始...")
                        attack_started = False
                        timeout = time.time() + 3.0 
                        while time.time() < timeout and self.running:
                            bot.capture_screen()
                            if not bot.find_in_folder('system', 'back_btn.png', click_it=False):
                                attack_started = True
                                break
                            self.smart_sleep(0.3)

                        if not attack_started:
                            print("⚠️ [極限防呆] 3 秒後「返回按鈕」仍存在，判定為卡頓/吞 Tap！")
                            self.update_status("狀態：選卡卡頓，自動返回重試...", fg="orange")
                            bot.find_in_folder('system', 'back_btn.png', click_it=True)
                            self.smart_sleep(1.5)
                            self.click(1650, 920) 
                            self.smart_sleep(2.5)
                            print("🔄 執行第二次選卡...")
                            self.select_battle_cards(current_wave)
                            self.smart_sleep(1.0)

                        # ==========================================
                        # 🚀 6. 完美結合：死等 8 秒 + 動態跳過死亡/攻擊動畫
                        # ==========================================
                        print("⏳ [效能優化] 暫停掃描 8 秒，等待基礎戰鬥動畫...")
                        if not self.smart_sleep(8): break
                        
                        # 呼叫你寫好的動態監控引擎
                        next_state = self.wait_for_next_turn_dynamic()
                        
                        # 更新狀態與回合數
                        self.current_state = next_state
                        if next_state == "BATTLE":
                            current_wave += 1 
                            
                        continue
                        
                    elif bot.find_in_folder('system', 'bond_screen.png', click_it=False) or \
                         bot.find_in_folder('system', 'exp_screen.png', click_it=False) or \
                         bot.find_in_folder('system', 'drop_screen.png', click_it=False) or \
                         bot.find_in_folder('system', 'next_btn.png', click_it=False):
                        print("🔄 狀態切換：BATTLE -> RESULT")
                        self.current_state = "RESULT"
                        continue
                    
                    elif bot.find_in_folder('system', 'retreat_btn.png', click_it=False):
                        print("🔄 狀態切換：BATTLE -> DEFEAT (戰鬥失敗，全滅撤退)")
                        self.current_state = "DEFEAT"
                        continue

                elif self.current_state == "DEFEAT":
                    self.update_status("狀態：戰鬥失敗，執行撤退程序...", fg="red")
                    timeout = time.time() + 25.0
                    while time.time() < timeout and self.running:
                        self.bot.capture_screen()
                        if self.bot.find_in_folder('system', 'retreat_btn.png', click_it=True):
                            print("👉 已點擊「撤退」按鈕")
                            self.smart_sleep(1.0)
                            continue
                        if self.bot.find_in_folder('system', 'retreat_decide_btn.png', click_it=True):
                            print("👉 已點擊「決定」撤退")
                            self.smart_sleep(1.5)
                            continue
                        if self.bot.find_in_folder('system', 'close_btn.png', click_it=True):
                            print("👉 已點擊撤退結果視窗的「關閉」")
                            self.smart_sleep(2.0)
                            continue
                        if self.bot.find_in_folder('system', 'menu_button.png', click_it=False):
                            print("✅ 已成功退回大廳")
                            break
                        self.smart_sleep(0.5)
                        
                    self.update_status("⛔ 狀態：已從任務撤退，強制終止周回腳本。", fg="red")
                    self.running = False 
                    break

                elif self.current_state == "RESULT":
                    self.update_status(f"狀態：結算中... (剛打完第 {self.current_loop} 場)")
                    timeout = time.time() + 30 
                    while time.time() < timeout and self.running:
                        bot.capture_screen() 
                        
                        # 1. 優先處理各種彈窗
                        if bot.find_in_folder('system', 'bond_ce_close.png', click_it=True):
                            self.smart_sleep(1.0); continue
                            
                        # ==========================================
                        # 🚀 修改：統一使用萬用獎勵截圖 (請點擊畫面)
                        # ==========================================
                        if bot.find_in_folder('system', 'reward_screen.png', threshold=0.85, click_it=False):
                            print("💎 [RESULT] 偵測到過關報酬/強化畫面！執行關閉...")
                            self.click(65, 65, duration=50) # 點擊左上角關閉
                            self.smart_sleep(2.0)
                            self.current_state = "INIT" # 強制跳回 INIT，重新分配狀態
                            break

                        # ==========================================
                        # 🚀 新增：從者資料更新與新幕間開放 (必須點擊實體關閉按鈕)
                        # ==========================================
                        if bot.find_in_folder('system', 'servant_data_update.png', threshold=0.85, click_it=False) or \
                           bot.find_in_folder('system', 'new_interlude_unlocked.png', threshold=0.85, click_it=False):
                            print("💎 [RESULT] 偵測到資料更新或新幕間開放！尋找並點擊關閉按鈕...")
                            if bot.find_in_folder('system', 'close_btn.png', click_it=True):
                                self.smart_sleep(2.0)
                                self.current_state = "INIT" 
                                break
                            else:
                                self.smart_sleep(0.5)
                                continue # 等待按鈕浮現

                        if bot.find_in_folder('system', 'friend_request.png', click_it=False):
                            if bot.find_in_folder('system', 'reject_friend.png'): self.smart_sleep(1.5)
                            else: self.click(480, 850); self.smart_sleep(1.5)
                            continue

                        if bot.find_in_folder('system', 'next_btn.png', click_it=True):
                            self.smart_sleep(0.5); continue
                            
                        if bot.find_in_folder('system', 'close_btn.png', click_it=True):
                            print("⚠️ 結算畫面偵測到「關閉」按鈕 (可能是 御主升級 或 白紙化無能量)！")
                            self.smart_sleep(1.0); continue
                        
                        # 2. 檢查是否已經回到大廳 (一般周回的安全鎖)
                        if bot.find_in_folder('system', 'continue_battle.png', click_it=False) or \
                           bot.find_in_folder('system', 'menu_button.png', click_it=False) or \
                           bot.find_in_folder('system', 'go_to_interlude_list.png', click_it=False):
                            break
                            
                        # 🚀 幕間模式劇情提早跳出
                        if self.config.get('interlude_mode', False) and self.check_skip_button() in ["READY", "DARK"]:
                            print("✨ 結算途中偵測到劇情 SKIP，提早結束結算迴圈！")
                            break

                        # ==========================================
                        # 🚀 終極黑屏凍結鎖：如果畫面是純黑轉場，絕對不點擊！
                        # ==========================================
                        if np.std(bot.current_screen_gray) < 5:
                            print("⏳ 偵測到黑屏載入中，凍結手指防止點擊殘留！")
                            self.smart_sleep(0.5)
                            continue # 直接跳過下方的連點，回去繼續監視畫面

                        # ==========================================
                        # 🚀 終極防護鎖：拔刀前最後確認！
                        # 只要看到大廳或幕間目錄的 UI，立刻收手並退回 INIT！
                        # ==========================================
                        bot.capture_screen()
                        if bot.find_in_folder('system', 'go_to_interlude_list.png', click_it=False) or \
                           bot.find_in_folder('system', 'menu_button.png', click_it=False):
                            print("⚠️ 攔截！畫面處於選單狀態，取消結算連點以防關閉視窗，並退回 INIT！")
                            self.current_state = "INIT"
                            break # 打破結算迴圈，交給 INIT 重新導航

                        # 安全確認完畢，放心執行加速連點 (統一改回 65, 65)
                        self.click(65, 65, times=1, duration=50)
                        self.smart_sleep(0.2)

                    # 🚀 如果是幕間模式，打完一次直接回 INIT 掃描是否完全通關
                    if self.config.get('interlude_mode', False):
                        print("🔄 狀態切換：RESULT -> INIT (幕間結算中跳轉)")
                        self.current_state = "INIT"
                        self.smart_sleep(1.0)
                        continue
                        
                    target_loops = self.config['loop_target']
                    if target_loops > 0 and self.current_loop >= target_loops:
                        self.update_status(f"🎉 任務達成：已完成 {self.current_loop} 場周回！", fg="green")
                        bot.capture_screen()
                        if bot.find_in_folder('system', 'continue_battle.png', click_it=False):
                            if not bot.find_in_folder('system', 'close_btn.png'):
                                self.click(650, 850) 
                            self.smart_sleep(3.0) 
                        break 
                    else:
                        bot.capture_screen() 
                        if bot.find_in_folder('system', 'continue_battle.png'):
                            self.update_status("狀態：準備連續出擊")
                            self.current_loop += 1 
                            print("🔄 狀態切換：RESULT -> INIT (一般連續出擊)")
                            self.current_state = "INIT" 
                            if not self.smart_sleep(5): break 
                            continue
                        elif bot.find_in_folder('system', 'menu_button.png', click_it=False):
                            self.update_status("狀態：無連續出擊，退回大廳重新接管...")
                            self.current_loop += 1 
                            print("🔄 狀態切換：RESULT -> INIT (大廳重新接管)")
                            self.current_state = "INIT" 
                            if not self.smart_sleep(3): break 
                            continue
                        else:
                            print("⚠️ 結算異常：找不到連續出擊，也找不到大廳。")
                            self.update_status("⛔ 狀態：結算卡死 (能量耗盡?)，腳本停止", fg="red")
                            self.running = False
                            break

            except Exception as e: 
                print(f"Error: {e}")
            self.smart_sleep(0.5)
            
        self.stop_cb()