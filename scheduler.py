import time
import subprocess
import datetime
import os

def run_tracker():
    print(f"\\n[{datetime.datetime.now()}] ⚡ 啟動自動化回診排程 (track_trends.py)...")
    try:
        subprocess.run(["python3", "track_trends.py"])
        print(f"[{datetime.datetime.now()}] ✅ 回診結束。等待下一次排程...")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] ❌ 執行失敗：{e}")

if __name__ == "__main__":
    print("===========================================")
    print("🔥 Threads 跨時間監控排程器已啟動 🔥")
    print("設定：每 4 小時自動回診一次 (追蹤 7 天內 >4 分之貼文)")
    print("===========================================")
    
    while True:
        run_tracker()
        time.sleep(4 * 3600)  # 休眠 4 小時
