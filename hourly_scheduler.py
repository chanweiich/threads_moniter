"""
每小時 Threads 爬蟲 - 單次執行版本
設計給 Windows 工作排程器使用，執行一次後自動結束
"""
import asyncio
import sys
import datetime
from hourly_scraper import scrape_threads_hourly, init_database


def main():
    """執行單次爬蟲任務"""
    print("=" * 50)
    print(f"[{datetime.datetime.now()}] 🕐 Threads 爬蟲啟動")
    print("=" * 50)
    
    keywords = ["政大", "國立政治大學", "NCCU", "政大交流板"]
    
    try:
        # 初始化資料庫 (如果表格不存在會自動建立)
        init_database()
        
        # 執行爬蟲
        stats = asyncio.run(scrape_threads_hourly(keywords))
        
        print(f"\n[{datetime.datetime.now()}] ✅ 爬蟲任務完成！")
        print(f"   統計：共 {stats['total']} 筆貼文")
        return 0
        
    except Exception as e:
        print(f"[{datetime.datetime.now()}] ❌ 爬蟲任務失敗：{e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
