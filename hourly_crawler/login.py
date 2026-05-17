"""
Threads 初次手動登入引導模組 (init_login.py)
運行此程式會開啟一個真實的 Chrome 視窗，請手動輸入帳號密碼並完成雙重驗證 (2FA)。
成功登入後，憑證將會永久保存在 browser_data 目錄中，供後續自動化爬蟲無頭使用。
"""
import asyncio
import os
import sys
from playwright.async_api import async_playwright

# 確保抓到正確的專案根目錄與憑證儲存路徑
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_DATA_DIR = os.path.join(BASE_DIR, "browser_data")

async def setup_login():
    print("=" * 60)
    print("🛡️ [Threads 授權憑證初始化系統]")
    print(f"📂 憑證儲存位置: {USER_DATA_DIR}")
    print("=" * 60)
    print("正在啟動瀏覽器...")
    print("⚠️ 請注意：開啟後請『手動』輸入您的 Threads/Instagram 帳號密碼。")
    print("⚠️ 若有雙重驗證 (2FA)，請一併完成。成功看到首頁內容後，再回到終端機按下 Enter 結束。")
    print("-" * 60)

    async with async_playwright() as p:
        # 必須使用與爬蟲完全相同的啟動參數，確保指紋一致性
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,  # 登入引導必須開啟實體視窗讓使用者操作
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox"
            ],
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        page = await context.new_page()
        
        # 導向 Threads 登入頁面
        await page.goto("https://www.threads.net/login", wait_until="domcontentloaded")
        
        # 使用非同步的事件迴圈等待使用者手動確認，避免卡死
        await asyncio.get_event_loop().run_in_executor(
            None, 
            input, 
            "\n👉 【等待確認】當您在瀏覽器中成功登入並看到 Threads 首頁後，請在此處按下 [Enter] 鍵儲存憑證並離開..."
        )

        print("\n正在安全封裝並寫入 Cookie 狀態...")
        await context.close()
        
    print("\n✅ 登入憑證已成功保存！")
    print("以後執行的 hourly_scraper.py 將會自動套用此身分，無需再次登入。")
    print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(setup_login())
    except KeyboardInterrupt:
        print("\n🛑 操作已取消。")
        sys.exit(0)