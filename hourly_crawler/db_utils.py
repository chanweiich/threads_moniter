"""
SQLite 資料庫工具模組
提供其他組員查詢 posts 表的便利函式
"""
import sqlite3
import os
from datetime import datetime, timedelta

# 取得專案根目錄 (hourly_crawler 的上層)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "threads_posts.db")


def get_connection():
    """取得 SQLite 資料庫連線"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_posts(limit=100):
    """
    取得所有貼文 (依最後更新時間排序)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM posts ORDER BY updated_at DESC LIMIT ?', (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_post_by_url(url):
    """
    根據 URL 取得單篇貼文
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM posts WHERE url = ?', (url,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_posts_by_author(author):
    """
    根據作者名稱取得貼文 (模糊比對)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM posts WHERE author LIKE ? ORDER BY updated_at DESC', (f'%{author}%',))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def search_posts(keyword):
    """
    搜尋貼文內容 (模糊比對)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM posts WHERE content LIKE ? ORDER BY updated_at DESC', (f'%{keyword}%',))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_recent_posts(hours=24):
    """
    取得最近 N 小時內更新的貼文
    """
    conn = get_connection()
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    cursor.execute('SELECT * FROM posts WHERE updated_at >= ? ORDER BY updated_at DESC', (cutoff,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_top_posts(by='likes', limit=10):
    """
    取得互動數最高的貼文
    
    Args:
        by: 排序依據 ('likes', 'comments', 'reposts')
        limit: 最多回傳幾筆
    """
    allowed = {'likes', 'comments', 'reposts', 'shares'}
    column = by if by in allowed else 'likes'
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f'SELECT * FROM posts ORDER BY {column} DESC LIMIT ?', (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_stats():
    """
    取得資料庫統計資訊
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM posts')
    total_posts = cursor.fetchone()[0]
    
    cursor.execute('SELECT MAX(updated_at) FROM posts')
    last_update = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_posts': total_posts,
        'last_update': last_update
    }


# ===== 使用範例 =====
if __name__ == "__main__":
    print("=== 資料庫統計 ===")
    stats = get_stats()
    print(f"總貼文數：{stats['total_posts']}")
    print(f"最後更新：{stats['last_update']}")
    
    print("\n=== 最新 5 筆貼文 ===")
    for post in get_all_posts(limit=5):
        print(f"- [{post['author']}] {post['content'][:50] if post['content'] else ''}...")
        print(f"  ❤️ {post['likes']} | 💬 {post['comments']} | 🔄 {post['reposts']}")
        print()
