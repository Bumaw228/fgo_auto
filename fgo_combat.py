import os
import time
import random
import cv2
import numpy as np
import re

from coords import (
    SKILLS, MASTER_SKILLS, MASTER_BTN, TARGETS, ENEMIES, NP_CARDS,
    CARDS, ATTACK_BTN, BLANK_SPOT, SERVANT_PORTRAIT,
    ORDER_FRONT, ORDER_BACK, ORDER_CONFIRM_BTN, ORDER_CHANGE_SKILL,
    ORDER_CONFIRM_BRIGHT, ORDER_CHANGE_MAX_RETRY, ORDER_DEBUG,
    ORDER_SLOT_X, ORDER_SELECT_Y, ORDER_SELECT_ASSET,
    SKIP_CLICK_EVERY,
    AI_TARGET_POSITIONS,
)

class FGOCombat:
    def __init__(self, context):
        self.ctx = context
        self.current_wave = 0

    def reset_battle_state_if_needed(self):
        print("🔄 [啟動防護] 從戰鬥中啟動，執行 UI 強制重置...")
        bot = self.ctx.bot
        bot.capture_screen()

        # 🚀 這裡刻意「不做智慧判斷」，一律執行重置。原因：
        #    1. 只看 Attack 按鈕不夠 —— 御主技能欄展開時 Attack 仍然看得見
        #    2. 想改看 order_change_btn 也不行 —— 該技能進 CD 後外觀會變（變暗＋剩餘字樣），
        #       而且不是每個御主禮裝都有換人技能
        #    這個重置整個腳本執行期間只會跑一次，約 5 秒，
        #    用固定成本換取「絕不誤判」，對長時間掛機而言划算得多。
        
        if self.ctx.bot.find_in_folder('system', 'servant_detail_close_x.png', click_it=True):
            print("✅ 偵測到角色詳情已在開啟狀態，直接關閉洗白 UI！")
            self.ctx.smart_sleep(1.0)
            return

        self.ctx.click(*SERVANT_PORTRAIT, times=3, duration=50) 
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
        
        # 🚀 雙階段等待法 (Two-Phase Wait)
        # 每次點擊都是一趟 ADB 呼叫（約 110ms），而 FGO 只要點一下就會跳過動畫，
        # 因此改成每 SKIP_CLICK_EVERY 輪才點一次，仍保有防 lag 的冗餘。
        loops = 0

        # 階段一：等待 Attack 按鈕「消失」（代表技能動畫開始）
        animation_started = False
        timeout_start = time.time() + 1.5 # 最多等 1.5 秒讓 UI 消失
        while time.time() < timeout_start and self.ctx.running:
            if do_click and loops % SKIP_CLICK_EVERY == 0:
                self.ctx.click(*BLANK_SPOT, duration=50)
            loops += 1
            self.ctx.bot.capture_screen()
            if not self.ctx.bot.find_in_folder('system', 'attack.png', click_it=False):
                animation_started = True
                break
            self.ctx.smart_sleep(0.15)

        # 階段二：如果 Attack 按鈕真的消失了，才耐心等待它「重新出現」（動畫結束）
        # 如果第一階段等了 1.5 秒都沒消失，代表那是瞬間發動的 Buff，直接跳過階段二！
        if animation_started:
            loops = 0   # 動畫剛開始，重新計數確保第一輪就點一下
            timeout_end = time.time() + timeout_sec
            while time.time() < timeout_end and self.ctx.running:
                if do_click and loops % SKIP_CLICK_EVERY == 0:
                    self.ctx.click(*BLANK_SPOT, duration=50)
                loops += 1
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
                if is_master_skill: self.ctx.click(*MASTER_BTN); self.ctx.smart_sleep(0.4) 
                else: self.ctx.click(*BLANK_SPOT, times=2, duration=50)
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
                            self.ctx.click(*BLANK_SPOT, duration=50) 
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
                        self.ctx.click(*BLANK_SPOT, duration=50) 
                        self.ctx.smart_sleep(0.15) 
                    return 

                # 🚀 同上，完美銜接
                self.wait_attack_and_skip(do_click=True)
                return
            self.ctx.smart_sleep(0.5)

        if skill_mode != "極限盲操":
            if is_master_skill: self.ctx.click(*MASTER_BTN); self.ctx.smart_sleep(0.6) 
            else: self.ctx.click(*BLANK_SPOT, times=2, duration=50)
            self.wait_attack_and_skip(do_click=True)

    def select_battle_cards(self, current_wave=99):
        is_ai_mode = self.ctx.config.get('ai_card_mode', False)
        is_auto_np = self.ctx.config.get('auto_np_mode', True)
        priority_str = self.ctx.config.get('card_priority', "無")
        script_len = len(self.ctx.config.get('script_data', []))
        can_auto_np = (self.ctx.config['battle_mode'] == "random") or (current_wave >= script_len)

        if not is_ai_mode:
            if is_auto_np and can_auto_np:
                for nx, ny in NP_CARDS[1:]:
                    self.ctx.click(nx, ny); self.ctx.smart_sleep(0.15)
            cards = list(CARDS)
            random.shuffle(cards)
            for i in range(3): self.ctx.click(cards[i][0], cards[i][1]); self.ctx.smart_sleep(0.25)
            self.ctx.smart_sleep(0.2); self.ctx.click(cards[3][0], cards[3][1]) 
            return

        print(f"🧠 [AI 決策] 啟動智能選卡！(戰略: {priority_str})")
        if is_auto_np and can_auto_np:
            np_cards = NP_CARDS[1:]
            self.ctx.bot.capture_screen()
            img = self.ctx.bot.current_screen
            for i, (nx, ny) in enumerate(np_cards):
                roi = img[ny-20:ny+20, nx-20:nx+20]
                if roi.size > 0:
                    v_val = np.mean(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)[:, :, 2])
                    if v_val > 140: 
                        self.ctx.click(nx, ny); self.ctx.smart_sleep(0.15)
            
        color_order = [] if priority_str == "無" else [c.strip() for c in priority_str.split('>')]
        cards = list(CARDS)
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

    @staticmethod
    def _safe_pos(table, idx, label, cmd):
        """安全地從座標表取值。

        指令來自 JSON 設定檔，使用者可能手動編輯而寫出超出範圍的編號
        （例如 E0、S12）。這裡統一擋下來，印出提示並略過該指令，
        避免整個腳本因為一個手誤而崩潰。
        """
        if not isinstance(idx, int) or idx < 1 or idx >= len(table) or table[idx] is None:
            print(f"⚠️ [腳本] 指令 '{cmd}' 的{label}編號 {idx} 超出範圍 "
                  f"(可用 1~{len(table) - 1})，已略過這道指令。")
            return None
        return table[idx]

    def _close_order_change_panel(self):
        """換人失敗時強制關閉面板，讓腳本能回到可操作的戰鬥畫面。

        換人面板是覆蓋整個畫面的獨立視窗，點 master_btn 對它無效，
        必須按右上角的叉叉（與從者詳情共用同一顆按鈕）。
        """
        for attempt in range(1, 4):
            self.ctx.bot.capture_screen()
            if not self.ctx.bot.find_in_folder('system', 'order_change_confirm_btn.png', click_it=False):
                print("✅ 換人面板已關閉，回到戰鬥畫面")
                return True
            if self.ctx.bot.find_in_folder('system', 'servant_detail_close_x.png', click_it=True):
                print(f"🚪 按下關閉鈕退出換人面板（第 {attempt} 次）")
            else:
                print(f"⚠️ 找不到關閉鈕（第 {attempt} 次），改點空白處嘗試脫困")
                self.ctx.click(*BLANK_SPOT, duration=50)
            self.ctx.smart_sleep(1.0)

        print("❌ 無法關閉換人面板，後續指令可能失效")
        return False

    def _detect_order_selection(self):
        """用畫面上的 SELECT 標記判斷前後排各選了誰。

        回傳 (前排編號清單, 後排編號清單)，若素材不存在則回傳 None
        讓呼叫端退回舊的亮度判斷法。

        只用 x 座標歸屬格子：六格橫向分得很開（間距約 295px），
        因此不需要知道 SELECT 標記相對格子的精確偏移。
        """
        path = os.path.join(self.ctx.bot.sys_path, ORDER_SELECT_ASSET)
        if not os.path.exists(path):
            return None

        self.ctx.bot.capture_screen()
        points = self.ctx.bot.find_all_by_abspath(path, threshold=0.8)

        y_lo, y_hi = ORDER_SELECT_Y
        front, back = [], []
        for x, y in points:
            if not (y_lo <= y <= y_hi):
                continue          # 不在換人畫面該有的高度，視為誤判
            for (side, idx), (x1, x2) in ORDER_SLOT_X.items():
                if x1 <= x <= x2:
                    (front if side == "front" else back).append(idx)
                    break

        front.sort(); back.sort()
        if ORDER_DEBUG:
            print(f"🔬 [換人診斷] SELECT 偵測 → 前排 {front or '無'}｜後排 {back or '無'}"
                  f"（共找到 {len(points)} 個標記）")
        return front, back

    def _fix_side(self, side_name, slots, want, selected):
        """讓某一排只選中 want 這一個格子。

        FGO 點擊已選中的格子會取消選取，所以選錯人時要先點掉再點對的。
        """
        for wrong in selected:
            if wrong != want:
                print(f"↩️ {side_name}選到 {wrong} 不是 {want}，先取消")
                self.ctx.click(*slots[wrong]); self.ctx.smart_sleep(0.35)
        if want not in selected:
            self.ctx.click(*slots[want]); self.ctx.smart_sleep(0.35)

    def _do_order_change_by_select(self, f, b):
        """以 SELECT 標記為依據執行換人。成功回傳 True，素材不存在回傳 None。"""
        if self._detect_order_selection() is None:
            return None

        for attempt in range(1, ORDER_CHANGE_MAX_RETRY + 1):
            if not self.ctx.running:
                return False

            state = self._detect_order_selection()
            if state is None:
                return None
            front, back = state

            if front == [f] and back == [b]:
                self.ctx.click(*ORDER_CONFIRM_BTN); self.ctx.smart_sleep(1.0)
                self.ctx.bot.capture_screen()
                if not self.ctx.bot.find_in_folder('system', 'order_change_confirm_btn.png', click_it=False):
                    if attempt > 1:
                        print(f"✅ 換人成功（第 {attempt} 輪）")
                    return True
                print("⚠️ 確定鈕按下後面板仍在，重試")
                continue

            print(f"🔧 修正選取（第 {attempt} 輪）：目前前排 {front or '無'}／後排 {back or '無'}"
                  f"，目標 前{f} 後{b}")
            self._fix_side("前排", ORDER_FRONT, f, front)
            self._fix_side("後排", ORDER_BACK, b, back)

        print(f"❌ 換人重試 {ORDER_CHANGE_MAX_RETRY} 次仍未成功，改為關閉面板繼續戰鬥")
        self._close_order_change_panel()
        return False

    def _log_confirm_brightness(self, stage):
        """開發用：印出確定鈕當下的亮度，供校準 ORDER_CONFIRM_BRIGHT。"""
        if not ORDER_DEBUG:
            return
        self.ctx.bot.capture_screen()
        pos = self.ctx.bot.find_in_folder('system', 'order_change_confirm_btn.png', click_it=False)
        if pos:
            _, v = self.ctx.vision.get_skill_color_stats(pos[0], pos[1])
            print(f"🔬 [換人診斷] {stage}｜確定鈕亮度 {v:.0f}（目前門檻 {ORDER_CONFIRM_BRIGHT}）")
        else:
            print(f"🔬 [換人診斷] {stage}｜畫面上找不到確定鈕")

    def _order_change_state(self):
        """判斷換人面板目前的狀態。

        回傳 (面板是否開啟, 確定鈕是否為可按的亮色, 亮度值)。
        確定鈕在面板開啟期間一直存在，只是前後排都選滿之前呈暗色，
        所以「亮不亮」才是判斷選取是否完成的依據。
        """
        self.ctx.bot.capture_screen()
        pos = self.ctx.bot.find_in_folder('system', 'order_change_confirm_btn.png', click_it=False)
        if not pos:
            return False, False, 0.0
        _, v = self.ctx.vision.get_skill_color_stats(pos[0], pos[1])
        return True, v > ORDER_CONFIRM_BRIGHT, float(v)

    def _do_order_change(self, f_pos, b_pos, f_idx, b_idx):
        """執行一次換人，並在失敗時重試。

        失敗有三種可能：前排沒點到、後排沒點到、確定鈕沒點到。
        這裡不去猜是哪一種，而是直接看確定鈕的狀態：
          亮著 = 兩邊都選好了，純粹是確定鈕沒點到 → 重按確定
          暗著 = 選取不完整 → 依序補點前後排（點到已選中的會取消，
                 所以每點一次就重新確認一次狀態，最多幾次就會收斂）
        """
        # 🚀 優先使用 SELECT 標記判斷（確定性高），素材不存在才退回亮度判斷
        result = self._do_order_change_by_select(f_idx, b_idx)
        if result is not None:
            return result

        self._log_confirm_brightness("尚未選取")
        self.ctx.click(*f_pos); self.ctx.smart_sleep(0.3)
        self.ctx.click(*b_pos); self.ctx.smart_sleep(0.3)
        self._log_confirm_brightness("前後排都已選取")   # ← 這行印出的就是「可按」狀態的亮度
        self.ctx.click(*ORDER_CONFIRM_BTN); self.ctx.smart_sleep(1.0)

        for attempt in range(1, ORDER_CHANGE_MAX_RETRY + 1):
            if not self.ctx.running:
                return False
            is_open, ready, v = self._order_change_state()

            if not is_open:
                if attempt > 1:
                    print(f"✅ 換人成功（第 {attempt - 1} 次重試）")
                return True

            print(f"⚠️ 換人未完成（第 {attempt} 次檢查）｜確定鈕亮度 {v:.0f}"
                  f"（門檻 {ORDER_CONFIRM_BRIGHT}）→ {'可按' if ready else '尚未選滿'}")

            if ready:
                self.ctx.click(*ORDER_CONFIRM_BTN); self.ctx.smart_sleep(1.0)
                continue

            # 選取不完整：補點前排，若仍未選滿再補後排
            self.ctx.click(*f_pos); self.ctx.smart_sleep(0.4)
            _, ready, _ = self._order_change_state()
            if not ready:
                self.ctx.click(*b_pos); self.ctx.smart_sleep(0.4)
            self.ctx.click(*ORDER_CONFIRM_BTN); self.ctx.smart_sleep(1.0)

        is_open, _, _ = self._order_change_state()
        if is_open:
            print(f"❌ 換人重試 {ORDER_CHANGE_MAX_RETRY} 次仍未成功，改為關閉面板繼續戰鬥")
            self._close_order_change_panel()
            return False
        return True

    def execute_script_from_list(self, wave_idx):
        cmds = self.ctx.config['script_data'][wave_idx]
        if not cmds: return False 
        skill_mode = self.ctx.config.get('skill_mode', '智慧安全')
        
        # 🚀 座標統一由 coords.py 管理，改版時只需修改該檔案
        enemies = ENEMIES
        skills = SKILLS
        targets = TARGETS
        nps = NP_CARDS
        master_btn = MASTER_BTN
        m_skills = MASTER_SKILLS
        o_front = ORDER_FRONT
        o_back = ORDER_BACK
        order_change_confirm_btn = ORDER_CONFIRM_BTN
        
        attack_opened = False 

        for c in cmds:
            if not self.ctx.running: break
            
            if c.startswith('E'):
                match = re.match(r'E(\d+)', c)
                if match:
                    idx = int(match.group(1))
                    pos = self._safe_pos(enemies, idx, "敵方", c)
                    if pos is None: continue
                    self.ctx.click(*pos); self.ctx.smart_sleep(0.4) 
                    self.wait_attack_and_skip(timeout_sec=5.0, do_click=True)
                    
            elif c.startswith('N'):
                match = re.match(r'N(\d+)', c)
                if match:
                    if not attack_opened:
                        if skill_mode == "極限盲操": self.wait_attack_and_skip(timeout_sec=8.0, do_click=False); self.ctx.smart_sleep(0.2)
                        self.ctx.smart_sleep(0.1); self.ctx.click(*ATTACK_BTN)
                        self.ctx.smart_sleep(1.0)
                        attack_opened = True
                    idx = int(match.group(1))
                    pos = self._safe_pos(nps, idx, "寶具", c)
                    if pos is None: continue
                    self.ctx.click(*pos); self.ctx.smart_sleep(0.15) 
                    
            elif c.startswith('S'):
                match = re.match(r'S(\d+)(_[a-z]+)?(?:-(\d+))?', c)
                if match:
                    s_idx = int(match.group(1))
                    modifier = match.group(2)[1:] if match.group(2) else None
                    skill_pos = self._safe_pos(skills, s_idx, "技能", c)
                    if skill_pos is None: continue
                    target_pos = None
                    if match.group(3):
                        target_pos = self._safe_pos(targets, int(match.group(3)), "對象", c)
                        if target_pos is None: continue
                    self.smart_cast_skill(skill_pos[0], skill_pos[1], modifier, target_pos)
                    
            elif c.startswith('M'):
                match = re.match(r'M(\d+)(?:-(\d+))?', c)
                if match:
                    # 🚀 先驗證編號，通過了才動畫面。
                    #    這樣非法指令完全不會碰到 UI，也就不需要事後收拾。
                    m_pos = self._safe_pos(m_skills, int(match.group(1)), "御主技能", c)
                    if m_pos is None: continue
                    target_pos = None
                    if match.group(2):
                        target_pos = self._safe_pos(targets, int(match.group(2)), "對象", c)
                        if target_pos is None: continue

                    if skill_mode == "極限盲操": self.wait_attack_and_skip(timeout_sec=8.0, do_click=False); self.ctx.smart_sleep(0.2)
                    self.ctx.click(*master_btn)
                    self.ctx.smart_sleep(1.0)
                    self.smart_cast_skill(m_pos[0], m_pos[1], target_pos=target_pos, is_master_skill=True)
                    
            elif c.startswith('O'):
                match = re.match(r'O-(\d+)-(\d+)', c)
                if match:
                    # 🚀 先驗證前後排編號，避免開了技能列才發現指令不合法
                    f, b = int(match.group(1)), int(match.group(2))
                    f_pos = self._safe_pos(o_front, f, "場上位置", c)
                    b_pos = self._safe_pos(o_back, b, "後備位置", c)
                    if f_pos is None or b_pos is None: continue

                    if skill_mode == "極限盲操": self.wait_attack_and_skip(timeout_sec=8.0, do_click=False); self.ctx.smart_sleep(0.2)
                    self.ctx.click(*master_btn)
                    self.ctx.smart_sleep(1.0)

                    # 🚀 換人所在的御主技能格數可設定：不同御主禮裝位置未必都在第 3 格
                    oc_slot = int(self.ctx.config.get('order_change_slot', 3))
                    oc_skill = self._safe_pos(m_skills, oc_slot, "換人技能格", c)
                    if oc_skill is None:
                        self.ctx.click(*master_btn); self.ctx.smart_sleep(0.6); continue

                    is_order_change_cd = False
                    self.ctx.bot.capture_screen()
                    _, v_before = self.ctx.vision.get_skill_color_stats(*oc_skill)
                    if skill_mode == "智慧安全":
                        if self.ctx.vision.check_skill_cooldown_visual(*oc_skill, is_master=True):
                            is_order_change_cd = True
                        elif v_before < 60:
                            is_order_change_cd = True

                    if is_order_change_cd:
                        print("⏩ 換人技能處於 CD 狀態，自動跳過")
                        self.ctx.click(*master_btn); self.ctx.smart_sleep(0.6); continue

                    self.ctx.click(*oc_skill)
                    self.ctx.smart_sleep(1.2)

                    if not self._do_order_change(f_pos, b_pos, f, b):
                        # 面板已在 _do_order_change 內關閉，這裡直接跳過這道指令，
                        # 讓後續流程回到正常的 Attack 選卡
                        self.ctx.smart_sleep(0.5)
                        continue

                    self.ctx.smart_sleep(3.0)
                    self.wait_attack_and_skip(timeout_sec=20.0, do_click=True)

            self.ctx.smart_sleep(0.1)
        return attack_opened

    def wait_for_next_turn_dynamic(self):
        self.ctx.update_status("狀態：等待攻擊結束 (加速跳過中...)")
        timeout = time.time() + 150.0 
        while time.time() < timeout and self.ctx.running:
            self.ctx.click(*BLANK_SPOT, duration=50)
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
                skill_coords = SKILLS
                
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
                        all_target_positions = AI_TARGET_POSITIONS
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
                    self.ctx.click(*ATTACK_BTN); self.ctx.smart_sleep(2.5); bot.capture_screen()
                    if bot.find_in_folder('system', 'attack.png', click_it=False):
                        self.ctx.click(*ATTACK_BTN); self.ctx.smart_sleep(2.5) 
                
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
                self.ctx.smart_sleep(1.5); self.ctx.click(*ATTACK_BTN); self.ctx.smart_sleep(2.5)
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