import sqlite3
import os

# 指向你的資料庫路徑
DB_PATH = "threads_posts.db"

def check_latest_views():
    if not os.path.exists(DB_PATH):
        print("❌ 找不到資料庫檔案！")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 查詢最新的 5 筆貼文，包含各項互動指標
        query = """
            SELECT url, author, likes, comments, views, updated_at 
            FROM posts 
            ORDER BY updated_at DESC 
            LIMIT 5
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        print(f"\n📊 --- 最新 5 筆爬蟲資料驗證 ---")
        for row in rows:
            url, author, likes, comments, views, updated_at = row
            print(f"帳號: @{author}")
            print(f"時間: {updated_at}")
            print(f"指標: 讚({likes}) | 留言({comments}) | 👁️ 瀏覽量({views})")
            print(f"網址: {url}")
            print("-" * 50)

    except sqlite3.OperationalError as e:
        print(f"❌ 查詢失敗，可能是欄位還沒建立：{e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_latest_views()