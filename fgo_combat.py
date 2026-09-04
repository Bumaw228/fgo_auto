import time
import random
import cv2
import numpy as np
import re  

class FGOCombat:
    def __init__(self, context):
        self.ctx = context
        self.current_wave = 0

    def reset_battle_state_if_needed(self):
        print("🔄 [戰鬥狀態檢查] 掃描是否需要洗白 UI...")
        self.ctx.bot.capture_screen()
        
        if self.ctx.bot.find_in_folder('system', 'attack.png', click_it=False):
            print("✅ [智慧跳過] 畫面已是乾淨的戰鬥首頁，不執行強制洗白，直接開打！")
            return

        print("⚠️ [系統初始化] 未偵測到 Attack，可能卡在技能或御主選單，執行戰鬥狀態強制重置...")
        
        if self.ctx.bot.find_in_folder('system', 'servant_detail_close_x.png', click_it=True):
            print("✅ 偵測到角色詳情已在開啟狀態，直接關閉洗白 UI！")
            self.ctx.smart_sleep(1.0)
            return

        self.ctx.click(705, 670, times=3, duration=50) 
        self.ctx.smart_sleep(1.5) 
        
        timeout = time.time() + 3.0
        while time.time() < timeout and self.ctx.running:
            self.ctx.bot.capture_screen()
            if self.ctx.bot.find_in_folder('system', 'servant_detail_close_x.png', click_it=True):
                print("✅ 成功關閉角色詳情，戰鬥 UI 已重置為乾淨狀態！")
                self.ctx.smart_sleep(1.0)
                return
            self.ctx.smart_sleep(0.2)
        print("⚠️ 未偵測到角色詳情專屬叉叉，假設畫面已是乾淨狀態。")

    def wait_for_target_window(self, timeout_sec=3.0):
        timeout = time.time() + timeout_sec
        while time.time() < timeout and self.ctx.running:
            self.ctx.bot.capture_screen()
            if self.ctx.bot.find_in_folder('system', 'select_target_text.png', click_it=False):
                return True
            self.ctx.smart_sleep(0.1)
        print("⚠️ 警告：等待目標視窗超時，強制放行盲點！")
        return False

    def wait_attack_and_skip(self, timeout_sec=15.0, do_click=True):
        if not self.ctx.running: return
        
        # 🚀 終極解法：雙階段等待法 (Two-Phase Wait)
        # 階段一：等待 Attack 按鈕「消失」（代表技能動畫開始）
        animation_started = False
        timeout_start = time.time() + 1.5 # 最多等 1.5 秒讓 UI 消失
        while time.time() < timeout_start and self.ctx.running:
            if do_click: self.ctx.click(1750, 150, duration=50) 
            self.ctx.bot.capture_screen()
            if not self.ctx.bot.find_in_folder('system', 'attack.png', click_it=False):
                animation_started = True
                break
            self.ctx.smart_sleep(0.15)
            
        # 階段二：如果 Attack 按鈕真的消失了，才耐心等待它「重新出現」（動畫結束）
        # 如果第一階段等了 1.5 秒都沒消失，代表那是瞬間發動的 Buff，直接跳過階段二！
        if animation_started:
            timeout_end = time.time() + timeout_sec
            while time.time() < timeout_end and self.ctx.running:
                if do_click: self.ctx.click(1750, 150, duration=50) 
                self.ctx.bot.capture_screen()
                if self.ctx.bot.find_in_folder('system', 'attack.png', click_it=False):
                    break
                self.ctx.smart_sleep(0.15)
                
        self.ctx.smart_sleep(0.1) # 給一點極短緩衝，確保 UI 可以點擊

    def smart_cast_skill(self, x, y, modifier=None, target_pos=None, is_master_skill=False):
        skill_mode = self.ctx.config.get('skill_mode', '智慧安全')
        extreme_sleep = float(self.ctx.config.get('extreme_sleep', 2.5))
        role_str = "御主" if is_master_skill else "從者"
        print(f"📊 [技能執行] 準備點擊 {role_str} 座標 ({x}, {y}) | 模式: {skill_mode}")
        
        if skill_mode == "智慧安全":
            self.ctx.bot.capture_screen() 
            s_before, v_before = self.ctx.vision.get_skill_color_stats(x, y)
            is_cd = False
            if self.ctx.vision.check_skill_cooldown_visual(x, y, is_master_skill):
                is_cd = True
            if not is_cd and v_before < 60:
                is_cd = True

            if is_cd:
                print(f"⏩ 偵測到{role_str}技能處於 CD 狀態，自動跳過！")
                if is_master_skill: self.ctx.click(1792, 472); self.ctx.smart_sleep(0.4) 
                else: self.ctx.click(1750, 150, times=2, duration=50)
                return

        max_retries = 2 if skill_mode != "極限盲操" else 1
        for attempt in range(max_retries):
            if not self.ctx.running: return
            self.ctx.click(x, y)
            
            if modifier:
                self.ctx.smart_sleep(0.4) 
                timeout = time.time() + 1.5 
                while time.time() < timeout and self.ctx.running:
                    self.ctx.bot.capture_screen() 
                    if modifier == "star":
                        pos = self.ctx.bot.find_in_folder('system', 'sp_use_star.png', click_it=False)
                        if pos:
                            s, v = self.ctx.vision.get_skill_color_stats(pos[0], pos[1])
                            if v > 120:
                                self.ctx.click(pos[0], pos[1]); self.ctx.smart_sleep(0.2); break
                            else:
                                if self.ctx.bot.find_in_folder('system', 'sp_no_star.png', click_it=True):
                                    self.ctx.smart_sleep(0.2); break
                    elif modifier == "nostar":
                        if self.ctx.bot.find_in_folder('system', 'sp_no_star.png', click_it=True):
                            self.ctx.smart_sleep(0.2); break
                    self.ctx.smart_sleep(0.1)

            if target_pos:
                target_ready = self.wait_for_target_window(2.5) if skill_mode == "智慧安全" else True
                if target_ready:
                    self.ctx.click(target_pos[0], target_pos[1])
                    self.ctx.smart_sleep(0.25)
                    
                    if skill_mode == "極限盲操":
                        end_time = time.time() + extreme_sleep
                        while time.time() < end_time and self.ctx.running: 
                            self.ctx.click(1750, 150, duration=50) 
                            self.ctx.smart_sleep(0.15) 
                        return 

                    # 🚀 套用雙階段等待，不再需要賭 2 秒了！
                    self.wait_attack_and_skip(do_click=True)
                    return
            else:
                self.ctx.smart_sleep(0.15)
                if skill_mode == "極限盲操":
                    end_time = time.time() + extreme_sleep
                    while time.time() < end_time and self.ctx.running: 
                        self.ctx.click(1750, 150, duration=50) 
                        self.ctx.smart_sleep(0.15) 
                    return 

                # 🚀 同上，完美銜接
                self.wait_attack_and_skip(do_click=True)
                return
            self.ctx.smart_sleep(0.5)

        if skill_mode != "極限盲操":
            if is_master_skill: self.ctx.click(1792, 472); self.ctx.smart_sleep(0.6) 
            else: self.ctx.click(1750, 150, times=2, duration=50)
            self.wait_attack_and_skip(do_click=True)

    def select_battle_cards(self, current_wave=99):
        is_ai_mode = self.ctx.config.get('ai_card_mode', False)
        is_auto_np = self.ctx.config.get('auto_np_mode', True)
        priority_str = self.ctx.config.get('card_priority', "無")
        script_len = len(self.ctx.config.get('script_data', []))
        can_auto_np = (self.ctx.config['battle_mode'] == "random") or (current_wave >= script_len)

        if not is_ai_mode:
            if is_auto_np and can_auto_np:
                for nx, ny in [(605, 300), (960, 300), (1315, 300)]:
                    self.ctx.click(nx, ny); self.ctx.smart_sleep(0.15)
            cards = [(195, 755), (580, 755), (960, 755), (1345, 755), (1735, 755)]
            random.shuffle(cards)
            for i in range(3): self.ctx.click(cards[i][0], cards[i][1]); self.ctx.smart_sleep(0.25)
            self.ctx.smart_sleep(0.2); self.ctx.click(cards[3][0], cards[3][1]) 
            return

        print(f"🧠 [AI 決策] 啟動智能選卡！(戰略: {priority_str})")
        if is_auto_np and can_auto_np:
            np_cards = [(605, 300), (960, 300), (1315, 300)]
            self.ctx.bot.capture_screen()
            img = self.ctx.bot.current_screen
            for i, (nx, ny) in enumerate(np_cards):
                roi = img[ny-20:ny+20, nx-20:nx+20]
                if roi.size > 0:
                    v_val = np.mean(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)[:, :, 2])
                    if v_val > 140: 
                        self.ctx.click(nx, ny); self.ctx.smart_sleep(0.15)
            
        color_order = [] if priority_str == "無" else [c.strip() for c in priority_str.split('>')]
        cards = [(195, 755), (580, 755), (960, 755), (1345, 755), (1735, 755)]
        card_scores = []
        self.ctx.bot.capture_screen()
        screen_color = self.ctx.bot.current_screen
        screen_gray = self.ctx.bot.current_screen_gray
        h, w = screen_gray.shape

        for idx, (cx, cy) in enumerate(cards):
            score = 0
            roi_c = screen_color[min(h, cy+50):min(h, cy+120), max(0, cx-60):min(w, cx+60)]
            if roi_c.size > 0:
                b, g, r = np.mean(roi_c, axis=(0, 1))
                card_color = "紅" if r>b and r>g else "藍" if b>r and b>g else "綠"
                if card_color in color_order: score += (30 - color_order.index(card_color)*10)
            
            roi_g = screen_gray[max(0, cy-250):max(0, cy+50), max(0, cx-120):min(w, cx+170)]
            weak_score, resist_score = 0.0, 0.0
            if self.ctx.vision.weak_tpl is not None:
                res_w = cv2.matchTemplate(roi_g, self.ctx.vision.weak_tpl, cv2.TM_CCOEFF_NORMED)
                weak_score = np.max(res_w)
            if self.ctx.vision.resist_tpl is not None:
                res_r = cv2.matchTemplate(roi_g, self.ctx.vision.resist_tpl, cv2.TM_CCOEFF_NORMED)
                resist_score = np.max(res_r)

            if weak_score > 0.7 and weak_score > resist_score: score += 500
            elif resist_score > 0.7 and resist_score > weak_score: score -= 500
            card_scores.append({'score': score, 'pos': (cx, cy)})

        card_scores.sort(key=lambda x: x['score'], reverse=True)
        for card in card_scores[:3]: 
            self.ctx.click(card['pos'][0], card['pos'][1]); self.ctx.smart_sleep(0.25)
        self.ctx.smart_sleep(0.3)
        self.ctx.click(card_scores[3]['pos'][0], card_scores[3]['pos'][1])

    def execute_script_from_list(self, wave_idx):
        cmds = self.ctx.config['script_data'][wave_idx]
        if not cmds: return False 
        skill_mode = self.ctx.config.get('skill_mode', '智慧安全')
        
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
            if not self.ctx.running: break
            
            if c.startswith('E'):
                match = re.match(r'E(\d+)', c)
                if match:
                    idx = int(match.group(1))
                    self.ctx.click(*enemies[idx]); self.ctx.smart_sleep(0.4) 
                    self.wait_attack_and_skip(timeout_sec=5.0, do_click=True)
                    
            elif c.startswith('N'):
                match = re.match(r'N(\d+)', c)
                if match:
                    if not attack_opened:
                        if skill_mode == "極限盲操": self.wait_attack_and_skip(timeout_sec=8.0, do_click=False); self.ctx.smart_sleep(0.2)
                        self.ctx.smart_sleep(0.1); self.ctx.click(1650, 920)
                        self.ctx.smart_sleep(1.0)
                        attack_opened = True
                    idx = int(match.group(1))
                    self.ctx.click(*nps[idx]); self.ctx.smart_sleep(0.15) 
                    
            elif c.startswith('S'):
                match = re.match(r'S(\d+)(_[a-z]+)?(?:-(\d+))?', c)
                if match:
                    s_idx = int(match.group(1))
                    modifier = match.group(2)[1:] if match.group(2) else None 
                    target_pos = targets[int(match.group(3))] if match.group(3) else None
                    self.smart_cast_skill(skills[s_idx][0], skills[s_idx][1], modifier, target_pos)
                    
            elif c.startswith('M'):
                match = re.match(r'M(\d+)(?:-(\d+))?', c)
                if match:
                    if skill_mode == "極限盲操": self.wait_attack_and_skip(timeout_sec=8.0, do_click=False); self.ctx.smart_sleep(0.2)
                    self.ctx.click(*master_btn)
                    self.ctx.smart_sleep(1.0)
                    m_idx = int(match.group(1))
                    target_pos = targets[int(match.group(2))] if match.group(2) else None
                    self.smart_cast_skill(m_skills[m_idx][0], m_skills[m_idx][1], target_pos=target_pos, is_master_skill=True)
                    
            elif c.startswith('O'):
                match = re.match(r'O-(\d+)-(\d+)', c)
                if match:
                    if skill_mode == "極限盲操": self.wait_attack_and_skip(timeout_sec=8.0, do_click=False); self.ctx.smart_sleep(0.2)
                    self.ctx.click(*master_btn)
                    self.ctx.smart_sleep(1.0)

                    is_order_change_cd = False
                    self.ctx.bot.capture_screen() 
                    s_before, v_before = self.ctx.vision.get_skill_color_stats(m_skills[3][0], m_skills[3][1])
                    if skill_mode == "智慧安全":
                        if self.ctx.vision.check_skill_cooldown_visual(m_skills[3][0], m_skills[3][1], is_master=True): is_order_change_cd = True
                        elif v_before < 60: is_order_change_cd = True

                    if is_order_change_cd:
                        self.ctx.click(1792, 472); self.ctx.smart_sleep(0.6); continue 

                    self.ctx.click(m_skills[3][0], m_skills[3][1])
                    self.ctx.smart_sleep(1.2)
                    
                    f, b = int(match.group(1)), int(match.group(2))
                    self.ctx.click(*o_front[f]); self.ctx.smart_sleep(0.3)
                    self.ctx.click(*o_back[b]); self.ctx.smart_sleep(0.3)
                    self.ctx.click(*order_change_confirm_btn); self.ctx.smart_sleep(1.0) 
                    
                    self.ctx.bot.capture_screen()
                    if self.ctx.bot.find_in_folder('system', 'order_change_confirm_btn.png', click_it=False):
                        print("⚠️ 換人失敗，請檢查座標！")
                    
                    self.ctx.smart_sleep(3.0)
                    self.wait_attack_and_skip(timeout_sec=20.0, do_click=True)

            self.ctx.smart_sleep(0.1)
        return attack_opened

    def wait_for_next_turn_dynamic(self):
        self.ctx.update_status("狀態：等待攻擊結束 (加速跳過中...)")
        timeout = time.time() + 150.0 
        while time.time() < timeout and self.ctx.running:
            self.ctx.click(1750, 150, duration=50)
            self.ctx.smart_sleep(0.2) 
            self.ctx.bot.capture_screen()
            
            if self.ctx.bot.find_in_folder('system', 'attack.png', click_it=False): return "BATTLE"
            if any(self.ctx.bot.find_in_folder('system', img) for img in ['bond_screen.png', 'exp_screen.png', 'next_btn.png']): return "RESULT"
            if self.ctx.bot.find_in_folder('system', 'back_btn.png', click_it=False): return "BATTLE"
        return "INIT"

    def handle_battle_state(self):
        bot = self.ctx.bot
        if bot.find_in_folder('system', 'attack.png', click_it=False):
            self.ctx.update_status(f"狀態：戰鬥中 (第 {self.current_wave + 1} 波)")
            if self.ctx.config.get('smart_turn_mode', False):
                self.ctx.smart_sleep(0.3); bot.capture_screen()
                if bot.find_in_folder('system', 'turn_1.png', click_it=False): self.current_wave = 0
                elif bot.find_in_folder('system', 'turn_2.png', click_it=False): self.current_wave = 1
                elif bot.find_in_folder('system', 'turn_3.png', click_it=False): self.current_wave = 2
                else: self.current_wave = 99 
            
            attack_opened = False
            is_random_mode = (self.ctx.config['battle_mode'] == "random")
            is_script_mode = (self.ctx.config['battle_mode'] == "script")
            
            if is_script_mode and self.current_wave < len(self.ctx.config['script_data']):
                attack_opened = self.execute_script_from_list(self.current_wave)
            
            # 全自動 AI / 殘局補招 
            if not attack_opened and (is_random_mode or (is_script_mode and self.current_wave >= len(self.ctx.config['script_data']))):
                self.ctx.update_status("狀態：戰鬥中 - AI 判斷可用技能並自動施放...")
                self.ctx.bot.capture_screen() 
                available_skills = self.ctx.vision.check_skill_available_batch(is_master=False)
                skills_to_use = [i for i, avail in enumerate(available_skills) if avail][:3]
                skill_coords = [None, (111, 871), (244, 871), (376, 871), (586, 871), (716, 871), (847, 871), (1060, 871), (1191, 871), (1324, 871)]
                
                for s_idx in skills_to_use:
                    if not self.ctx.running: break
                    self.ctx.click(*skill_coords[s_idx+1]); self.ctx.smart_sleep(0.8)
                    bot.capture_screen()
                    
                    star_pos = bot.find_in_folder('system', 'sp_use_star.png', click_it=False)
                    if star_pos:
                        s, v = self.ctx.vision.get_skill_color_stats(star_pos[0], star_pos[1])
                        if v > 120: self.ctx.click(star_pos[0], star_pos[1])
                        else: bot.find_in_folder('system', 'sp_no_star.png', click_it=True)
                        self.ctx.smart_sleep(0.5); bot.capture_screen() 
                    elif bot.find_in_folder('system', 'sp_no_star.png', click_it=True):
                        self.ctx.smart_sleep(0.5); bot.capture_screen()
                    
                    if bot.find_in_folder('system', 'select_target_text.png', click_it=False):
                        all_target_positions = [(485, 590), (725, 590), (965, 590), (1195, 590), (1425, 590)]
                        try_order = all_target_positions.copy()
                        if is_random_mode: random.shuffle(try_order)
                            
                        for tx, ty in try_order:
                            if not self.ctx.running: break
                            self.ctx.click(tx, ty); self.ctx.smart_sleep(0.6)
                            bot.capture_screen()
                            if not bot.find_in_folder('system', 'select_target_text.png', click_it=False): break 
                    self.wait_attack_and_skip(timeout_sec=6.0, do_click=True)

            if not self.ctx.running: return "BATTLE"
            
            # 補點剩餘卡片
            if not attack_opened:
                if self.ctx.config.get('skill_mode') == '極限盲操': self.wait_attack_and_skip(timeout_sec=8.0, do_click=False)
                bot.capture_screen() 
                if bot.find_in_folder('system', 'attack.png', click_it=False):
                    self.ctx.click(1650, 920); self.ctx.smart_sleep(2.5); bot.capture_screen()
                    if bot.find_in_folder('system', 'attack.png', click_it=False):
                        self.ctx.click(1650, 920); self.ctx.smart_sleep(2.5) 
                
            self.ctx.update_status("狀態：戰鬥中 - 選擇指令卡...")
            self.select_battle_cards(self.current_wave)
            
            # 等待戰鬥動畫
            attack_started = False
            timeout = time.time() + 3.0 
            while time.time() < timeout and self.ctx.running:
                bot.capture_screen()
                if not bot.find_in_folder('system', 'back_btn.png', click_it=False):
                    attack_started = True; break
                self.ctx.smart_sleep(0.3)

            if not attack_started:
                bot.find_in_folder('system', 'back_btn.png', click_it=True)
                self.ctx.smart_sleep(1.5); self.ctx.click(1650, 920); self.ctx.smart_sleep(2.5)
                self.select_battle_cards(self.current_wave); self.ctx.smart_sleep(1.0)

            self.ctx.smart_sleep(8)
            next_state = self.wait_for_next_turn_dynamic()
            if next_state == "BATTLE": self.current_wave += 1 
            return next_state
            
        elif any(bot.find_in_folder('system', img) for img in ['bond_screen.png', 'exp_screen.png', 'drop_screen.png', 'next_btn.png']):
            return "RESULT"
        
        elif bot.find_in_folder('system', 'retreat_btn.png', click_it=False):
            print("🔄 狀態切換：BATTLE -> DEFEAT")
            return "DEFEAT"
            
        return "BATTLE"