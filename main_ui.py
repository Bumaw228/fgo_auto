import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading
import os
import sys  
import cv2
import subprocess 
import json
import re
from fgo_core import FGOBot, detect_devices, list_devices, kill_adb_server
from fgo_logic import FGOLogic 
from PIL import Image, ImageTk
import ctypes
import webbrowser
import traceback # 🚀 新增：用來捕捉詳細錯誤訊息
from updater import (check_for_update_async, download_and_apply_async,
                     CURRENT_VERSION, REPO_URL, RELEASES_URL)
import fgo_logger
import script_check

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
# 💾 程式層級設定 (記住上次使用的設定檔)
# ==============================
CONFIG_PATH = os.path.join(get_base_dir(), "config.json")

def read_app_config():
    """讀取 config.json，失敗一律回傳空 dict，不影響程式啟動"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def write_app_config(data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"⚠️ 寫入 config.json 失敗: {e}")

# ==============================
# 🌟 設置 CustomTkinter 主題與效能
# ==============================
# 統一的間距：區塊之間用 PAD_BLOCK，區塊內部用 PAD_ITEM。
# 原本散落 2/5/10/15 沒有規律，是版面看起來不整齊的主因。
PAD_BLOCK = 10
PAD_ITEM = 4

# 截圖預覽尺寸（16:9）。改這裡會同時影響版面與縮圖，兩者不會不同步。
PREVIEW_SIZE = (320, 180)

# 腳本檢查的嚴重度配色。色條與文字都用同一組，比淡底色好辨識。
LEVEL_COLOR = {
    "error": "#E5534B",
    "warn": "#D9A441",
    "info": "#4F94CD",
}

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

ctk.deactivate_automatic_dpi_awareness()
ctk.set_window_scaling(1.0)
ctk.set_widget_scaling(1.0)



class FGOApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"FGO 好玩遊戲輔助工具 v{CURRENT_VERSION}")
        self.root.geometry("820x660")
        self.root.minsize(780, 620)
        
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
        # 🚀 每次啟動遞增，用來辨識「這是第幾輪」，避免舊執行緒的收尾關掉新一輪的 UI
        self.session_id = 0 
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
        self.order_change_slot = tk.StringVar(value="3")
        
        self.skill_mode.trace_add("write", self.toggle_extreme_sleep_ui)
        
        self.ai_card_mode = tk.BooleanVar(value=False)
        self.card_priority = tk.StringVar(value="無")
        self.auto_np_mode = tk.BooleanVar(value=True) 
        self.auto_formation = tk.BooleanVar(value=False)
        self.interlude_mode = tk.BooleanVar(value=False)
        self.smart_turn_mode = tk.BooleanVar(value=False)
        self.use_roi = tk.BooleanVar(value=True)
        self.use_raw_capture = tk.BooleanVar(value=True)
        self.use_tap = tk.BooleanVar(value=True)
        self.kill_adb_on_exit = tk.BooleanVar(value=False)

        self.script_data = [[], [], []]
        self._script_rows = []      # 指令清單的列元件，重複使用以避免閃爍
        self._empty_hint = None
        self._wave_issues = {}      # 當前 Wave 的檢查結果，index -> issue 
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

        # 🚀 自動載入上次使用的設定檔
        self.auto_load_last_profile()
        # 🚀 開程式就先確認 ADB 連線狀態，不用等使用者按「自動偵測」
        self.root.after(300, self.check_connection_async)
        # 🚀 延遲 1.5 秒再檢查更新，讓視窗先畫完再說
        self.root.after(1500, self.check_update)

    def toggle_extreme_sleep_ui(self, *args):
        if hasattr(self, 'entry_extreme_sleep') and self.entry_extreme_sleep:
            if self.skill_mode.get() == "極限盲操":
                self.entry_extreme_sleep.configure(state="normal")
            else:
                self.entry_extreme_sleep.configure(state="disabled")

    def setup_ui(self):
        # 頂部：ADB 連線
        top_frame = ctk.CTkFrame(self.root)
        top_frame.pack(fill="x", padx=15, pady=(10, 6))
        
        ctk.CTkLabel(top_frame, text="ADB 連線:", font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=10)
        self.entry_adb = ctk.CTkEntry(top_frame, width=160, font=("Arial", 14))
        self.entry_adb.insert(0, "127.0.0.1:5555")
        self.entry_adb.pack(side=tk.LEFT, padx=5)
        
        ctk.CTkButton(top_frame, text="自動偵測", command=self.detect_adb, width=80).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(top_frame, text="截圖測試", command=self.test_connection, width=80, fg_color="#6c757d", hover_color="#5a6268").pack(side=tk.LEFT, padx=5)
        
        self.led_indicator = ctk.CTkLabel(top_frame, text="●", text_color="gray", font=("Arial", 28))
        self.led_indicator.pack(side=tk.LEFT, padx=(10, 2))
        # 只靠顏色不夠清楚，補一段文字說明目前連線狀態
        self.lbl_conn = ctk.CTkLabel(top_frame, text="尚未檢查", text_color="gray", font=("Arial", 13))
        self.lbl_conn.pack(side=tk.LEFT)

        # 中央：四大分頁
        self.tabview = ctk.CTkTabview(self.root)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(0, 4))
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
        bottom_frame.pack(side=tk.BOTTOM, fill="x", padx=15, pady=(6, 8))

        self.label_status = ctk.CTkLabel(bottom_frame, text="狀態：待機中", text_color="#00CFFF", font=("Arial", 16, "bold"))
        self.label_status.pack(pady=(8, 4))

        ctrl_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        ctrl_frame.pack(pady=(0, 10))

        self.btn_start = ctk.CTkButton(ctrl_frame, text="🚀 開始", command=self.start_thread, fg_color="#28a745", hover_color="#218838", font=("Arial", 16, "bold"), width=120, height=38)
        self.btn_start.pack(side=tk.LEFT, padx=10)

        self.btn_stop = ctk.CTkButton(ctrl_frame, text="🛑 停止", command=self.stop_script, fg_color="#dc3545", hover_color="#c82333", font=("Arial", 16, "bold"), width=100, height=38, state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=10)

        self.btn_save = ctk.CTkButton(ctrl_frame, text="💾 存檔", command=self.save_profile, fg_color="#17a2b8", hover_color="#138496", font=("Arial", 16, "bold"), width=100, height=38)
        self.btn_save.pack(side=tk.LEFT, padx=10)

        self.btn_load = ctk.CTkButton(ctrl_frame, text="📂 讀檔", command=self.load_profile, fg_color="#ffc107", hover_color="#e0a800", text_color="black", font=("Arial", 16, "bold"), width=100, height=38)
        self.btn_load.pack(side=tk.LEFT, padx=10)

    # ==============================
    # 分頁設計
    # ==============================
    def setup_tab_basic(self, parent):
        f1 = ctk.CTkFrame(parent, fg_color="transparent"); f1.pack(fill="x", pady=PAD_BLOCK)
        ctk.CTkLabel(f1, text="出擊隊伍編號:", font=("Arial", 14)).pack(side=tk.LEFT, padx=15)
        self.create_dropdown(f1, self.team_index, [str(i) for i in range(1, 16)], 80).pack(side=tk.LEFT)
        
        ctk.CTkLabel(f1, text="蘋果補充:", font=("Arial", 14)).pack(side=tk.LEFT, padx=(30, 10))
        self.create_dropdown(f1, self.apple_mode, ["不自動回體", "銅蘋果", "青銅蘋果", "銀蘋果", "金蘋果"], 120).pack(side=tk.LEFT)

        f2 = ctk.CTkFrame(parent, fg_color="transparent"); f2.pack(fill="x", pady=PAD_BLOCK)
        ctk.CTkLabel(f2, text="目標周回次數:", font=("Arial", 14)).pack(side=tk.LEFT, padx=15)
        ctk.CTkEntry(f2, textvariable=self.loop_target, width=80, font=("Arial", 14)).pack(side=tk.LEFT)
        ctk.CTkLabel(f2, text="(0 = 無限刷到沒體/蘋果)", text_color="gray", font=("Arial", 12)).pack(side=tk.LEFT, padx=10)

        ctk.CTkLabel(parent, text="--- 戰鬥行為 ---", text_color="gray", font=("Arial", 14, "bold")).pack(pady=(12, 6))
        
        f3 = ctk.CTkFrame(parent, fg_color="transparent"); f3.pack(fill="x", pady=5)
        ctk.CTkRadioButton(f3, text="隨機選卡 (耍廢平A流)", variable=self.battle_mode, value="random", font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=15)
        ctk.CTkRadioButton(f3, text="精準 3T (請至分頁設定)", variable=self.battle_mode, value="script", font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=15)

        f4 = ctk.CTkFrame(parent, fg_color="transparent"); f4.pack(fill="x", pady=PAD_BLOCK, padx=15)
        ctk.CTkCheckBox(f4, text="每回合自動放寶具", variable=self.auto_np_mode, font=("Arial", 14)).pack(side=tk.LEFT)
        ctk.CTkCheckBox(f4, text="啟用 AI 視覺算牌", variable=self.ai_card_mode, font=("Arial", 14)).pack(side=tk.LEFT, padx=20)
        
        f5 = ctk.CTkFrame(parent, fg_color="transparent"); f5.pack(fill="x", pady=5)
        ctk.CTkLabel(f5, text="AI 優先順序:", font=("Arial", 14)).pack(side=tk.LEFT, padx=15)
        self.create_dropdown(f5, self.card_priority, ["無", "紅 > 藍 > 綠", "藍 > 綠 > 紅", "綠 > 藍 > 紅", "紅 > 綠 > 藍"], 130).pack(side=tk.LEFT)

    def setup_tab_support(self, parent):
        class_frame = ctk.CTkFrame(parent, fg_color="transparent") 
        class_frame.pack(pady=PAD_BLOCK, fill="x", padx=5)
        ctk.CTkLabel(class_frame, text="尋找職階：", font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=10)
        self.create_dropdown(class_frame, self.support_class, ["ALL", "Saber", "Archer", "Lancer", "Rider", "Caster", "Assassin", "Berserker", "Extra", "Mix"], 120).pack(side=tk.LEFT)

        img_frame = ctk.CTkFrame(parent, fg_color=("gray95", "gray20"))
        img_frame.pack(pady=5, fill="both", expand=True, padx=5)
        ctk.CTkLabel(img_frame, text="目標圖片 (符合任一即選取，全空則盲選)", font=("Arial", 15, "bold")).pack(anchor="w", padx=15, pady=(8, 4))
        
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

        # 指令清單：每一列都能單獨上移、下移、刪除
        self.script_list = ctk.CTkScrollableFrame(parent, fg_color=("white", "gray10"),
                                                  corner_radius=10, height=170)
        self.script_list.pack(pady=5, fill="both", expand=True, padx=10)

        # 檢查結果：上排是摘要與「詳細」按鈕，下排顯示選取那一列的說明
        chk_f = ctk.CTkFrame(parent, fg_color="transparent")
        chk_f.pack(fill="x", padx=14, pady=(2, 0))
        self.lbl_script_check = ctk.CTkLabel(chk_f, text="", font=("Arial", 13), anchor="w")
        self.lbl_script_check.pack(side=tk.LEFT)
        self.btn_check_detail = ctk.CTkButton(chk_f, text="查看全部", width=76, height=24,
                                              font=("Arial", 12), fg_color="#4A4A4A",
                                              hover_color="#5C5C5C", command=self.show_check_report)
        self.btn_check_detail.pack(side=tk.RIGHT)

        self.lbl_issue_detail = ctk.CTkLabel(parent, text="", font=("Arial", 12),
                                             anchor="w", justify="left", wraplength=740,
                                             text_color="gray")
        self.lbl_issue_detail.pack(fill="x", padx=14, pady=(0, 2))

        act_btn_frame = ctk.CTkFrame(parent, fg_color="transparent"); act_btn_frame.pack(pady=2)
        ctk.CTkButton(act_btn_frame, text="🗑️ 清除本 Wave", command=self.clear_current_script,
                      fg_color="#C13828", hover_color="#8B2519",
                      font=("Arial", 13, "bold"), height=30, width=130).pack(side=tk.LEFT, padx=15)

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
        """系統與進階：左右兩欄配置。

        原本所有元件擠成一長條，把視窗高度撐到 850px。
        改成左欄放設定、右欄放截圖工具之後，這一頁的高度需求幾乎減半。
        """
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=6, pady=PAD_BLOCK)
        wrap.grid_columnconfigure(0, weight=3)
        wrap.grid_columnconfigure(1, weight=2)
        wrap.grid_rowconfigure(0, weight=1)

        # ── 左欄：功能開關與模式 ──────────────────────
        left = ctk.CTkFrame(wrap, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ctk.CTkCheckBox(left, text="幕間劇情模式 (主線複雜選項尚未完全支援)",
                        variable=self.interlude_mode, font=("Arial", 14)).pack(pady=PAD_ITEM, anchor="w")
        ctk.CTkCheckBox(left, text="自動編隊 (每次出擊強制點「自動編成」刷絆用)",
                        variable=self.auto_formation, font=("Arial", 14)).pack(pady=PAD_ITEM, anchor="w")
        ctk.CTkCheckBox(left, text="智能對齊 Wave (讀取右上角 1/3, 2/3)",
                        variable=self.smart_turn_mode, font=("Arial", 14)).pack(pady=PAD_ITEM, anchor="w")

        accel_f = ctk.CTkFrame(left, fg_color=("gray95", "gray20"), corner_radius=8)
        accel_f.pack(pady=(PAD_BLOCK, PAD_ITEM), fill="x")
        ctk.CTkLabel(accel_f, text="⚡ 加速選項", font=("Arial", 14, "bold")).pack(anchor="w", padx=12, pady=(6, 2))
        ctk.CTkCheckBox(accel_f, text="ROI 加速 (限定影像搜尋範圍)", variable=self.use_roi,
                        font=("Arial", 14)).pack(pady=PAD_ITEM, padx=12, anchor="w")
        ctk.CTkCheckBox(accel_f, text="高速截圖 (截圖速度約快一倍)", variable=self.use_raw_capture,
                        font=("Arial", 14)).pack(pady=PAD_ITEM, padx=12, anchor="w")
        ctk.CTkCheckBox(accel_f, text="快速點擊 (每次點擊約快 70ms)", variable=self.use_tap,
                        font=("Arial", 14)).pack(pady=PAD_ITEM, padx=12, anchor="w")
        ctk.CTkLabel(accel_f, text="皆會自動偵測異常並退回安全模式，遇到問題可取消勾選",
                     text_color="gray", font=("Arial", 11)).pack(anchor="w", padx=12, pady=(0, 8))

        ctk.CTkCheckBox(left, text="關閉程式時一併結束 ADB 服務",
                        variable=self.kill_adb_on_exit, font=("Arial", 14)).pack(pady=PAD_ITEM, anchor="w")
        ctk.CTkLabel(left, text="可避免 adb.exe 殘留與更新時檔案被鎖，但會中斷其他使用 ADB 的程式",
                     text_color="gray", font=("Arial", 11), wraplength=380,
                     justify="left").pack(anchor="w", pady=(0, PAD_ITEM))

        mode_f = ctk.CTkFrame(left, fg_color="transparent"); mode_f.pack(pady=PAD_ITEM, anchor="w", fill="x")
        ctk.CTkLabel(mode_f, text="技能施放模式:", font=("Arial", 14)).pack(side=tk.LEFT)
        self.create_dropdown(mode_f, self.skill_mode, ["智慧安全", "標準無腦", "極限盲操"], 110).pack(side=tk.LEFT, padx=8)

        sleep_f = ctk.CTkFrame(left, fg_color="transparent"); sleep_f.pack(pady=PAD_ITEM, anchor="w", fill="x")
        self.lbl_extreme_sleep = ctk.CTkLabel(sleep_f, text="盲等(秒):", font=("Arial", 14))
        self.lbl_extreme_sleep.pack(side=tk.LEFT)
        self.entry_extreme_sleep = ctk.CTkSlider(
            sleep_f, from_=0.5, to=6.0, number_of_steps=55,
            command=lambda v: self.extreme_sleep.set(f"{v:.1f}"), width=170
        )
        self.entry_extreme_sleep.set(float(self.extreme_sleep.get() or 2.5))
        self.entry_extreme_sleep.pack(side=tk.LEFT, padx=6)
        ctk.CTkLabel(sleep_f, textvariable=self.extreme_sleep, width=35,
                     font=("Arial", 14, "bold")).pack(side=tk.LEFT)
        self.toggle_extreme_sleep_ui()

        oc_f = ctk.CTkFrame(left, fg_color="transparent"); oc_f.pack(pady=PAD_ITEM, anchor="w", fill="x")
        ctk.CTkLabel(oc_f, text="換人位於御主技能第:", font=("Arial", 14)).pack(side=tk.LEFT)
        self.create_dropdown(oc_f, self.order_change_slot, ["1", "2", "3"], 60).pack(side=tk.LEFT, padx=6)
        ctk.CTkLabel(oc_f, text="格 (戰鬥服為第 3 格)", text_color="gray",
                     font=("Arial", 12)).pack(side=tk.LEFT)

        # ── 右欄：截圖與紀錄 ──────────────────────────
        right = ctk.CTkFrame(wrap, fg_color=("gray95", "gray20"), corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew")

        ctk.CTkLabel(right, text="🖼️ 畫面擷取", font=("Arial", 14, "bold")).pack(anchor="w", padx=12, pady=(8, 2))

        self.btn_screenshot = ctk.CTkButton(right, text="📸 擷取模擬器畫面", height=34,
                                            font=("Arial", 14), command=self.test_screenshot)
        self.btn_screenshot.pack(pady=PAD_ITEM, padx=12, fill="x")

        self.btn_save_screenshot = ctk.CTkButton(right, text="💾 儲存高畫質截圖", height=34,
                                                 font=("Arial", 14), fg_color="#17a2b8",
                                                 hover_color="#138496", state="disabled",
                                                 command=self.save_screenshot)
        self.btn_save_screenshot.pack(pady=PAD_ITEM, padx=12, fill="x")

        self.lbl_image_preview = ctk.CTkLabel(right, text="(擷取後顯示於此，\n可存檔裁切作為助戰圖片)",
                                              width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1], fg_color="#1a1a1a",
                                              text_color="gray", corner_radius=8)
        self.lbl_image_preview.pack(pady=PAD_BLOCK, padx=12)

        ctk.CTkButton(right, text="📋 開啟紀錄資料夾", height=34, font=("Arial", 14),
                      fg_color="#6c757d", hover_color="#5a6268",
                      command=fgo_logger.open_log_folder).pack(pady=PAD_ITEM, padx=12, fill="x")

        ctk.CTkLabel(right, text="ℹ️ 說明與更新", font=("Arial", 14, "bold")).pack(anchor="w", padx=12, pady=(PAD_BLOCK, 2))

        link_f = ctk.CTkFrame(right, fg_color="transparent")
        link_f.pack(pady=(PAD_ITEM, 12), padx=12, fill="x")
        ctk.CTkButton(link_f, text="🌐 專案頁面", height=34, font=("Arial", 14),
                      fg_color="#4A4A4A", hover_color="#5C5C5C",
                      command=lambda: webbrowser.open(REPO_URL)).pack(side=tk.LEFT, expand=True, fill="x", padx=(0, 3))
        ctk.CTkButton(link_f, text="🔄 檢查更新", height=34, font=("Arial", 14),
                      fg_color="#4A4A4A", hover_color="#5C5C5C",
                      command=self.manual_check_update).pack(side=tk.LEFT, expand=True, fill="x", padx=(3, 0))

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

    @staticmethod
    def format_command(c):
        """把內部指令碼轉成看得懂的文字。

        改用正規表示式逐一解析，取代原本的連續 replace —— 後者只要指令格式
        稍微變動就可能把不該換的字元也換掉。
        """
        m = re.match(r'^S(\d+)(_star|_nostar)?(?:-(\d+))?$', c)
        if m:
            mod = {"_star": " (耗星)", "_nostar": " (不耗星)"}.get(m.group(2), "")
            tgt = f" → 對象{m.group(3)}" if m.group(3) else ""
            return f"技能 {m.group(1)}{mod}{tgt}"

        m = re.match(r'^M(\d+)(?:-(\d+))?$', c)
        if m:
            tgt = f" → 對象{m.group(2)}" if m.group(2) else ""
            return f"御主技 {m.group(1)}{tgt}"

        m = re.match(r'^N(\d+)$', c)
        if m:
            return f"從者 {m.group(1)} 寶具"

        m = re.match(r'^E(\d+)$', c)
        if m:
            return f"切換敵方 {m.group(1)}"

        m = re.match(r'^O-(\d+)-(\d+)$', c)
        if m:
            return f"換人  前{m.group(1)} ⇄ 後{m.group(2)}"

        return c   # 無法解析就原樣顯示，至少看得出有東西

    def _show_issue_detail(self, idx):
        """顯示某一列的檢查說明。idx 為 None 時清空。"""
        if not hasattr(self, "lbl_issue_detail"):
            return
        issue = (self._wave_issues or {}).get(idx) if idx is not None else None
        if issue is None:
            hint = "點選任一列可查看該列的檢查說明" if self._wave_issues else ""
            self.lbl_issue_detail.configure(text=hint, text_color="gray")
        else:
            self.lbl_issue_detail.configure(
                text=f"{script_check.LEVEL_ICON[issue['level']]} 第 {idx + 1} 道：{issue['msg']}",
                text_color=LEVEL_COLOR[issue["level"]])

    def show_check_report(self):
        """列出整份腳本的所有檢查結果"""
        issues = script_check.check_script(self.script_data)
        if not issues:
            messagebox.showinfo("腳本檢查", "✅ 檢查通過，未發現問題。")
            return
        messagebox.showinfo(
            "腳本檢查結果",
            f"{script_check.summarize(issues)}\n\n{script_check.format_report(issues)}\n\n"
            f"🔴 錯誤會導致指令失效　🟡 建議確認　🔵 僅供參考，多為需要搭配特定隊伍才成立")

    def _update_check_summary(self, issues):
        """更新清單下方的檢查摘要。整份腳本一起看，不只當前 Wave。"""
        if not hasattr(self, "lbl_script_check"):
            return
        colour = "#28a745"
        if script_check.has_error(issues):
            colour = "#dc3545"
        elif any(x["level"] == script_check.WARN for x in issues):
            colour = "#ffc107"
        elif issues:
            colour = "#4F94CD"
        self.lbl_script_check.configure(text=script_check.summarize(issues), text_color=colour)

    def move_command(self, idx, delta):
        """把第 idx 個指令往上或往下移動一格"""
        cmds = self.script_data[self.edit_wave_idx.get()]
        new_idx = idx + delta
        if 0 <= new_idx < len(cmds):
            cmds[idx], cmds[new_idx] = cmds[new_idx], cmds[idx]
            self.update_script_display()

    def delete_command(self, idx):
        cmds = self.script_data[self.edit_wave_idx.get()]
        if 0 <= idx < len(cmds):
            cmds.pop(idx)
            self.update_script_display()

    def _build_script_row(self, i):
        """建立第 i 列的元件。列的位置固定不變，所以按鈕的索引可以在建立時就綁定。"""
        row = ctk.CTkFrame(self.script_list, fg_color=("gray92", "gray20"), corner_radius=6)
        row.pack(fill="x", pady=2, padx=4)

        # 左側色條：比整列淡淡的底色更容易一眼看出嚴重度
        stripe = ctk.CTkFrame(row, width=6, height=30, corner_radius=3, fg_color=("gray92", "gray20"))
        stripe.pack(side=tk.LEFT, padx=(6, 2), pady=4)
        stripe.pack_propagate(False)

        lbl_no = ctk.CTkLabel(row, text=f"{i + 1}.", width=26, text_color="gray",
                              font=("Arial", 13))
        lbl_no.pack(side=tk.LEFT, padx=(2, 0))
        lbl_txt = ctk.CTkLabel(row, text="", anchor="w", font=("Arial", 14))
        lbl_txt.pack(side=tk.LEFT, padx=6, fill="x", expand=True)

        # 點任一處都能看該列的檢查說明
        for widget in (row, lbl_no, lbl_txt, stripe):
            widget.bind("<Button-1>", lambda e, k=i: self._show_issue_detail(k))

        btn_del = ctk.CTkButton(row, text="✕", width=30, height=26, fg_color="#C13828",
                                hover_color="#8B2519", font=("Arial", 13, "bold"),
                                command=lambda: self.delete_command(i))
        btn_del.pack(side=tk.RIGHT, padx=(2, 6))
        btn_dn = ctk.CTkButton(row, text="▼", width=30, height=26, fg_color="#4A4A4A",
                               hover_color="#5C5C5C", font=("Arial", 13),
                               command=lambda: self.move_command(i, 1))
        btn_dn.pack(side=tk.RIGHT, padx=2)
        btn_up = ctk.CTkButton(row, text="▲", width=30, height=26, fg_color="#4A4A4A",
                               hover_color="#5C5C5C", font=("Arial", 13),
                               command=lambda: self.move_command(i, -1))
        btn_up.pack(side=tk.RIGHT, padx=2)

        return {"row": row, "txt": lbl_txt, "up": btn_up, "down": btn_dn,
                "no": lbl_no, "stripe": stripe}

    def update_script_display(self):
        """更新指令清單。

        🚀 重複使用既有的列，只在數量改變時才新增或移除元件。
           原本每次都全部銷毀重建，導致上下移動時畫面會閃爍。
        """
        cmds = self.script_data[self.edit_wave_idx.get()]

        # 數量不足就補、過多就砍，其餘沿用
        while len(self._script_rows) < len(cmds):
            self._script_rows.append(self._build_script_row(len(self._script_rows)))
        while len(self._script_rows) > len(cmds):
            self._script_rows.pop()["row"].destroy()

        # 跑一次乾跑檢查，把問題對應到各列
        issues = script_check.check_script(self.script_data)
        wave = self.edit_wave_idx.get()
        by_index = {}
        for x in issues:
            if x["wave"] == wave and x["index"] is not None:
                # 同一列有多個問題時，以最嚴重的為準
                cur = by_index.get(x["index"])
                order = {script_check.ERROR: 0, script_check.WARN: 1, script_check.INFO: 2}
                if cur is None or order[x["level"]] < order[cur["level"]]:
                    by_index[x["index"]] = x

        self._wave_issues = by_index

        last = len(cmds) - 1
        for i, c in enumerate(cmds):
            r = self._script_rows[i]
            issue = by_index.get(i)
            lv = issue["level"] if issue else None
            r["txt"].configure(text=self.format_command(c),
                               text_color=LEVEL_COLOR.get(lv, ("gray10", "gray90")))
            r["stripe"].configure(fg_color=LEVEL_COLOR.get(lv, ("gray92", "gray20")))
            r["no"].configure(text=f"{i + 1}.")
            r["up"].configure(state="normal" if i > 0 else "disabled")
            r["down"].configure(state="normal" if i < last else "disabled")

        self._update_check_summary(issues)
        self._show_issue_detail(None)

        # 空清單時顯示提示文字
        if not cmds:
            if self._empty_hint is None:
                self._empty_hint = ctk.CTkLabel(self.script_list, text="(尚未設定任何指令)",
                                                text_color="gray", font=("Arial", 14))
                self._empty_hint.pack(pady=25)
        elif self._empty_hint is not None:
            self._empty_hint.destroy()
            self._empty_hint = None

    def save_profile(self):
        try:
            d = os.path.join(get_base_dir(), "assets_saves")
            os.makedirs(d, exist_ok=True)
            fp = filedialog.asksaveasfilename(initialdir=d, defaultextension=".json", filetypes=[("FGO 腳本檔", "*.json")])
            if not fp: return
            data = self._collect_profile_data()
            with open(fp, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)
            write_app_config({'last_profile': fp})   # 🚀 記住這次存到哪，下次開機自動載入
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
            self._apply_profile_data(data)
            write_app_config({'last_profile': fp})   # 🚀 記住這次讀了哪個檔
            self.update_status_label(f"狀態：已載入設定 ({os.path.basename(fp)})", "#28a745")
        except Exception as e: 
            messagebox.showerror("讀檔失敗", traceback.format_exc())

    # ==============================
    # 💾 設定檔的收集 / 套用 (存檔、讀檔、自動載入共用)
    # ==============================
    def _collect_profile_data(self):
        """把目前 UI 上的所有設定收集成 dict"""
        return {
            'device_id': self.entry_adb.get(),
            'battle_mode': self.battle_mode.get(), 'smart_turn_mode': self.smart_turn_mode.get(),
            'skill_mode': self.skill_mode.get(), 'extreme_sleep': self.extreme_sleep.get(),
            'apple_mode': self.apple_mode.get(), 'loop_target': self.loop_target.get(),
            'support_class': self.support_class.get(), 'target_servant_paths': self.target_servant_paths,
            'target_ce_paths': self.target_ce_paths, 'team_index': int(self.team_index.get()),
            'script_data': self.script_data, 'auto_formation': self.auto_formation.get(),
            'interlude_mode': self.interlude_mode.get(), 'ai_card_mode': self.ai_card_mode.get(),
            'card_priority': self.card_priority.get(), 'auto_np_mode': self.auto_np_mode.get(),
            'use_roi': self.use_roi.get(),
            'use_raw_capture': self.use_raw_capture.get(),
            'order_change_slot': self.order_change_slot.get(),
            'use_tap': self.use_tap.get(),
            'kill_adb_on_exit': self.kill_adb_on_exit.get()
        }

    def _apply_profile_data(self, data):
        """把 dict 套用回 UI。所有欄位都用 .get() 附預設值，舊版存檔也能正常讀取"""
        dev = data.get('device_id')
        if dev:
            self.entry_adb.delete(0, tk.END)
            self.entry_adb.insert(0, dev)

        self.battle_mode.set(data.get('battle_mode', 'script'))
        self.smart_turn_mode.set(data.get('smart_turn_mode', False))
        self.skill_mode.set(data.get('skill_mode', "智慧安全"))
        self.extreme_sleep.set(str(data.get('extreme_sleep', '2.5')))
        self.apple_mode.set(data.get('apple_mode', '不自動回體'))
        self.loop_target.set(str(data.get('loop_target', '0')))
        self.support_class.set(data.get('support_class', 'ALL'))

        # 🚀 滑桿不會跟著 StringVar 連動，必須手動同步位置
        try:
            self.entry_extreme_sleep.set(float(self.extreme_sleep.get()))
        except (ValueError, AttributeError, TypeError):
            pass

        paths_s = data.get('target_servant_paths', [None, None, None])
        paths_c = data.get('target_ce_paths', [None, None, None])
        for i in range(3):
            self.target_servant_paths[i] = paths_s[i] if i < len(paths_s) else None
            self.selected_servants[i].set(
                os.path.basename(paths_s[i]) if i < len(paths_s) and paths_s[i] else "尚未選取")
            self.target_ce_paths[i] = paths_c[i] if i < len(paths_c) else None
            self.selected_ces[i].set(
                os.path.basename(paths_c[i]) if i < len(paths_c) and paths_c[i] else "尚未選取")

        self.team_index.set(str(data.get('team_index', 1)))
        self.auto_formation.set(data.get('auto_formation', False))
        self.interlude_mode.set(data.get('interlude_mode', False))
        self.ai_card_mode.set(data.get('ai_card_mode', False))
        self.card_priority.set(data.get('card_priority', "無"))
        self.auto_np_mode.set(data.get('auto_np_mode', True))
        self.use_roi.set(data.get('use_roi', True))
        self.use_raw_capture.set(data.get('use_raw_capture', True))
        self.order_change_slot.set(str(data.get('order_change_slot', 3)))
        self.use_tap.set(data.get('use_tap', True))
        self.kill_adb_on_exit.set(data.get('kill_adb_on_exit', False))
        self.script_data = data.get('script_data', [[], [], []])
        self.update_script_display()

    def auto_load_last_profile(self):
        """開機時自動套用上次使用的設定檔。任何失敗都只印訊息，不打斷啟動"""
        fp = read_app_config().get('last_profile')
        if not fp or not os.path.exists(fp):
            return
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                self._apply_profile_data(json.load(f))
            self.update_status_label(f"狀態：已自動載入 ({os.path.basename(fp)})", "#28a745")
            print(f"💾 已自動載入上次設定: {fp}")
        except Exception as e:
            print(f"⚠️ 自動載入設定失敗，將使用預設值: {e}")

    # ==============================
    # 🔄 自動更新
    # ==============================
    def manual_check_update(self):
        """使用者主動按下的更新檢查：不論結果都要有回應。"""
        self.update_status_label("狀態：正在檢查更新...", "orange")

        def up_to_date(info):
            self.root.after(0, lambda: (
                self.update_status_label(f"狀態：目前已是最新版 v{CURRENT_VERSION}", "#28a745"),
                messagebox.showinfo("檢查更新", f"目前已是最新版本 v{CURRENT_VERSION}。")))

        def failed(msg):
            self.root.after(0, lambda: (
                self.update_status_label("狀態：無法檢查更新", "#dc3545"),
                messagebox.showwarning(
                    "檢查更新失敗",
                    f"無法連線至更新伺服器（{msg}）。\n\n"
                    f"可以直接到專案頁面查看是否有新版本：\n{RELEASES_URL}")))

        check_for_update_async(
            lambda info: self.root.after(0, lambda: self._ask_update(info)),
            on_error=failed, on_up_to_date=up_to_date)

    def check_update(self):
        check_for_update_async(
            lambda info: self.root.after(0, lambda: self._ask_update(info)),
            on_error=lambda msg: print(f"[更新檢查] 略過：{msg}")
        )

    def _ask_update(self, info):
        notes = info["notes"]
        if len(notes) > 400:
            notes = notes[:400] + "\n..."
        size_txt = ""
        if info.get("zip"):
            size_txt = f"\n更新檔大小：{info['zip']['size'] / 1024 / 1024:.1f} MB"
        msg = (f"目前版本：v{CURRENT_VERSION}\n"
               f"最新版本：{info['version']}{size_txt}\n\n"
               f"{notes}\n\n"
               f"要現在自動更新嗎？\n（程式會關閉，更新完成後自動重新開啟）")
        if messagebox.askyesno("🎉 有新版本可用", msg):
            self._start_update(info)

    def _start_update(self, info):
        self.stop_script()
        for b in (self.btn_start, self.btn_save, self.btn_load):
            b.configure(state="disabled")

        def on_fail(m):
            messagebox.showerror("更新失敗", f"{m}\n\n將為您開啟下載頁面，請手動更新。")
            webbrowser.open(info["page"])
            self.btn_start.configure(state="normal")
            self.btn_save.configure(state="normal")
            self.btn_load.configure(state="normal")

        download_and_apply_async(
            info,
            on_progress=lambda p: self.update_status_label(f"狀態：下載更新中... {p}%", "orange"),
            on_ready=lambda: self.root.after(0, self.root.destroy),
            on_error=lambda m: self.root.after(0, lambda: on_fail(m))
        )

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
                
                # 🚀 啟動前跑一次乾跑檢查。有錯誤時詢問，但不強制阻擋 ——
                #    使用者可能有程式沒考慮到的理由。
                if self.battle_mode.get() == "script":
                    issues = script_check.check_script(self.script_data)
                    if script_check.has_error(issues):
                        report = script_check.format_report(
                            [x for x in issues if x["level"] != script_check.INFO])
                        if not messagebox.askyesno(
                                "腳本檢查發現問題",
                                f"{script_check.summarize(issues)}\n\n{report}\n\n仍要繼續執行嗎？"):
                            self.running = False
                            self.btn_start.configure(state="normal")
                            self.btn_stop.configure(state="disabled")
                            return

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
                    'interlude_mode': self.interlude_mode.get(),
                    'use_roi': self.use_roi.get(),
                    'use_raw_capture': self.use_raw_capture.get(),
                    'order_change_slot': int(self.order_change_slot.get()),
                    'use_tap': self.use_tap.get()
                }
                
                self.session_id += 1
                my_session = self.session_id
                self.logic_thread = None
                self.update_status_label("狀態：正在連線模擬器...", "orange")

                # 獨立執行緒執行大腦，若出錯也能被抓到
                def thread_worker():
                    try:
                        # 🚀 FGOLogic 建構時會跑 ADB 初始化（最久 10 秒），
                        #    放在這裡執行，按下「開始」時視窗就不會凍住
                        logic = FGOLogic(config, self.update_status_label,
                                         lambda: self.stop_script(session=my_session))

                        # 建構期間若使用者已按下停止（或又按了一次開始），直接放棄這一輪
                        if my_session != self.session_id or not self.running:
                            print("🛑 啟動已被取消，本輪不執行")
                            return

                        self.logic_thread = logic
                        logic.run_logic()
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
            
    def stop_script(self, session=None):
        # 🚀 舊執行緒收尾時會帶著自己的 session 編號回呼，
        #    如果使用者已經開始新的一輪，就忽略這次請求，避免誤關新一輪的 UI
        if session is not None and session != self.session_id:
            print(f"↩️ 忽略第 {session} 輪的停止回呼（目前已是第 {self.session_id} 輪）")
            return

        self.running = False
        if self.logic_thread: self.logic_thread.running = False
        self.root.after(0, self._stop_script_ui)

    def _stop_script_ui(self):
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        if "任務達成" not in self.label_status.cget("text"):
            self.label_status.configure(text="狀態：已停止", text_color="#dc3545")

    def on_close(self):
        """關閉視窗時的收尾：先停腳本，需要的話再關掉 ADB 服務。"""
        self.stop_script()
        if self.kill_adb_on_exit.get():
            self.update_status_label("狀態：正在關閉 ADB 服務...", "orange")
            self.root.update()
            kill_adb_server()
        self.root.destroy()

    def set_conn_state(self, state, text):
        """更新連線指示燈。state: connected / checking / disconnected"""
        colour = {"connected": "#28a745", "checking": "#ffc107", "disconnected": "#dc3545"}
        c = colour.get(state, "gray")
        self.led_indicator.configure(text_color=c)
        self.lbl_conn.configure(text=text, text_color=c)

    def check_connection_async(self):
        """在背景確認目前填入的位址是否真的連得上。

        只查詢不主動連線，所以很快；若填入的位址不通、而剛好只有一台裝置在線，
        就順手帶入，省去使用者再按一次「自動偵測」。
        """
        self.set_conn_state("checking", "檢查中...")

        def worker():
            try:
                devices = list_devices()
            except Exception as e:
                print(f"[連線檢查] 失敗: {e}")
                devices = []
            target = self.entry_adb.get().strip()
            self.root.after(0, lambda: self._apply_conn_result(devices, target))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_conn_result(self, devices, target):
        if target in devices:
            self.set_conn_state("connected", "已連線")
            print(f"[連線檢查] {target} 已連線")
            return

        if len(devices) == 1:
            self.entry_adb.delete(0, tk.END)
            self.entry_adb.insert(0, devices[0])
            self.set_conn_state("connected", "已連線 (自動帶入)")
            print(f"[連線檢查] 填入的 {target} 未連線，改用偵測到的 {devices[0]}")
            return

        if devices:
            self.set_conn_state("disconnected", f"未連線 (偵測到 {len(devices)} 台)")
            print(f"[連線檢查] {target} 未連線，可用裝置: {devices}")
            return

        self.set_conn_state("disconnected", "未連線 (請按自動偵測)")
        print("[連線檢查] 找不到任何已連線裝置")

    def detect_adb(self):
        """自動偵測模擬器（在背景執行緒跑，避免視窗假死）"""
        self.update_status_label("狀態：正在偵測設備...", "white")
        self.set_conn_state("checking", "偵測中...")

        def worker():
            try:
                devices = detect_devices(
                    status_cb=lambda msg: self.update_status_label(f"狀態：{msg}", "orange")
                )
            except Exception:
                err = traceback.format_exc()
                self.root.after(0, lambda: messagebox.showerror("ADB 執行錯誤", err))
                return
            self.root.after(0, lambda: self._apply_detect_result(devices))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_detect_result(self, devices):
        if devices:
            self.entry_adb.delete(0, tk.END)
            self.entry_adb.insert(0, devices[0])
            self.set_conn_state("connected", "已連線")
            self.update_status_label(f"狀態：ADB 連線成功 ({devices[0]})", "#28a745")
            extra = f"\n(共偵測到 {len(devices)} 台，已選用第一台)" if len(devices) > 1 else ""
            messagebox.showinfo("成功", f"已連線: {devices[0]}{extra}")
        else:
            self.set_conn_state("disconnected", "未連線")
            self.update_status_label("狀態：找不到設備，請確認模擬器設定", "#dc3545")
            messagebox.showwarning("找不到設備",
                "請確認模擬器已開啟，且已在模擬器設定中啟用「ADB 偵錯 / Root」。")

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
                
                pil_img = self.last_raw_image.resize(PREVIEW_SIZE, Image.LANCZOS)
                self.ctk_preview_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=PREVIEW_SIZE)
                self.lbl_image_preview.configure(image=self.ctk_preview_image, text="")
                
                self.btn_save_screenshot.configure(state="normal")
                self.set_conn_state("connected", "已連線")   # 截得到圖就是真的通了
                self.update_status_label("狀態：截圖成功，請至「系統與進階」查看並存檔", "#28a745")
            else:
                self.set_conn_state("disconnected", "未連線")
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

if __name__ == "__main__":
    # 🚀 一定要最先呼叫：之後所有 print 都會同時寫進紀錄檔。
    #    打包成 --noconsole 之後，這是唯一的診斷來源。
    fgo_logger.setup_logging(CURRENT_VERSION)

    root = ctk.CTk()
    app = FGOApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()