"""
日誌模組
========
接管 sys.stdout / sys.stderr，讓程式裡既有的 print() 自動同時寫入檔案。

這樣做的好處是不必修改散落各處的數百個 print 呼叫，
零風險、也不會有漏掉某一行的問題。

打包成 --noconsole 之後主控台消失，這個模組就是唯一的診斷來源。
"""

import os
import sys
import time
import glob
import threading
import traceback

LOG_DIR_NAME = "logs"
KEEP_LOGS = 10          # 保留最近幾份紀錄，更舊的自動刪除

_log_file = None
_log_path = None
_lock = threading.Lock()


def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class _Tee:
    """同時往原本的串流與紀錄檔輸出。

    打包成 --noconsole 時 sys.stdout 會是 None，所以每一步都要能容忍
    底層串流不存在；寫檔失敗也絕不能讓主程式崩潰。
    """

    def __init__(self, stream, fh):
        self._stream = stream
        self._fh = fh
        self._at_line_start = True

    def write(self, text):
        if not text:
            return 0
        with _lock:
            if self._stream is not None:
                try:
                    self._stream.write(text)
                except Exception:
                    pass
            try:
                self._write_to_file(text)
            except Exception:
                pass
        return len(text)

    def _write_to_file(self, text):
        if self._fh is None:
            return
        # 逐行處理，只在行首加時間戳，避免同一行被切成多次 write 時重複加
        for part in text.splitlines(keepends=True):
            if self._at_line_start and part.strip():
                self._fh.write(time.strftime("[%H:%M:%S] "))
            self._fh.write(part)
            self._at_line_start = part.endswith("\n")
        self._fh.flush()   # 立刻寫入，確保當機時不會遺失最後幾行

    def flush(self):
        if self._stream is not None:
            try:
                self._stream.flush()
            except Exception:
                pass
        if self._fh is not None:
            try:
                self._fh.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    @property
    def encoding(self):
        return "utf-8"


def _cleanup_old_logs(log_dir):
    """只保留最近 KEEP_LOGS 份紀錄"""
    try:
        files = sorted(glob.glob(os.path.join(log_dir, "fgo_*.log")))
        for old in files[:-KEEP_LOGS]:
            os.remove(old)
    except Exception:
        pass


def get_log_dir():
    return os.path.join(get_base_dir(), LOG_DIR_NAME)


def get_log_path():
    return _log_path


def setup_logging(app_version="?"):
    """啟動紀錄。請在程式最一開始呼叫一次。"""
    global _log_file, _log_path

    if _log_file is not None:      # 避免重複初始化
        return _log_path

    try:
        log_dir = get_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        _cleanup_old_logs(log_dir)

        _log_path = os.path.join(log_dir, time.strftime("fgo_%Y%m%d_%H%M%S.log"))
        _log_file = open(_log_path, "a", encoding="utf-8")
    except Exception as e:
        # 連紀錄檔都開不起來也不能影響主程式
        print(f"⚠️ 無法建立紀錄檔: {e}")
        return None

    sys.stdout = _Tee(sys.__stdout__, _log_file)
    sys.stderr = _Tee(sys.__stderr__, _log_file)

    # 未捕捉的例外也要進紀錄，否則 --noconsole 下會完全無跡可循
    def _excepthook(exc_type, exc, tb):
        print("=" * 60)
        print("❌ 未捕捉的例外")
        traceback.print_exception(exc_type, exc, tb)
        print("=" * 60)

    sys.excepthook = _excepthook

    # 子執行緒的例外預設不會走 sys.excepthook，要另外掛
    if hasattr(threading, "excepthook"):
        def _thread_excepthook(args):
            print("=" * 60)
            print(f"❌ 執行緒 {args.thread.name if args.thread else '?'} 發生未捕捉的例外")
            traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
            print("=" * 60)
        threading.excepthook = _thread_excepthook

    print("=" * 60)
    print(f"FGO Auto v{app_version} 啟動")
    print(f"時間: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"執行模式: {'打包 EXE' if getattr(sys, 'frozen', False) else '原始碼'}")
    print(f"工作目錄: {get_base_dir()}")
    print(f"紀錄檔: {_log_path}")
    print("=" * 60)

    return _log_path


def open_log_folder():
    """開啟紀錄資料夾，方便使用者回報問題時取出檔案"""
    try:
        log_dir = get_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        if os.name == 'nt':
            os.startfile(log_dir)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", log_dir])
        return True
    except Exception as e:
        print(f"⚠️ 無法開啟紀錄資料夾: {e}")
        return False