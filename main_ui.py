import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading
import os
import sys  
import cv2
import subprocess 
import json 
from fgo_core import FGOBot 
from fgo_logic import FGOLogic 
from PIL import Image, ImageTk
import ctypes
import traceback # 🚀 新增：用來捕捉詳細錯誤訊息

# ==============================
# 🚀 終極路徑解決方案：防禦 _internal 陷阱與打包路徑問題
# ==============================
def get_base_dir():
    """判斷目前是 EXE 執行還是 Python 執行，確保路徑永遠在最外層"""
    if getattr(sys, 'frozen', False):
        # 正在以 PyInstaller 打包的 EXE 執行
        return os.path.dirname(sys.executable)
    # 正在以 Python 腳本執行
    return os.path.dirname(os.path.abspath(__file__))

# ==============================
# 🌟 設置 CustomTkinter 主題與效能
# ==============================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

ctk.deactivate_automatic_dpi_awareness()
ctk.set_window_scaling(1.0)
ctk.set_widget_scaling(1.0)

class FGOApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FGO 好玩遊戲輔助工具")
        self.root.geometry("700x850") 
        self.root.minsize(650, 800)
        
        # 破解 Windows 工作列圖示
        try:
            myappid = 'mycompany.myproduct.subproduct.version' 
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            ui_dir = os.path.join(get_base_dir(), "assets_ui")
            icon_path = os.path.join(ui_dir, "app_icon.ico")
            if os.path.exists(icon_path): self.root.iconbitmap(icon_path)
        except Exception as e: 
            print(f"載入 Icon 失敗: {e}")

        # ==========================================
        # 🌟 初始化變數
        # ==========================================
        self.running = False
        self.logic_thread = None 
        self.dot_count = 0 
        self.last_raw_image = None 
        self.entry_extreme_sleep = None 
        
        self.battle_mode = tk.StringVar(value="script")
        self.apple_mode = tk.StringVar(value="不自動回體")
        self.support_class = tk.StringVar(value="ALL")
        self.team_index = tk.StringVar(value="1") 
        self.loop_target = tk.StringVar(value="0") 
        self.extreme_sleep = tk.StringVar(value="2.5")
        self.skill_mode = tk.StringVar(value="智慧安全")
        
        self.skill_mode.trace_add("write", self.toggle_extreme_sleep_ui)
        
        self.ai_card_mode = tk.BooleanVar(value=False)
        self.card_priority = tk.StringVar(value="無")
        self.auto_np_mode = tk.BooleanVar(value=True) 
        self.auto_formation = tk.BooleanVar(value=False)
        self.interlude_mode = tk.BooleanVar(value=False)
        self.smart_turn_mode = tk.BooleanVar(value=False)

        self.script_data = [[], [], []] 
        self.target_servant_paths = [None, None, None]
        self.target_ce_paths = [None, None, None]
        self.selected_servants = [tk.StringVar(value="尚未選取") for _ in range(3)]
        self.selected_ces = [tk.StringVar(value="尚未選取") for _ in range(3)]

        def create_dropdown(parent, variable, values, width=100, **kwargs):
            combo = ctk.CTkComboBox(
                parent, variable=variable, values=values, width=width,
                state="readonly", fg_color="#3b3b3b", button_color="#5c5c5c", 
                button_hover_color="#737373", dropdown_fg_color="#2b2b2b",
                font=("Arial", 14), dropdown_font=("Arial", 14), **kwargs
            )
            if hasattr(combo, '_entry') and hasattr(combo, '_canvas'):
                combo._entry.bind("<Button-1>", lambda e: combo._canvas.event_generate("<Button-1>"), add="+")
            def on_mouse_wheel(event):
                current_vals = combo.cget("values")
                if not current_vals: return
                try: current_idx = current_vals.index(variable.get())
                except ValueError: current_idx = 0
                if event.delta > 0: new_idx = max(0, current_idx - 1)
                elif event.delta < 0: new_idx = min(len(current_vals) - 1, current_idx + 1)
                else: return
                variable.set(current_vals[new_idx])
                return "break" 
            combo.bind("<MouseWheel>", on_mouse_wheel)
            if hasattr(combo, '_entry'): combo._entry.bind("<MouseWheel>", on_mouse_wheel)
            if hasattr(combo, '_canvas'): combo._canvas.bind("<MouseWheel>", on_mouse_wheel)
            return combo
        self.create_dropdown = create_dropdown 

        self.setup_ui()
        self.update_dynamic_status()

    def toggle_extreme_sleep_ui(self, *args):
        if hasattr(self, 'entry_extreme_sleep') and self.entry_extreme_sleep:
            if self.skill_mode.get() == "極限盲操":
                self.entry_extreme_sleep.configure(state="normal")
            else:
                self.entry_extreme_sleep.configure(state="disabled")

    def setup_ui(self):
        # 頂部：ADB 連線
        top_frame = ctk.CTkFrame(self.root)
        top_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(top_frame, text="ADB 連線:", font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=10)
        self.entry_adb = ctk.CTkEntry(top_frame, width=160, font=("Arial", 14))
        self.entry_adb.insert(0, "127.0.0.1:5555")
        self.entry_adb.pack(side=tk.LEFT, padx=5)
        
        ctk.CTkButton(top_frame, text="自動偵測", command=self.detect_adb, width=80).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(top_frame, text="截圖測試", command=self.test_connection, width=80, fg_color="#6c757d", hover_color="#5a6268").pack(side=tk.LEFT, padx=5)
        
        self.led_indicator = ctk.CTkLabel(top_frame, text="●", text_color="red", font=("Arial", 28))
        self.led_indicator.pack(side=tk.LEFT, padx=10)

        # 中央：四大分頁
        self.tabview = ctk.CTkTabview(self.root)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=5)
        self.tabview._segmented_button.configure(font=("Arial", 15, "bold"))
        
        tab_basic = self.tabview.add("【 基本與周回 】")
        tab_support = self.tabview.add("【 助戰設定 】")
        tab_script = self.tabview.add("【 精準 3T 編輯 】")
        tab_sys = self.tabview.add("【 系統與進階 】")

        self.setup_tab_basic(tab_basic)
        self.setup_tab_support(tab_support)
        self.setup_tab_script(tab_script)
        self.setup_tab_sys(tab_sys)

        # 底部：控制區
        bottom_frame = ctk.CTkFrame(self.root, fg_color=("gray90", "gray12"), corner_radius=10)
        bottom_frame.pack(side=tk.BOTTOM, fill="x", padx=15, pady=10)

        self.label_status = ctk.CTkLabel(bottom_frame, text="狀態：待機中", text_color="#00CFFF", font=("Arial", 16, "bold"))
        self.label_status.pack(pady=10)

        ctrl_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        ctrl_frame.pack(pady=(0, 15))

        self.btn_start = ctk.CTkButton(ctrl_frame, text="🚀 開始", command=self.start_thread, fg_color="#28a745", hover_color="#218838", font=("Arial", 16, "bold"), width=120, height=45)
        self.btn_start.pack(side=tk.LEFT, padx=10)

        self.btn_stop = ctk.CTkButton(ctrl_frame, text="🛑 停止", command=self.stop_script, fg_color="#dc3545", hover_color="#c82333", font=("Arial", 16, "bold"), width=100, height=45, state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=10)

        self.btn_save = ctk.CTkButton(ctrl_frame, text="💾 存檔", command=self.save_profile, fg_color="#17a2b8", hover_color="#138496", font=("Arial", 16, "bold"), width=100, height=45)
        self.btn_save.pack(side=tk.LEFT, padx=10)

        self.btn_load = ctk.CTkButton(ctrl_frame, text="📂 讀檔", command=self.load_profile, fg_color="#ffc107", hover_color="#e0a800", text_color="black", font=("Arial", 16, "bold"), width=100, height=45)
        self.btn_load.pack(side=tk.LEFT, padx=10)

    # ==============================
    # 分頁設計
    # ==============================
    def setup_tab_basic(self, parent):
        f1 = ctk.CTkFrame(parent, fg_color="transparent"); f1.pack(fill="x", pady=10)
        ctk.CTkLabel(f1, text="出擊隊伍編號:", font=("Arial", 14)).pack(side=tk.LEFT, padx=15)
        self.create_dropdown(f1, self.team_index, [str(i) for i in range(1, 16)], 80).pack(side=tk.LEFT)
        
        ctk.CTkLabel(f1, text="蘋果補充:", font=("Arial", 14)).pack(side=tk.LEFT, padx=(30, 10))
        self.create_dropdown(f1, self.apple_mode, ["不自動回體", "銅蘋果", "青銅蘋果", "銀蘋果", "金蘋果"], 120).pack(side=tk.LEFT)

        f2 = ctk.CTkFrame(parent, fg_color="transparent"); f2.pack(fill="x", pady=10)
        ctk.CTkLabel(f2, text="目標周回次數:", font=("Arial", 14)).pack(side=tk.LEFT, padx=15)
        ctk.CTkEntry(f2, textvariable=self.loop_target, width=80, font=("Arial", 14)).pack(side=tk.LEFT)
        ctk.CTkLabel(f2, text="(0 = 無限刷到沒體/蘋果)", text_color="gray", font=("Arial", 12)).pack(side=tk.LEFT, padx=10)

        ctk.CTkLabel(parent, text="--- 戰鬥行為 ---", text_color="gray", font=("Arial", 14, "bold")).pack(pady=(20, 10))
        
        f3 = ctk.CTkFrame(parent, fg_color="transparent"); f3.pack(fill="x", pady=5)
        ctk.CTkRadioButton(f3, text="隨機選卡 (耍廢平A流)", variable=self.battle_mode, value="random", font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=15)
        ctk.CTkRadioButton(f3, text="精準 3T (請至分頁設定)", variable=self.battle_mode, value="script", font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=15)

        f4 = ctk.CTkFrame(parent, fg_color="transparent"); f4.pack(fill="x", pady=15, padx=15)
        ctk.CTkCheckBox(f4, text="每回合自動放寶具", variable=self.auto_np_mode, font=("Arial", 14)).pack(side=tk.LEFT)
        ctk.CTkCheckBox(f4, text="啟用 AI 視覺算牌", variable=self.ai_card_mode, font=("Arial", 14)).pack(side=tk.LEFT, padx=20)
        
        f5 = ctk.CTkFrame(parent, fg_color="transparent"); f5.pack(fill="x", pady=5)
        ctk.CTkLabel(f5, text="AI 優先順序:", font=("Arial", 14)).pack(side=tk.LEFT, padx=15)
        self.create_dropdown(f5, self.card_priority, ["無", "紅 > 藍 > 綠", "藍 > 綠 > 紅", "綠 > 藍 > 紅", "紅 > 綠 > 藍"], 130).pack(side=tk.LEFT)

    def setup_tab_support(self, parent):
        class_frame = ctk.CTkFrame(parent, fg_color="transparent") 
        class_frame.pack(pady=10, fill="x", padx=5)
        ctk.CTkLabel(class_frame, text="尋找職階：", font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=10)
        self.create_dropdown(class_frame, self.support_class, ["ALL", "Saber", "Archer", "Lancer", "Rider", "Caster", "Assassin", "Berserker", "Extra", "Mix"], 120).pack(side=tk.LEFT)

        img_frame = ctk.CTkFrame(parent, fg_color=("gray95", "gray20"))
        img_frame.pack(pady=5, fill="both", expand=True, padx=5)
        ctk.CTkLabel(img_frame, text="目標圖片 (符合任一即選取，全空則盲選)", font=("Arial", 15, "bold")).pack(anchor="w", padx=15, pady=10)
        
        ctk.CTkLabel(img_frame, text="【從者圖片】", text_color="#4F94CD", font=("Arial", 14)).pack(anchor="w", padx=15)
        for i in range(3):
            f = ctk.CTkFrame(img_frame, fg_color="transparent"); f.pack(fill="x", padx=15, pady=2)
            ctk.CTkButton(f, text=f"選取 {i+1}", command=lambda idx=i: self.select_img('servant', idx), width=60, height=28).pack(side=tk.LEFT)
            ctk.CTkButton(f, text="取下", command=lambda idx=i: self.remove_img('servant', idx), width=50, height=28, fg_color="#C13828", hover_color="#8B2519").pack(side=tk.LEFT, padx=8)
            ctk.CTkLabel(f, textvariable=self.selected_servants[i], text_color="#7FBBF0").pack(side=tk.LEFT)
            
        ctk.CTkLabel(img_frame, text="【禮裝圖片】", text_color="#A25AC6", font=("Arial", 14)).pack(anchor="w", padx=15, pady=(15,0))
        for i in range(3):
            f = ctk.CTkFrame(img_frame, fg_color="transparent"); f.pack(fill="x", padx=15, pady=2)
            ctk.CTkButton(f, text=f"選取 {i+1}", command=lambda idx=i: self.select_img('ce', idx), width=60, height=28).pack(side=tk.LEFT)
            ctk.CTkButton(f, text="取下", command=lambda idx=i: self.remove_img('ce', idx), width=50, height=28, fg_color="#C13828", hover_color="#8B2519").pack(side=tk.LEFT, padx=8)
            ctk.CTkLabel(f, textvariable=self.selected_ces[i], text_color="#C090E0").pack(side=tk.LEFT)

    def setup_tab_script(self, parent):
        wave_sel_frame = ctk.CTkFrame(parent, fg_color="transparent"); wave_sel_frame.pack(pady=5)
        self.edit_wave_idx = tk.IntVar(value=0)
        for i in range(3):
            ctk.CTkRadioButton(wave_sel_frame, text=f"Wave {i+1}", variable=self.edit_wave_idx, value=i, command=self.update_script_display, font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=20)

        self.script_display = ctk.CTkLabel(parent, text="目前指令：\n(空)", bg_color="transparent", fg_color=("white", "black"), corner_radius=10, height=80, justify="left", anchor="nw", padx=15, pady=10, font=("Consolas", 14))
        self.script_display.pack(pady=5, fill="x", padx=10) 
        
        act_btn_frame = ctk.CTkFrame(parent, fg_color="transparent"); act_btn_frame.pack(pady=2)
        ctk.CTkButton(act_btn_frame, text="⏪ 刪除上一個指令", command=self.undo_last_script, fg_color="#E0721E", hover_color="#B35D1B", font=("Arial", 13, "bold"), height=30).pack(side=tk.LEFT, padx=15)
        ctk.CTkButton(act_btn_frame, text="🗑️ 清除 Wave 全部", command=self.clear_current_script, fg_color="#C13828", hover_color="#8B2519", font=("Arial", 13, "bold"), height=30).pack(side=tk.LEFT, padx=15)

        cmd_frame = ctk.CTkFrame(parent, fg_color=("gray95", "gray20"))
        cmd_frame.pack(pady=10, padx=10, fill="x")
        ctk.CTkLabel(cmd_frame, text="➕ 新增指令", font=("Arial", 15, "bold")).pack(anchor="w", padx=15, pady=(8, 2))

        self.cmd_category = tk.StringVar(value="從者技能")
        self.cmd_action = tk.StringVar(value="技1")
        self.cmd_target = tk.StringVar(value="無")
        self.cmd_modifier = tk.StringVar(value="無") 

        self.action_options = {
            "從者技能": [f"技{i}" for i in range(1, 10)],
            "寶具": [f"從者{i} 寶具" for i in range(1, 4)],
            "御主/換人": ["御主技1", "御主技2", "御主技3", "換人"],
            "切換敵人": ["敵方1", "敵方2", "敵方3"]
        }

        cat_f = ctk.CTkFrame(cmd_frame, fg_color="transparent"); cat_f.pack(pady=5)
        ctk.CTkLabel(cat_f, text="類:", font=("Arial", 14)).pack(side=tk.LEFT, padx=(5, 2))
        self.create_dropdown(cat_f, self.cmd_category, list(self.action_options.keys()), 110).pack(side=tk.LEFT, padx=2)
        ctk.CTkLabel(cat_f, text="動:", font=("Arial", 14)).pack(side=tk.LEFT, padx=(8, 2))
        self.combo_action = self.create_dropdown(cat_f, self.cmd_action, ["技1"], 100)
        self.combo_action.pack(side=tk.LEFT, padx=2)

        self.frame_target = ctk.CTkFrame(cat_f, fg_color="transparent")
        ctk.CTkLabel(self.frame_target, text="對:", font=("Arial", 14)).pack(side=tk.LEFT, padx=(8, 2))
        self.combo_target = self.create_dropdown(self.frame_target, self.cmd_target, ["無"], 95)
        self.combo_target.pack(side=tk.LEFT, padx=2)
        
        self.frame_modifier = ctk.CTkFrame(cat_f, fg_color="transparent")
        ctk.CTkLabel(self.frame_modifier, text="加:", font=("Arial", 14)).pack(side=tk.LEFT, padx=(8, 2))
        self.combo_modifier = self.create_dropdown(self.frame_modifier, self.cmd_modifier, ["無", "庫庫爾坎耗星", "庫庫爾坎不耗星"], 160)
        self.combo_modifier.pack(side=tk.LEFT, padx=(2, 5))

        def update_actions_ctk(*args):
            cat = self.cmd_category.get()
            opts = self.action_options.get(cat, [])
            self.combo_action.configure(values=opts) 
            if opts and self.cmd_action.get() not in opts: self.cmd_action.set(opts[0])
            update_targets_ctk()

        def update_targets_ctk(*args):
            cat = self.cmd_category.get()
            act = self.cmd_action.get()
            
            if cat == "切換敵人": self.frame_target.pack_forget(); self.frame_modifier.pack_forget() 
            elif cat == "寶具" or cat == "御主/換人": self.frame_target.pack(side=tk.LEFT); self.frame_modifier.pack_forget() 
            else: self.frame_target.pack(side=tk.LEFT); self.frame_modifier.pack(side=tk.LEFT) 

            if cat == "寶具" or cat == "切換敵人": 
                self.combo_target.configure(values=["無"]); self.cmd_target.set("無")
            elif cat == "御主/換人" and act == "換人":
                opts = [f"前{f} 換 後{b}" for f in range(1, 4) for b in range(1, 4)]
                self.combo_target.configure(values=opts)
                if self.cmd_target.get() not in opts: self.cmd_target.set(opts[0])
            else:
                opts = ["無", "對象1", "對象2", "對象3"]
                self.combo_target.configure(values=opts)
                if self.cmd_target.get() not in opts: self.cmd_target.set("無")

        self.cmd_category.trace_add("write", update_actions_ctk)
        self.cmd_action.trace_add("write", update_targets_ctk)
        update_actions_ctk()

        ctk.CTkButton(cmd_frame, text="➕ 寫入指令", command=self.process_add_command, fg_color="#007bff", hover_color="#0056b3", font=("Arial", 14, "bold"), height=35).pack(pady=(10, 15))

    def setup_tab_sys(self, parent):
        switch_frame = ctk.CTkFrame(parent, fg_color="transparent")
        switch_frame.pack(pady=5, fill="x", padx=10)
        
        ctk.CTkCheckBox(switch_frame, text="幕間劇情模式 (註：主線複雜選項尚未完全支援)", variable=self.interlude_mode, font=("Arial", 14)).pack(pady=10, anchor="w")
        ctk.CTkCheckBox(switch_frame, text="自動編隊 (每次出擊強制點「自動編成」刷絆用)", variable=self.auto_formation, font=("Arial", 14)).pack(pady=10, anchor="w")
        ctk.CTkCheckBox(switch_frame, text="智能對齊 Wave (讀取右上角 1/3, 2/3)", variable=self.smart_turn_mode, font=("Arial", 14)).pack(pady=10, anchor="w")

        mode_f = ctk.CTkFrame(switch_frame, fg_color="transparent"); mode_f.pack(pady=5, anchor="w")
        ctk.CTkLabel(mode_f, text="技能施放模式:", font=("Arial", 14)).pack(side=tk.LEFT)
        self.create_dropdown(mode_f, self.skill_mode, ["智慧安全", "標準無腦", "極限盲操"], 110).pack(side=tk.LEFT, padx=10)
        
        self.lbl_extreme_sleep = ctk.CTkLabel(mode_f, text="盲等(秒):", font=("Arial", 14))
        self.lbl_extreme_sleep.pack(side=tk.LEFT)
        self.entry_extreme_sleep = ctk.CTkSlider(
            mode_f, from_=0.5, to=6.0, number_of_steps=55,
            command=lambda v: self.extreme_sleep.set(f"{v:.1f}"), width=200
        )
        self.entry_extreme_sleep.set(float(self.extreme_sleep.get() or 2.5))
        self.entry_extreme_sleep.pack(side=tk.LEFT, padx=5)
        ctk.CTkLabel(mode_f, textvariable=self.extreme_sleep, width=35, font=("Arial", 14, "bold")).pack(side=tk.LEFT)
        self.toggle_extreme_sleep_ui()

        ctk.CTkLabel(parent, text="--- ADB 畫面抓取與存檔 ---", text_color="gray", font=("Arial", 14)).pack(pady=(15, 5))
        
        btn_ss_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_ss_frame.pack(pady=5)
        
        self.btn_screenshot = ctk.CTkButton(btn_ss_frame, text="📸 立即擷取模擬器畫面", height=35, command=self.test_screenshot)
        self.btn_screenshot.pack(side=tk.LEFT, padx=5)
        
        self.btn_save_screenshot = ctk.CTkButton(btn_ss_frame, text="💾 儲存高畫質截圖", height=35, fg_color="#17a2b8", hover_color="#138496", state="disabled", command=self.save_screenshot)
        self.btn_save_screenshot.pack(side=tk.LEFT, padx=5)
        
        self.lbl_image_preview = ctk.CTkLabel(parent, text="(截圖將顯示於此，可儲存後裁切作為助戰圖片)", width=426, height=240, fg_color="#1a1a1a", corner_radius=10)
        self.lbl_image_preview.pack(pady=10)

    # ==============================
    # ⚙️ 核心邏輯 (加入 Error 防護)
    # ==============================
    def select_img(self, img_type, idx):
        try:
            sub_folder = "servants" if img_type == 'servant' else "craft_essences"
            d = os.path.join(get_base_dir(), "assets_friends", sub_folder)
            os.makedirs(d, exist_ok=True)
            p = filedialog.askopenfilename(initialdir=d, filetypes=(("PNG files", "*.png"), ("all files", "*.*")))
            if p: 
                if img_type == 'servant':
                    self.target_servant_paths[idx] = p
                    self.selected_servants[idx].set(os.path.basename(p))
                else:
                    self.target_ce_paths[idx] = p
                    self.selected_ces[idx].set(os.path.basename(p))
        except Exception as e:
            messagebox.showerror("選擇圖片發生錯誤", traceback.format_exc())

    def remove_img(self, img_type, idx):
        if img_type == 'servant':
            self.target_servant_paths[idx] = None
            self.selected_servants[idx].set("尚未選取")
        else:
            self.target_ce_paths[idx] = None
            self.selected_ces[idx].set("尚未選取")

    def process_add_command(self):
        cat = self.cmd_category.get(); act = self.cmd_action.get(); tgt = self.cmd_target.get()
        mod = self.cmd_modifier.get()
        cmd_str = ""
        
        if cat == "從者技能":
            idx = int(act.replace("技", ""))
            mod_str = "_star" if mod == "庫庫爾坎耗星" else "_nostar" if mod == "庫庫爾坎不耗星" else ""
            cmd_str = f"S{idx}{mod_str}" if tgt in ["無", ""] else f"S{idx}{mod_str}-{tgt.replace('對象', '')}"
        elif cat == "寶具":
            cmd_str = f"N{int(act.replace('從者', '').replace(' 寶具', ''))}"
        elif cat == "切換敵人":
            cmd_str = f"E{int(act.replace('敵方', ''))}"
        elif cat == "御主/換人":
            if act == "換人":
                parts = tgt.split(" ")
                cmd_str = f"O-{parts[0].replace('前', '')}-{parts[2].replace('後', '')}"
            else:
                idx = int(act.replace("御主技", ""))
                cmd_str = f"M{idx}" if tgt in ["無", ""] else f"M{idx}-{tgt.replace('對象', '')}"
                
        if cmd_str:
            self.script_data[self.edit_wave_idx.get()].append(cmd_str)
            self.update_script_display()

    def clear_current_script(self):
        self.script_data[self.edit_wave_idx.get()] = []; self.update_script_display()

    def undo_last_script(self):
        wave_idx = self.edit_wave_idx.get()
        if self.script_data[wave_idx]: 
            self.script_data[wave_idx].pop() 
            self.update_script_display() 

    def update_script_display(self):
        cmds = self.script_data[self.edit_wave_idx.get()]
        readable = [c.replace('S','技').replace('M','御主').replace('O-','換人').replace('N','寶具').replace('E','敵方').replace('_star', '(耗星)').replace('_nostar', '(不耗星)') for c in cmds]
        text = " → ".join(readable) if cmds else "(空)"
        self.script_display.configure(text=f"目前指令：\n{text}")

    def save_profile(self):
        try:
            d = os.path.join(get_base_dir(), "assets_saves")
            os.makedirs(d, exist_ok=True)
            fp = filedialog.asksaveasfilename(initialdir=d, defaultextension=".json", filetypes=[("FGO 腳本檔", "*.json")])
            if not fp: return
            data = {
                'battle_mode': self.battle_mode.get(), 'smart_turn_mode': self.smart_turn_mode.get(),
                'skill_mode': self.skill_mode.get(), 'extreme_sleep': self.extreme_sleep.get(), 
                'apple_mode': self.apple_mode.get(), 'loop_target': self.loop_target.get(),
                'support_class': self.support_class.get(), 'target_servant_paths': self.target_servant_paths, 
                'target_ce_paths': self.target_ce_paths, 'team_index': int(self.team_index.get()),
                'script_data': self.script_data, 'auto_formation': self.auto_formation.get(),
                'interlude_mode': self.interlude_mode.get(), 'ai_card_mode': self.ai_card_mode.get(),
                'card_priority': self.card_priority.get(), 'auto_np_mode': self.auto_np_mode.get()
            }
            with open(fp, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)
            messagebox.showinfo("成功", "設定已成功儲存！")
            self.update_status_label(f"狀態：已儲存設定 ({os.path.basename(fp)})", "#28a745")
        except Exception as e: 
            messagebox.showerror("存檔失敗", traceback.format_exc())

    def load_profile(self):
        try:
            d = os.path.join(get_base_dir(), "assets_saves")
            os.makedirs(d, exist_ok=True)
            fp = filedialog.askopenfilename(initialdir=d, filetypes=[("FGO 腳本檔", "*.json")])
            if not fp: return
            
            with open(fp, 'r', encoding='utf-8') as f: data = json.load(f)
            self.battle_mode.set(data.get('battle_mode', 'script'))
            self.smart_turn_mode.set(data.get('smart_turn_mode', False))
            self.skill_mode.set(data.get('skill_mode', "智慧安全"))
            self.extreme_sleep.set(str(data.get('extreme_sleep', '2.5')))
            self.apple_mode.set(data.get('apple_mode', '不自動回體'))
            self.loop_target.set(str(data.get('loop_target', '0')))
            self.support_class.set(data.get('support_class', 'ALL'))
            
            paths_s = data.get('target_servant_paths', [None, None, None])
            for i in range(3):
                self.target_servant_paths[i] = paths_s[i] if i < len(paths_s) else None
                self.selected_servants[i].set(os.path.basename(paths_s[i]) if i < len(paths_s) and paths_s[i] else "尚未選取")

            paths_c = data.get('target_ce_paths', [None, None, None])
            for i in range(3):
                self.target_ce_paths[i] = paths_c[i] if i < len(paths_c) else None
                self.selected_ces[i].set(os.path.basename(paths_c[i]) if i < len(paths_c) and paths_c[i] else "尚未選取")

            self.team_index.set(str(data.get('team_index', 1))) 
            self.auto_formation.set(data.get('auto_formation', False))
            self.interlude_mode.set(data.get('interlude_mode', False))
            self.ai_card_mode.set(data.get('ai_card_mode', False))
            self.card_priority.set(data.get('card_priority', "無"))
            self.auto_np_mode.set(data.get('auto_np_mode', True))
            self.script_data = data.get('script_data', [[], [], []])
            self.update_script_display() 
            self.update_status_label(f"狀態：已載入設定 ({os.path.basename(fp)})", "#28a745")
        except Exception as e: 
            messagebox.showerror("讀檔失敗", traceback.format_exc())

    def update_status_label(self, text, color="#00CFFF"):
        self.root.after(0, lambda: self.label_status.configure(text=text, text_color=color))

    def update_dynamic_status(self):
        if self.running:
            base_text = self.label_status.cget("text").rstrip(".") 
            dots = "." * ((self.dot_count % 4))
            self.label_status.configure(text=f"{base_text}{dots}")
            self.dot_count += 1
        self.root.after(800, self.update_dynamic_status)

    def start_thread(self):
        if not self.running: 
            # 🚀 加入啟動防護與報錯機制
            try:
                self.running = True
                self.btn_start.configure(state="disabled")
                self.btn_stop.configure(state="normal")
                
                try: loop_val = int(self.loop_target.get() or 0)
                except: loop_val = 0
                try: extreme_val = float(self.extreme_sleep.get() or 2.5)
                except: extreme_val = 2.5
                
                config = {
                    'device_id': self.entry_adb.get(), 'smart_turn_mode': self.smart_turn_mode.get(),
                    'skill_mode': self.skill_mode.get(), 'extreme_sleep': extreme_val, 
                    'apple_mode': self.apple_mode.get(), 'loop_target': loop_val, 
                    'support_class': self.support_class.get(), 'team_index': int(self.team_index.get()),
                    'battle_mode': self.battle_mode.get(), 'script_data': self.script_data,
                    'target_servant_paths': self.target_servant_paths, 'target_ce_paths': self.target_ce_paths,
                    'ai_card_mode': self.ai_card_mode.get(), 'card_priority': self.card_priority.get(),
                    'auto_np_mode': self.auto_np_mode.get(), 'auto_formation': self.auto_formation.get(),
                    'interlude_mode': self.interlude_mode.get()
                }
                
                self.logic_thread = FGOLogic(config, self.update_status_label, self.stop_script)
                self.logic_thread.bot.init_device()
                
                # 獨立執行緒執行大腦，若出錯也能被抓到
                def thread_worker():
                    try:
                        self.logic_thread.run_logic()
                    except Exception as e:
                        err_msg = traceback.format_exc()
                        print(err_msg)
                        self.update_status_label("狀態：腳本發生致命錯誤崩潰！", "#dc3545")
                        # 避免在子執行緒中直接彈窗導致卡死，透過 after 呼叫
                        self.root.after(0, lambda: messagebox.showerror("腳本崩潰", f"發生未預期錯誤:\n{err_msg}"))
                        self.stop_script()

                threading.Thread(target=thread_worker, daemon=True).start()
                
            except Exception as e:
                self.running = False
                self.btn_start.configure(state="normal")
                self.btn_stop.configure(state="disabled")
                messagebox.showerror("啟動失敗", traceback.format_exc())
            
    def stop_script(self): 
        self.running = False
        if self.logic_thread: self.logic_thread.running = False 
        self.root.after(0, self._stop_script_ui)

    def _stop_script_ui(self):
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        if "任務達成" not in self.label_status.cget("text"):
            self.label_status.configure(text="狀態：已停止", text_color="#dc3545")

    def detect_adb(self):
        try:
            self.update_status_label("狀態：正在偵測設備...", "white"); self.root.update()
            result = subprocess.run("adb devices", capture_output=True, text=True, shell=True)
            lines = result.stdout.strip().split('\n')[1:]
            devices = [line.split('\t')[0] for line in lines if 'device' in line]
            if not devices:
                self.update_status_label("狀態：重置 ADB 伺服器中...", "orange"); self.root.update()
                subprocess.run("adb kill-server", shell=True, capture_output=True)
                subprocess.run("adb start-server", shell=True, capture_output=True)
                result = subprocess.run("adb devices", capture_output=True, text=True, shell=True)
                lines = result.stdout.strip().split('\n')[1:]
                devices = [line.split('\t')[0] for line in lines if 'device' in line]
            if devices: 
                self.entry_adb.delete(0, tk.END); self.entry_adb.insert(0, devices[0])
                self.led_indicator.configure(text_color="#28a745") 
                self.update_status_label(f"狀態：ADB 連線成功 ({devices[0]})", "#28a745")
                messagebox.showinfo("成功", f"已連線: {devices[0]}")
            else:
                self.led_indicator.configure(text_color="#dc3545")
                self.update_status_label("狀態：找不到設備，請確認模擬器設定", "#dc3545")
                messagebox.showwarning("找不到設備", "請確認模擬器已開啟，且「ADB 偵錯」已啟用。")
        except Exception as e: 
            self.led_indicator.configure(text_color="#dc3545")
            messagebox.showerror("ADB 執行錯誤", traceback.format_exc())

    def test_connection(self):
        self.test_screenshot()

    def test_screenshot(self):
        try:
            self.update_status_label("狀態：正在擷取畫面...", "white")
            self.root.update()
            bot = FGOBot(self.entry_adb.get())
            if bot.capture_screen():
                rgb = cv2.cvtColor(bot.current_screen, cv2.COLOR_BGR2RGB)
                self.last_raw_image = Image.fromarray(rgb) 
                
                pil_img = self.last_raw_image.resize((426, 240), Image.LANCZOS)
                self.ctk_preview_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(426, 240))
                self.lbl_image_preview.configure(image=self.ctk_preview_image, text="")
                
                self.btn_save_screenshot.configure(state="normal") 
                self.update_status_label("狀態：截圖成功，請至「系統與進階」查看並存檔", "#28a745")
            else:
                self.update_status_label("狀態：擷取失敗", "#dc3545")
                messagebox.showwarning("錯誤", "無法擷取畫面，請確認模擬器是否開啟。")
        except Exception as e:
            self.update_status_label("狀態：發生異常", "#dc3545")
            messagebox.showerror("截圖發生錯誤", traceback.format_exc())

    def save_screenshot(self):
        if self.last_raw_image is None: return
        try:
            initial_dir = get_base_dir()
            fp = filedialog.asksaveasfilename(
                initialdir=initial_dir,
                initialfile="fgo_screenshot.png",
                defaultextension=".png", 
                filetypes=[("PNG 圖片", "*.png"), ("JPEG 圖片", "*.jpg")]
            )
            if fp:
                self.last_raw_image.save(fp)
                messagebox.showinfo("成功", f"高畫質截圖已成功儲存至:\n{fp}\n您可以開啟此圖片進行裁切了！")
                self.update_status_label("狀態：截圖已儲存！", "#28a745")
        except Exception as e:
            messagebox.showerror("圖片儲存失敗", traceback.format_exc())

# 🚀 啟動前讀取 config，也必須使用絕對路徑
def load_initial_config():
    config_path = os.path.join(get_base_dir(), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                pass # 這裡只是測試讀取
        except: pass

if __name__ == "__main__":
    load_initial_config()
    root = ctk.CTk()
    app = FGOApp(root)
    root.mainloop()