#!/usr/bin/env python3
"""
每小時數據爬取排程器
負責每小時運行一次數據爬取，將新數據存入 threads_posts.db

適用於 Windows 任務計劃程序定時執行 & Mac cron 定時執行
"""
import time
import subprocess
import datetime
import os
import sys
import logging
import platform

# 獲取專案根目錄（hourly_scheduler.py 的上層目錄）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOURLY_CRAWLER_DIR = os.path.join(PROJECT_ROOT, "hourly_crawler")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "hourly_scheduler.log")

# 建立 logs 目錄
os.makedirs(LOG_DIR, exist_ok=True)

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def get_venv_python():
    """
    跨平台獲取虛擬環境中的 Python 路徑
    Windows: .venv\Scripts\python.exe
    Mac/Linux: .venv/bin/python
    """
    if platform.system() == "Windows":
        venv_python = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
    else:  # Mac, Linux
        venv_python = os.path.join(PROJECT_ROOT, ".venv", "bin", "python")
    
    # 如果虛擬環境不存在，使用當前 Python 直譯器
    if not os.path.exists(venv_python):
        logging.warning(f"虛擬環境未找到 ({venv_python})，使用當前 Python")
        return sys.executable
    
    return venv_python

def run_hourly_scraper():
    """運行每小時數據爬取"""
    logging.info("🚀 啟動每小時數據爬取...")

    try:
        venv_python = get_venv_python()
        
        # 運行 hourly_scraper.py（在 hourly_crawler 目錄中執行）
        result = subprocess.run([venv_python, "hourly_scraper.py"],
                              cwd=HOURLY_CRAWLER_DIR,
                              capture_output=True,
                              text=True,
                              timeout=300)  # 5分鐘超時

        if result.returncode == 0:
            logging.info("✅ 數據爬取完成")
            if result.stdout:
                logging.info(f"輸出: {result.stdout[-200:]}")
        else:
            logging.error(f"❌ 數據爬取失敗 (返回碼: {result.returncode})")
            if result.stderr:
                logging.error(f"錯誤: {result.stderr[-500:]}")

    except subprocess.TimeoutExpired:
        logging.warning("⏰ 數據爬取超時")
    except Exception as e:
        logging.error(f"❌ 數據爬取異常: {e}")

def run_analysis_if_needed():
    """每小時運行趨勢分析"""
    logging.info("📊 啟動每小時趨勢分析...")

    try:
        venv_python = get_venv_python()

        # 運行 track_trends.py（在根目錄執行）
        result = subprocess.run([venv_python, "track_trends.py"],
                              cwd=PROJECT_ROOT,
                              capture_output=True,
                              text=True,
                              timeout=600)  # 10分鐘超時

        if result.returncode == 0:
            logging.info("✅ 趨勢分析完成")
        else:
            logging.error("❌ 趨勢分析失敗")
            if result.stderr:
                logging.error(f"錯誤: {result.stderr[-500:]}")

    except subprocess.TimeoutExpired:
        logging.warning("⏰ 趨勢分析超時")
    except Exception as e:
        logging.error(f"❌ 趨勢分析異常: {e}")

if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info("🕐 Threads 每小時數據爬取排程器已啟動")
    logging.info(f"💻 作業系統: {platform.system()} {platform.release()}")
    logging.info(f"🐍 Python: {sys.version}")
    logging.info("設定：")
    logging.info("  - 每小時爬取新數據 → threads_posts.db")
    logging.info("  - 每小時運行趨勢分析 → trend_analysis表")
    logging.info(f"  - 日誌檔案：{LOG_FILE}")
    logging.info("  - 虛擬環境：自動偵測 (Windows/Mac/Linux 相容)")
    logging.info("=" * 60)

    while True:
        # 每小時運行數據爬取
        run_hourly_scraper()

        # 每小時運行趨勢分析
        run_analysis_if_needed()

        logging.info("😴 等待下一個小時...")
        time.sleep(3600)  # 休眠 1 小時