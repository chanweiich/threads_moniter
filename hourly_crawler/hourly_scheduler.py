#!/usr/bin/env python3
"""
每小時數據排程器 (一次性執行，由 Windows 工作排程器每小時呼叫)

執行邏輯：
  每次呼叫 → 執行 hourly_scraper.py + hourly_update.py
  每 6 小時 → 額外執行 trend_update.py（依 trend_analysis 表的最新 analyzed_at 判斷）
"""
import subprocess
import datetime
import os
import sys
import logging
import platform
import sqlite3
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOURLY_CRAWLER_DIR = os.path.join(PROJECT_ROOT, "hourly_crawler")
DB_PATH = os.path.join(PROJECT_ROOT, "threads_posts.db")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "hourly_scheduler.log")

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)


def get_venv_python():
    if platform.system() == "Windows":
        venv_python = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
    else:
        venv_python = os.path.join(PROJECT_ROOT, ".venv", "bin", "python")

    if not os.path.exists(venv_python):
        logging.warning(f"虛擬環境未找到 ({venv_python})，使用當前 Python")
        return sys.executable

    return venv_python


def make_env():
    """建立子 process 環境變數，強制 UTF-8 輸出（修正 Windows CP950 emoji 錯誤）"""
    return {**os.environ, 'PYTHONIOENCODING': 'utf-8'}


def should_run_trend():
    """
    查詢 trend_analysis 表的最新 analyzed_at，
    若距今超過 6 小時（或從未分析過）則回傳 True
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(analyzed_at) FROM trend_analysis")
        row = cursor.fetchone()
        conn.close()
        if not row or not row[0]:
            return True
        last = datetime.datetime.fromisoformat(row[0])
        elapsed = (datetime.datetime.now() - last).total_seconds()
        return elapsed >= 6 * 3600
    except Exception as e:
        logging.warning(f"無法查詢 trend_analysis，預設執行趨勢分析：{e}")
        return True


def run_script(script_name, cwd, timeout, label):
    """通用腳本執行函式"""
    logging.info(f"啟動 {label}...")
    try:
        result = subprocess.run(
            [get_venv_python(), script_name],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            env=make_env(),
            timeout=timeout
        )
        if result.returncode == 0:
            logging.info(f"{label} 完成")
            if result.stdout:
                logging.info(f"輸出: {result.stdout[-300:]}")
        else:
            logging.error(f"{label} 失敗 (返回碼: {result.returncode})")
            if result.stderr:
                logging.error(f"錯誤: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        logging.warning(f"{label} 超時")
    except Exception as e:
        logging.error(f"{label} 異常: {e}")


if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info(f"排程器啟動 | {platform.system()} {platform.release()} | Python {sys.version.split()[0]}")

    # 每次都執行：爬取新貼文 + 更新近 3 天指標
    run_script("hourly_scraper.py", HOURLY_CRAWLER_DIR, timeout=1800, label="每小時爬蟲")
    time.sleep(10)
    run_script("hourly_update.py",  PROJECT_ROOT,       timeout=1800, label="指標更新（近 3 天）")

    # 每 6 小時執行：趨勢分析
    if should_run_trend():
        logging.info("距上次趨勢分析已超過 6 小時，執行趨勢分析...")
        time.sleep(10)
        run_script("trend_update.py", PROJECT_ROOT, timeout=1800, label="趨勢分析")
    else:
        logging.info("趨勢分析距上次不足 6 小時，跳過。")

    logging.info("本次排程執行完畢。")
    logging.info("=" * 60)
