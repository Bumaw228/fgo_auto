import time
import cv2
import numpy as np
import os

class FGONav:
    def __init__(self, context):
        self.ctx = context
        self.swipe_count = 0
        self.is_startup = True 
        self.class_images = {
            "ALL": "class_all.png", "Saber": "class_saber.png", 
            "Archer": "class_archer.png", "Lancer": "class_lancer.png", 
            "Rider": "class_rider.png", "Caster": "class_caster.png", 
            "Assassin": "class_assassin.png", "Berserker": "class_berserker.png", 
            "Extra": "class_extra.png", "Mix": "class_mix.png"
        }
        self.story_skip_fails = 0 # 🚀 新增：記錄 SKIP 失敗次數

    def handle_ap_recovery(self):
        apple_type = self.ctx.config['apple_mode']
        if apple_type == "不自動回體":
            self.ctx.update_status("狀態：AP 不足，停止運行", fg="red")
            self.ctx.running = False
            return False

        apple_map = {"銅蘋果": "bronze_apple.png", "青銅蘋果": "blue_apple.png", "銀蘋果": "silver_apple.png", "金蘋果": "gold_apple.png"}
        target_apple = apple_map.get(apple_type)

        if apple_type in ["銅蘋果", "青銅蘋果"]:
            self.ctx.swipe(960, 800, 960, 300, 500)
            self.ctx.smart_sleep(1.5)
            self.ctx.bot.capture_screen() 

        if self.ctx.bot.find_in_folder('system', target_apple):
            print(f"✅ 已點擊蘋果: {target_apple}")
            self.ctx.smart_sleep(1.5) 
            
            timeout = time.time() + 15.0
            while time.time() < timeout and self.ctx.running:
                self.ctx.bot.capture_screen() 
                if self.ctx.bot.find_in_folder('system', 'decide_btn.png', click_it=True):
                    self.ctx.smart_sleep(2.5); return True
                self.ctx.click(1280, 830, duration=50)
                self.ctx.smart_sleep(1.5); self.ctx.bot.capture_screen() 
                if not self.ctx.bot.find_in_folder('system', 'ap_recovery_check.png', click_it=False): return True
            self.ctx.update_status("狀態：吃蘋果卡住，停止運行", fg="red")
            self.ctx.running = False
            return False
        return False

    def handle_init_state(self):
        bot = self.ctx.bot
        self.ctx.update_status("狀態：全局掃描，判斷當前畫面...")
        
        skip_status = self.ctx.vision.check_skip_button()
        if self.ctx.config.get('interlude_mode', False) and skip_status in ["READY", "DARK"]:
            self.is_startup = False # 進入劇情，關閉啟動標記
            return "STORY"
            
        if bot.find_in_folder('system', 'attack.png', click_it=False) or \
           bot.find_in_folder('system', 'select_target_text.png', click_it=False) or \
           bot.find_in_folder('system', 'order_change_btn.png', click_it=False) or \
           bot.find_in_folder('system', 'servant_detail_close_x.png', click_it=False):
            
            # 🚀 完美接手洗白邏輯：只有「剛按下開始」且「直接出現在戰鬥畫面」才洗白
            if self.is_startup:
                self.ctx.combat.reset_battle_state_if_needed() 
                self.is_startup = False # 洗白後解除啟動狀態
                
            return "BATTLE"
            
        elif bot.find_in_folder('system', 'back_btn.png', click_it=True):
            self.ctx.smart_sleep(1.0); return "BATTLE"
            
        elif bot.find_in_folder('system', 'reward_screen.png', click_it=False):
            self.is_startup = False # 看到大廳/獎勵畫面，關閉啟動標記
            self.ctx.click(65, 65, duration=50); self.ctx.smart_sleep(1.5); return "INIT"
            
        elif bot.find_in_folder('system', 'servant_data_update.png', threshold=0.85, click_it=False) or \
             bot.find_in_folder('system', 'new_interlude_unlocked.png', threshold=0.85, click_it=False):
            self.is_startup = False
            if bot.find_in_folder('system', 'close_btn.png', click_it=True): self.ctx.smart_sleep(1.5)
            else: self.ctx.smart_sleep(0.5) 
            return "INIT"
            
        elif bot.find_in_folder('system', 'support_check.png', click_it=False):
            self.is_startup = False
            self.swipe_count = 0
            return "SUPPORT"
            
        elif bot.find_in_folder('system', 'quest_start.png', click_it=False) or \
             bot.find_in_folder('system', 'battle_start.png', click_it=False) or \
             bot.find_in_folder('system', 'mission_start.png', click_it=False) or \
             bot.find_in_folder('system', 'team_confirm.png', click_it=False) or \
             bot.find_in_folder('system', 'auto_form_btn1.png', click_it=False): 
            self.is_startup = False
            return "TEAM_SELECT"
            
        elif any(bot.find_in_folder('system', x, click_it=False) for x in ['bond_screen.png', 'exp_screen.png', 'drop_screen.png', 'next_btn.png', 'bond_ce_close.png', 'continue_battle.png']):
            self.is_startup = False
            return "RESULT"
            
        elif bot.find_in_folder('system', 'retreat_btn.png', click_it=False):
            self.is_startup = False
            return "DEFEAT"
            
        elif bot.find_in_folder('system', 'menu_button.png', click_it=False) or \
             bot.find_in_folder('system', 'ap_recovery_check.png', click_it=False) or \
             bot.find_in_folder('system', 'interlude_active.png', click_it=False) or \
             bot.find_in_folder('system', 'go_to_interlude_list.png', click_it=False): 
            self.is_startup = False
            return "IDLE"
            
        else:
            if self.ctx.config.get('interlude_mode', False) and np.std(bot.current_screen_gray) >= 5:
                self.ctx.click(65, 65, duration=50); self.ctx.smart_sleep(0.5)
            else: self.ctx.smart_sleep(0.5)
            
        return "INIT"

    def handle_story_state(self):
        self.ctx.update_status("狀態：劇情播放中...")
        skip_status = self.ctx.vision.check_skip_button()
        
        # 🚀 神級防呆：如果 SKIP 失敗 3 次，強制當作卡選項 (DARK) 處理！
        if self.story_skip_fails >= 3:
            print("⚠️ [防呆] 連續 3 次無法 SKIP，判斷為選項卡住，強制盲點！")
            skip_status = "DARK"
            self.story_skip_fails = 0 # 重置
        
        if skip_status == "READY":
            self.ctx.click(1798, 61, duration=50) 
            skip_success = False
            timeout = time.time() + 2.5
            while time.time() < timeout and self.ctx.running:
                self.ctx.smart_sleep(0.3); self.ctx.bot.capture_screen()
                if self.ctx.bot.find_in_folder('system', 'skip_confirm.png', click_it=True):
                    self.ctx.smart_sleep(3.0)
                    skip_success = True
                    self.story_skip_fails = 0 # 成功就歸零
                    break
            if not skip_success:
                self.story_skip_fails += 1 # 失敗就 +1
                print(f"⚠️ [警告] 點擊了 SKIP 但未出現確認框 (累積失敗 {self.story_skip_fails}/3)")
        elif skip_status == "DARK":
            self.story_skip_fails = 0 # 進入選項模式就歸零
            points = [(950, 315), (950, 415), (950, 505)] 
            for px, py in points:
                if not self.ctx.running: break
                self.ctx.click(px, py, duration=50); self.ctx.smart_sleep(0.2)
        elif skip_status == "NONE":
            self.story_skip_fails = 0 
            self.ctx.bot.capture_screen()
            if not (self.ctx.bot.find_in_folder('system', 'menu_button.png', click_it=False) or \
                    self.ctx.bot.find_in_folder('system', 'go_to_interlude_list.png', click_it=False)):
                self.ctx.click(65, 65, duration=50)
            else:
                return "INIT"
                
        self.ctx.smart_sleep(0.5)
        return "INIT"

    def handle_idle_state(self):
        bot = self.ctx.bot
        self.ctx.update_status("狀態：待機中 / 尋找關卡或確認體力...")
        
        if bot.find_in_folder('system', 'close_btn.png', click_it=True):
            self.ctx.update_status("⛔ 狀態：大廳出現異常警告，已停止", fg="red")
            self.ctx.running = False; return "IDLE"

        if bot.find_in_folder('system', 'ap_recovery_check.png', click_it=False):
            self.handle_ap_recovery()
            return "IDLE"
            
        elif bot.find_in_folder('system', 'menu_button.png', click_it=False):
            if bot.find_in_folder('system', 'interlude_start_btn.png', click_it=True):
                self.ctx.smart_sleep(2.5); return "INIT"
            
            if self.ctx.config.get('interlude_mode', False):
                bot.capture_screen()
                if bot.find_in_folder('system', 'go_to_story_stage.png', click_it=True):
                    self.ctx.smart_sleep(2.0); return "IDLE"
                    
                bot.capture_screen()
                interlude_path = os.path.join(bot.sys_path, 'interlude_active.png')
                all_interludes = bot.find_all_by_abspath(interlude_path, threshold=0.85)
                
                found_bright_one = False
                if all_interludes:
                    for ix, iy in all_interludes:
                        patch = bot.current_screen[iy-10:iy+10, ix-10:ix+10]
                        v_val = np.mean(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[:, :, 2]) if patch.size > 0 else 0
                        if v_val > 120:
                            self.ctx.click(ix, iy); found_bright_one = True; self.ctx.smart_sleep(2.0); break

                if found_bright_one: return "IDLE"
                    
                bot.capture_screen()
                if bot.find_in_folder('system', 'go_to_interlude_list.png', click_it=True):
                    self.ctx.smart_sleep(3.0); return "IDLE"
                else:
                    if all_interludes: 
                        self.ctx.update_status("⛔ 狀態：無可挑戰關卡，已停止", fg="red")
                        self.ctx.running = False
                self.ctx.smart_sleep(1.0); return "IDLE"
            
            self.ctx.update_status("狀態：大廳選擇任務中...")
            self.ctx.click(1380, 300); self.ctx.smart_sleep(1.5); bot.capture_screen()
            if bot.find_in_folder('system', 'mission_start.png', click_it=True): self.ctx.smart_sleep(2.0)
            return "IDLE"

        elif bot.find_in_folder('system', 'decide_btn.png', click_it=False):
            bot.find_in_folder('system', 'decide_btn.png'); self.ctx.smart_sleep(2.0); return "IDLE"
        elif bot.find_in_folder('system', 'support_check.png', click_it=False):
            self.swipe_count = 0; return "SUPPORT"
        elif bot.find_in_folder('system', 'attack.png', click_it=False):
            return "BATTLE"
        return "IDLE"

    def handle_support_state(self):
        bot = self.ctx.bot
        self.ctx.update_status(f"狀態：尋找助戰 ({self.ctx.config['support_class']})")
        target_cls = self.ctx.config['support_class']
        
        # 🔙 依需求復原：拿掉「記憶上次職階、相同就跳過點擊」這個優化。
        # 原因：如果沒開遊戲內建的「自動選擇有利職階」，助戰清單刷新後畫面會自己跳掉職階分頁，
        # 這時候如果我們還「以為」自己停在原本的分頁而跳過點擊，就會抓錯職階。
        # 只保留 swipe_count == 0 這個條件：代表這是這一輪全新進入 SUPPORT 狀態的第一次判斷，
        # 才需要點一次職階分頁；scrolling 搜尋中(swipe_count > 0)不會再重複點，
        # 不然每滑一次都重點分頁，清單會被重置回最上面，永遠滑不到助戰。
        if target_cls in self.class_images and self.swipe_count == 0:
            cls_pos = bot.find_in_folder('system', self.class_images[target_cls], click_it=False)
            if cls_pos:
                self.ctx.click(cls_pos[0], cls_pos[1] - 10); self.ctx.smart_sleep(0.8)
                bot.capture_screen()
            else:
                self.ctx.smart_sleep(0.5); return "SUPPORT"
            
        found = False
        servant_paths = [p for p in self.ctx.config.get('target_servant_paths', []) if p]
        ce_paths = [p for p in self.ctx.config.get('target_ce_paths', []) if p]
        
        if self.ctx.config.get('interlude_mode', False) and not servant_paths and not ce_paths:
            self.ctx.click(600, 350); found = True
        else:
            serv_list, ce_list = [], []
            for p in servant_paths: serv_list.extend(bot.find_all_by_abspath(p))
            for p in ce_paths: ce_list.extend(bot.find_all_by_abspath(p))

            if servant_paths and ce_paths and serv_list and ce_list:
                for s_pos in serv_list:
                    for c_pos in ce_list:
                        if abs(s_pos[0] - c_pos[0]) < 50 and 50 < (c_pos[1] - s_pos[1]) < 250:
                            self.ctx.click(s_pos[0], s_pos[1]); found = True; break 
                    if found: break 
            elif servant_paths and not ce_paths and serv_list:
                self.ctx.click(serv_list[0][0], serv_list[0][1]); found = True
            elif ce_paths and not servant_paths and ce_list:
                self.ctx.click(ce_list[0][0], ce_list[0][1]); found = True

        if found: 
            self.swipe_count = 0; self.ctx.smart_sleep(3); return "TEAM_SELECT"
        else:
            if np.std(bot.current_screen_gray) < 5: self.ctx.smart_sleep(0.5); return "SUPPORT"
            old_patch = bot.current_screen_gray[400:600, 200:900].copy()
            self.ctx.swipe(960, 800, 960, 400, 300); self.ctx.smart_sleep(0.5); bot.capture_screen()
            new_search_area = bot.current_screen_gray[350:650, 200:900]
            res = cv2.matchTemplate(new_search_area, old_patch, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            
            if max_val > 0.95: 
                if bot.find_in_folder('system', 'refresh_btn.png', click_it=True):
                    self.ctx.smart_sleep(1.0); bot.capture_screen()
                    if bot.find_in_folder('system', 'refresh_yes.png', click_it=True):
                        self.swipe_count = 0; self.ctx.smart_sleep(2.5)
            else:
                self.swipe_count += 1
                if self.swipe_count > 25:
                    if bot.find_in_folder('system', 'refresh_btn.png', click_it=True):
                        self.ctx.smart_sleep(1.0); bot.capture_screen()
                        if bot.find_in_folder('system', 'refresh_yes.png', click_it=True):
                            self.swipe_count = 0; self.ctx.smart_sleep(2.5)
        return "SUPPORT"

    def handle_team_select_state(self):
        bot = self.ctx.bot
        bot.capture_screen() 
        if bot.find_in_folder('system', 'formation_limit.png', click_it=False):
            bot.find_in_folder('system', 'close_btn.png', click_it=True); self.ctx.smart_sleep(1.5); bot.capture_screen() 
        elif bot.find_in_folder('system', 'close_btn.png', click_it=True):
            self.ctx.update_status("⛔ 狀態：出擊警告，已停止", fg="red")
            self.ctx.running = False; return "TEAM_SELECT"

        if bot.find_in_folder('system', 'attack.png', click_it=False):
            self.ctx.combat.current_wave = 0; return "BATTLE"
            
        elif any(bot.find_in_folder('system', x, click_it=False) for x in ['quest_start.png', 'battle_start.png', 'mission_start.png', 'team_confirm.png']):
            target_team = self.ctx.config['team_index']
            dummy_team = 2 if target_team == 1 else 1
            self.ctx.update_status(f"狀態：選擇隊伍中 (第 {target_team} 隊)...")
            
            first_dot_x = 697  
            last_dot_x = 1222  
            team_dot_y = 75    
            team_dot_gap = (last_dot_x - first_dot_x) / 14.0
            
            dummy_x = int(first_dot_x + (dummy_team - 1) * team_dot_gap)
            self.ctx.click(dummy_x, team_dot_y); self.ctx.smart_sleep(0.8)
            
            target_x = int(first_dot_x + (target_team - 1) * team_dot_gap)
            self.ctx.click(target_x, team_dot_y); self.ctx.smart_sleep(1.5); bot.capture_screen()

            if self.ctx.config.get('auto_formation', False) or self.ctx.config.get('interlude_mode', False):
                for img_name in ['auto_form_btn1.png', 'auto_form_btn2.png']:
                    timeout = time.time() + 4.0
                    while time.time() < timeout and self.ctx.running:
                        bot.capture_screen()
                        if bot.find_in_folder('system', img_name, click_it=True): self.ctx.smart_sleep(1.5); break
                        self.ctx.smart_sleep(0.2)

                for _ in range(3):
                    bot.capture_screen()
                    if bot.find_in_folder('system', 'mandatory_slot.png', click_it=True):
                        timeout_support = time.time() + 4.0
                        while time.time() < timeout_support and self.ctx.running:
                            self.ctx.smart_sleep(0.5); bot.capture_screen()
                            if bot.find_in_folder('system', 'select_from_support.png', click_it=True):
                                self.ctx.smart_sleep(2.5); self.ctx.click(600, 350); self.ctx.smart_sleep(3.0); break
                    else: break 
                bot.capture_screen()
                if bot.find_in_folder('system', 'auto_form_btn3.png', click_it=True): self.ctx.smart_sleep(2.0)
            
            bot.capture_screen()
            pos_quest = bot.find_in_folder('system', 'quest_start.png', click_it=False)
            pos_battle = bot.find_in_folder('system', 'battle_start.png', click_it=False)
            pos_mission = bot.find_in_folder('system', 'mission_start.png', click_it=False)
            
            if pos_quest: self.ctx.click(pos_quest[0], pos_quest[1] + 10, duration=50)
            elif pos_battle: self.ctx.click(pos_battle[0], pos_battle[1] + 10, duration=50)
            elif pos_mission: self.ctx.click(pos_mission[0], pos_mission[1] + 10, duration=50)
            else: self.ctx.click(1750, 1000, duration=50)
                
            self.ctx.update_status(f"狀態：第 {target_team} 隊出擊！任務開始...")
            self.ctx.combat.current_wave = 0; self.ctx.smart_sleep(5); return "INIT"
        return "TEAM_SELECT"

    def handle_result_state(self):
        bot = self.ctx.bot
        self.ctx.update_status(f"狀態：結算中... (剛打完第 {self.ctx.current_loop} 場)")
        timeout = time.time() + 30 
        while time.time() < timeout and self.ctx.running:
            bot.capture_screen() 
            if bot.find_in_folder('system', 'bond_ce_close.png', click_it=True): self.ctx.smart_sleep(1.0); continue
            if bot.find_in_folder('system', 'reward_screen.png', threshold=0.85, click_it=False):
                self.ctx.click(65, 65, duration=50); self.ctx.smart_sleep(2.0); return "INIT"
            if bot.find_in_folder('system', 'servant_data_update.png', threshold=0.85, click_it=False) or \
               bot.find_in_folder('system', 'new_interlude_unlocked.png', threshold=0.85, click_it=False):
                if bot.find_in_folder('system', 'close_btn.png', click_it=True): self.ctx.smart_sleep(2.0); return "INIT"
                else: self.ctx.smart_sleep(0.5); continue 
            if bot.find_in_folder('system', 'friend_request.png', click_it=False):
                if bot.find_in_folder('system', 'reject_friend.png'): self.ctx.smart_sleep(1.5)
                else: self.ctx.click(480, 850); self.ctx.smart_sleep(1.5)
                continue
            if bot.find_in_folder('system', 'next_btn.png', click_it=True): self.ctx.smart_sleep(0.5); continue
            if bot.find_in_folder('system', 'close_btn.png', click_it=True): self.ctx.smart_sleep(1.0); continue
            
            if bot.find_in_folder('system', 'continue_battle.png', click_it=False) or \
               bot.find_in_folder('system', 'menu_button.png', click_it=False) or \
               bot.find_in_folder('system', 'go_to_interlude_list.png', click_it=False): break
                
            if self.ctx.config.get('interlude_mode', False) and self.ctx.vision.check_skip_button() in ["READY", "DARK"]: break
            if np.std(bot.current_screen_gray) < 5: self.ctx.smart_sleep(0.5); continue 
            
            bot.capture_screen()
            if bot.find_in_folder('system', 'go_to_interlude_list.png', click_it=False) or \
               bot.find_in_folder('system', 'menu_button.png', click_it=False):
                return "INIT"
            self.ctx.click(65, 65, times=1, duration=50); self.ctx.smart_sleep(0.2)

        if self.ctx.config.get('interlude_mode', False):
            self.ctx.smart_sleep(1.0); return "INIT"
            
        target_loops = self.ctx.config['loop_target']
        if target_loops > 0 and self.ctx.current_loop >= target_loops:
            self.ctx.update_status(f"🎉 任務達成：已完成 {self.ctx.current_loop} 場周回！", fg="green")
            bot.capture_screen()
            if bot.find_in_folder('system', 'continue_battle.png', click_it=False):
                if not bot.find_in_folder('system', 'close_btn.png'): self.ctx.click(650, 850) 
                self.ctx.smart_sleep(3.0) 
            self.ctx.running = False; return "RESULT"
        else:
            bot.capture_screen() 
            if bot.find_in_folder('system', 'continue_battle.png'):
                self.ctx.current_loop += 1; self.ctx.smart_sleep(5); return "INIT" 
            elif bot.find_in_folder('system', 'menu_button.png', click_it=False):
                self.ctx.current_loop += 1; self.ctx.smart_sleep(3); return "INIT" 
            else:
                self.ctx.update_status("⛔ 狀態：結算卡死 (能量耗盡?)，腳本停止", fg="red")
                self.ctx.running = False; return "RESULT"

    def handle_defeat_state(self):
        self.ctx.update_status("狀態：戰鬥失敗，執行撤退程序...", fg="red")
        timeout = time.time() + 25.0
        while time.time() < timeout and self.ctx.running:
            self.ctx.bot.capture_screen()
            if self.ctx.bot.find_in_folder('system', 'retreat_btn.png', click_it=True): self.ctx.smart_sleep(1.0); continue
            if self.ctx.bot.find_in_folder('system', 'retreat_decide_btn.png', click_it=True): self.ctx.smart_sleep(1.5); continue
            if self.ctx.bot.find_in_folder('system', 'close_btn.png', click_it=True): self.ctx.smart_sleep(2.0); continue
            if self.ctx.bot.find_in_folder('system', 'menu_button.png', click_it=False): break
            self.ctx.smart_sleep(0.5)
            
        self.ctx.update_status("⛔ 狀態：已從任務撤退，強制終止周回腳本。", fg="red")
        self.ctx.running = False 
        return "DEFEAT"