import time
from fgo_core import FGOBot
from fgo_vision import FGOVision
from fgo_combat import FGOCombat
from fgo_nav import FGONav
from coords import SERVANT_PORTRAIT

# 🚀 專屬中斷例外，用來達成 0.1 秒瞬間停止腳本
class ScriptStoppedException(Exception):
    pass

class FGOLogic:
    def __init__(self, config, status_callback, stop_callback):
        self.config = config
        self.update_status_cb = status_callback
        self.stop_cb = stop_callback
        
        self.running = True
        self.current_loop = 1
        self.current_state = "INIT"
        self.is_first_action = True  # 🚀 新增：用來記錄腳本是不是「剛按下開始」
        
        self.bot = FGOBot(self.config['device_id'],
                          use_roi=self.config.get('use_roi', True))
        
        # 🌟 啟動 Context 注入模式，將自己傳遞給各大子模組
        self.vision = FGOVision(self)
        self.combat = FGOCombat(self)
        self.nav = FGONav(self)

    # ==========================================
    # 🔌 底層共用工具 API (所有子模組都會透過這裡操作)
    # ==========================================
    def check_running(self):
        """檢查是否被使用者按下停止，如果是，立刻拋出例外打斷所有迴圈"""
        if not self.running:
            raise ScriptStoppedException("腳本已被使用者強制停止")

    def click(self, x, y, times=1, duration=120):
        for _ in range(times): 
            self.check_running()
            self.bot.smart_click(x, y, duration)

    def swipe(self, x1, y1, x2, y2, duration=400):
        self.check_running()
        self.bot.smart_swipe(x1, y1, x2, y2, duration)

    def update_status(self, text, fg="blue"):
        self.update_status_cb(text, fg)

    def smart_sleep(self, seconds):
        end_time = time.time() + seconds
        while time.time() < end_time:
            self.check_running() 
            time.sleep(0.1)
        return True

    # ==========================================
    # 🧠 主狀態機迴圈 (極致瘦身！)
    # ==========================================
    def run_logic(self):
        self.update_status("狀態：腳本啟動，進行全局畫面掃描...")
        try:
            while self.running:
                self.check_running()
                
                if not self.bot.capture_screen():
                    self.smart_sleep(0.5)
                    continue

                # 🛑 頂層防護網：全域崩潰攔截
                if self.bot.find_in_folder('system', 'inventory_full_close.png', click_it=True):
                    self.update_status("⛔ 狀態：倉庫已滿，腳本已停止！", fg="red")
                    break

                if self.bot.find_in_folder('system', 'network_retry.png', click_it=False) or \
                   self.bot.find_in_folder('system', 'close_x.png', click_it=False) or \
                   self.bot.find_in_folder('system', 'fgo_icon.png', click_it=False):
                    self.update_status("⚠️ 狀態：發生異常(斷線/閃退)，已停止！", fg="red")
                    break

                # 🔄 狀態機路由器 (State Router)
                if self.current_state == "INIT":
                    self.current_state = self.nav.handle_init_state()
                elif self.current_state == "STORY":
                    self.current_state = self.nav.handle_story_state()
                elif self.current_state == "IDLE":
                    self.current_state = self.nav.handle_idle_state()
                elif self.current_state == "SUPPORT":
                    self.current_state = self.nav.handle_support_state()
                elif self.current_state == "TEAM_SELECT":
                    self.current_state = self.nav.handle_team_select_state()
                elif self.current_state == "BATTLE":
                    self.current_state = self.combat.handle_battle_state()
                elif self.current_state == "RESULT":
                    self.current_state = self.nav.handle_result_state()
                elif self.current_state == "DEFEAT":
                    self.current_state = self.nav.handle_defeat_state()

                # 🚀 笨笨但最有效的「首次啟動防護」
                # 如果這是按下開始後的第一次畫面判定，且剛好是戰鬥畫面
                if self.is_first_action and self.current_state != "INIT":
                    self.is_first_action = False # 只要找到任何明確的狀態，就解除啟動標記
                    
                    if self.current_state == "BATTLE":
                        self.update_status("狀態：首次進入戰鬥，強制洗白 UI...", fg="orange")
                        print("🚀 [啟動防護] 偵測到從戰鬥中啟動腳本！強制執行 UI 洗白 (無視 Attack 判斷)...")
                        
                        # 暴力洗白：長按角色開啟詳情，然後關閉 (這能強制覆蓋並關掉御主技能)
                        self.click(*SERVANT_PORTRAIT, times=3, duration=50) 
                        self.smart_sleep(1.5) 
                        
                        timeout = time.time() + 3.0
                        while time.time() < timeout and self.running:
                            self.bot.capture_screen()
                            if self.bot.find_in_folder('system', 'servant_detail_close_x.png', click_it=True):
                                print("✅ 成功關閉角色詳情，戰鬥 UI 已強制重置為乾淨狀態！")
                                self.smart_sleep(1.0)
                                break
                            self.smart_sleep(0.2)

                self.smart_sleep(0.5)

        except ScriptStoppedException:
            print("🛑 收到中斷訊號，腳本瞬間安全停止！")
        except Exception as e: 
            print(f"Error: {e}")
        finally:
            self.stop_cb()