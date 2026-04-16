from flask import Flask, render_template, jsonify, request
import json
import os
import subprocess
import sys
import threading
from dotenv import load_dotenv
from datetime import datetime, timedelta
import re
import sqlite3
import collections

# 讀取上一層目錄 (專案根目錄) 的 .env 檔案
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)

# 資料庫路徑設定
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "threads_posts.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def get_python_executable():
    """Return the correct Python executable for this environment."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Windows virtualenv path
    win_path = os.path.join(project_root, ".venv", "Scripts", "python.exe")
    # Mac/Linux virtualenv path
    posix_path = os.path.join(project_root, ".venv", "bin", "python")

    if os.path.exists(win_path):
        return win_path
    if os.path.exists(posix_path):
        return posix_path
    return sys.executable


def parse_threads_time(time_str, content_str=""):
    now = datetime.now()
    
    if content_str:
        match_content = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', content_str)
        if match_content:
            try: return datetime(int(match_content.group(1)), int(match_content.group(2)), int(match_content.group(3)))
            except: pass
                
    if not time_str: return None
    time_str = time_str.strip().lower()
    
    match = re.search(r'^(\d+)\s*天', time_str)
    if match: return now - timedelta(days=int(match.group(1)))
        
    match = re.search(r'^(\d+)\s*(h|小時)', time_str)
    if match: return now - timedelta(hours=int(match.group(1)))
        
    match = re.search(r'^(\d+)\s*(m|分鐘)', time_str)
    if match: return now - timedelta(minutes=int(match.group(1)))
        
    match = re.search(r'^(\d+)\s*(s|秒)', time_str)
    if match: return now - timedelta(seconds=int(match.group(1)))
        
    match = re.search(r'^(\d+)\s*(w|週)', time_str)
    if match: return now - timedelta(weeks=int(match.group(1)))
        
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', time_str)
    if match:
        try: return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except: pass
            
    try:
        parts = time_str.split('/')
        if len(parts) == 3: return datetime.strptime(time_str, "%m/%d/%y")
        elif len(parts) == 2:
            dt = datetime.strptime(time_str, "%m/%d")
            return dt.replace(year=now.year)
    except: pass
        
    return None

def run_scraper_and_analyzer():
    try:
        python_exec = get_python_executable()
        print("啟動小規模爬蟲...")
        subprocess.run([python_exec, "hourly_crawler/hourly_scraper.py"], check=True, cwd=os.path.join(os.path.dirname(__file__), ".."))
        print("啟動分析模組...")
        subprocess.run([python_exec, "analyze_crisis.py"], check=True, cwd=os.path.join(os.path.dirname(__file__), ".."))
        print("啟動輿情追蹤模組...")
        subprocess.run([python_exec, "track_trends.py"], check=True, cwd=os.path.join(os.path.dirname(__file__), ".."))
        print("任務完成")
    except Exception as e:
        print(f"執行出錯: {e}")

@app.route('/')
def index():
    data = []
    
    if os.path.exists(DB_PATH):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # 根據你提供的資料表結構進行查詢
            query = """
                SELECT p.url, p.author, p.content, p.likes, p.comments, 
                       p.reposts, p.shares, p.post_date,
                       a.summary, a.sentiment, a.crisis_score
                FROM posts p
                LEFT JOIN post_analysis a ON p.url = a.post_url
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            
            for row in rows:
                post = dict(row)
                item = {
                    "url": post.get("url"),
                    "author": post.get("author", "未知帳號"),
                    "content": post.get("content", ""),
                    "likes": post.get("likes") or 0,
                    "comments": post.get("comments") or 0,
                    "reposts": post.get("reposts") or 0,
                    "shares": post.get("shares") or 0,
                    "time": post.get("post_date", ""),  # 將資料庫的 post_date 映射到前端的 time
                    "analysis": {
                        "summary": post.get("summary") or "分析中...",
                        "sentiment": post.get("sentiment") or "中立",
                        "crisis_score": post.get("crisis_score") or 0
                    }
                }
                data.append(item)
            conn.close()
        except Exception as e:
            print(f"❌ 資料庫讀取錯誤: {e}")

    # --- 以下保持不變 (處理日期格式轉換、排序、圖表數據等) ---
    # 從SQLite讀取trend_data
    trend_data = {}
    try:
        conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "threads_posts.db"))
        cursor = conn.cursor()
        cursor.execute("SELECT post_url, trend, reasoning, gemini_sentiment_score, negative_words, pr_analysis, top_3_complaints FROM trend_analysis")
        for row in cursor.fetchall():
            post_url, trend, reasoning, gemini_sentiment_score, negative_words, pr_analysis, top_3_complaints = row
            trend_data[post_url] = {
                "trend": trend,
                "reasoning": reasoning,
                "gemini_sentiment_score": gemini_sentiment_score,
                "negative_words": json.loads(negative_words) if negative_words else [],
                "pr_analysis": pr_analysis,
                "top_3_complaints": json.loads(top_3_complaints) if top_3_complaints else []
            }
        conn.close()
    except Exception as e:
        print(f"❌ 讀取trend_data錯誤: {e}")
            
    extracted_count = 0
    for item in data:
        # parse_threads_time 會嘗試解析資料庫中的 post_date 內容
        dt = parse_threads_time(item.get('time', ''), item.get('content', ''))
        if dt:
            item['timestamp'] = dt.timestamp()
            item['time_display'] = dt.strftime('%Y/%m/%d')
            extracted_count += 1
        else:
            item['timestamp'] = 0.0
            item['time_display'] = item.get('time') if item.get('time') else '日期不明'
            
        item['trend_info'] = trend_data.get(item.get('url'))
            
    # 排序邏輯：危機分數高者在前，分數相同則日期新者在前
    data.sort(key=lambda x: (x.get('analysis', {}).get('crisis_score', 0), x.get('timestamp', 0.0)), reverse=True)
    
    score_distribution = {str(i): 0 for i in range(1, 11)}
    sentiment_distribution = {"正面": 0, "中立": 0, "負面": 0}
    
    for item in data:
        analysis = item.get("analysis", {})
        score = analysis.get("crisis_score", 0)
        sentiment = analysis.get("sentiment", "中立")
        
        if 1 <= score <= 10:
            score_distribution[str(score)] += 1
            
        if sentiment in sentiment_distribution:
            sentiment_distribution[sentiment] += 1
            
    chart_data = {
        "scores": list(score_distribution.values()),
        "sentiments": [sentiment_distribution["正面"], sentiment_distribution["中立"], sentiment_distribution["負面"]]
    }
            
    # 從SQLite讀取time_series_data
    time_series = []
    try:
        conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "threads_posts.db"))
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM time_series ORDER BY date")
        for row in cursor.fetchall():
            data_str = row[0]
            if data_str:
                time_series.extend(json.loads(data_str))
        conn.close()
    except Exception as e:
        print(f"❌ 讀取time_series_data錯誤: {e}")
            
    ts_by_url = collections.defaultdict(list)
    for row in time_series:
        ts_by_url[row['url']].append(row)
        
    api_status = {"gemini": "Unknown", "groq": "Unknown", "last_updated": ""}
    # 從SQLite讀取api_status
    try:
        conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "threads_posts.db"))
        cursor = conn.cursor()
        cursor.execute("SELECT service_name, status, last_checked FROM api_status")
        for row in cursor.fetchall():
            service_name, status, last_checked = row
            api_status[service_name.lower()] = status
            if service_name.lower() == "gemini" or service_name.lower() == "groq":
                api_status["last_updated"] = last_checked
        conn.close()
    except Exception as e:
        print(f"❌ 讀取api_status錯誤: {e}")
            
    return render_template('index.html', posts=data, chart_data=chart_data, ts_by_url=dict(ts_by_url), api_status=api_status)

def get_search_queries(keyword):
    associations = {
        "宿舍": ["政大 宿舍", "自強七舍", "莊敬宿舍", "政大 住宿"],
        "美食": ["政大 美食", "指南路", "指南夜市", "政大 餐廳"],
        "作弊": ["政大 作弊", "期中 作弊", "期末 作弊"],
        "選課": ["政大 選課", "政大 擋修", "政大 必修", "政大 體育"]
    }
    
    if keyword in associations:
        return associations[keyword]
        
    keyword_lower = keyword.lower()
    if "政大" not in keyword and "nccu" not in keyword_lower:
        return [f"政大 {keyword}"]
    
    return [keyword]

@app.route('/api/search_intent', methods=['GET'])
def search_intent():
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({"status": "error", "queries": []})
        
    queries = get_search_queries(keyword)
    return jsonify({"status": "success", "queries": queries})

def filter_by_date_range(posts, start_date_str=None, end_date_str=None):
    """根據時間範圍篩選貼文"""
    if not start_date_str and not end_date_str:
        return posts
    
    filtered = []
    
    # 解析輸入的日期
    start_dt = None
    end_dt = None
    
    if start_date_str:
        try:
            start_dt = datetime.fromisoformat(start_date_str)
        except:
            pass
    
    if end_date_str:
        try:
            end_dt = datetime.fromisoformat(end_date_str)
            # 設定為該天的 23:59:59 (以包含整個一天)
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
        except:
            pass
    
    for post in posts:
        # 使用 parse_threads_time 將 post_date 轉換為絕對時間
        post_dt = parse_threads_time(post.get('time', ''), post.get('content', ''))
        
        if not post_dt:
            continue
        
        # 檢查是否在時間範圍內
        # 注：如果 post_dt 只有日期部分（沒有時間），會以當天 00:00:00 計算
        if start_dt and post_dt < start_dt:
            continue
        if end_dt and post_dt > end_dt:
            continue
        
        filtered.append(post)
    
    return filtered

@app.route('/api/search', methods=['GET'])
def search_posts():
    keyword = request.args.get('keyword', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    
    if not keyword:
        return jsonify({"status": "error", "message": "請提供搜尋關鍵字"})
        
    search_queries = get_search_queries(keyword)
    
    new_count = 0
    updated_count = 0
    
    try:
        os.chdir("..")
        venv_python = get_python_executable()
        print(f"啟動混合搜尋 (Hybrid Search): {search_queries}")
        result = subprocess.run([venv_python, "hybrid_search.py", *search_queries], capture_output=True, text=True)
        os.chdir("dashboard")
        
        output = result.stdout
        
        if "---OUTPUT_START---" in output and "---OUTPUT_END---" in output:
            try:
                json_str = output.split("---OUTPUT_START---")[1].split("---OUTPUT_END---")[0].strip()
                parsed = json.loads(json_str)
                new_count = parsed.get("new_count", 0)
                updated_count = parsed.get("updated_count", 0)
            except: pass
            
    except Exception as e:
        if os.getcwd().endswith('threads_monitor'):
            os.chdir("dashboard")
        print(f"混合搜查調用失敗: {e}")
    
    # 【改為從資料庫獲取資料做篩選】
    data = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            SELECT p.url, p.author, p.content, p.likes, p.comments, p.post_date,
                   a.summary, a.sentiment, a.crisis_score
            FROM posts p
            LEFT JOIN post_analysis a ON p.url = a.post_url
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        for row in rows:
            post = dict(row)
            
            # 【重點】計算 time_display
            time_str = post.get("post_date", "")
            dt = parse_threads_time(time_str, post.get("content", ""))
            if dt:
                time_display = dt.strftime('%Y/%m/%d')
                timestamp = dt.timestamp()
            else:
                time_display = time_str if time_str else '日期不明'
                timestamp = 0.0
            
            data.append({
                "url": post.get("url"),
                "author": post.get("author", ""),
                "content": post.get("content", ""),
                "likes": post.get("likes", "0"),
                "comments": post.get("comments", "0"),
                "time": post.get("post_date", ""),
                "time_display": time_display,
                "timestamp": timestamp,
                "analysis": {
                    "summary": post.get("summary") or "",
                    "sentiment": post.get("sentiment") or "中立",
                    "crisis_score": post.get("crisis_score") or 0
                }
            })
        conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": "無法讀取資料庫"}), 500

    filtered_posts = []
    all_text_for_cloud = ""
    
    for post in data:
        content = post.get('content', '').lower()
        author = post.get('author', '').lower()
        
        match = False
        if keyword.lower() in content or keyword.lower() in author:
            match = True
        else:
            for q in search_queries:
                if q.lower() in content:
                    match = True
                    break
                    
        if match:
            filtered_posts.append(post)
            all_text_for_cloud += " " + post.get('content', '')
    
    # 【新增】時間範圍篩選
    filtered_posts = filter_by_date_range(filtered_posts, start_date, end_date)
            
    if not filtered_posts:
        return jsonify({"status": "success", "posts": [], "wordcloud": [], "chart_data": None})
        
    import jieba
    from collections import Counter
    
    text_clean = re.sub(r'[^\w\s]', '', all_text_for_cloud)
    words = jieba.lcut(text_clean)
    
    stopwords = set(["的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一個", "上", "也", "很", "到", "說", "要", "去", "你", "會", "著", "沒有", "看", "好", "自己", "這", "那", "呢", "嗎", "啊", "吧", "呀", "惹", "這", "與", "及", "等", "但", "因為", "所以", "如果", "雖然", "而且", "可以", "我們", "他們", "什麼", "怎麼", "還是", "就是", "覺得", "知道", "政大", "然後", "感覺", "不少", "給到"])
    
    def is_valid_word(w):
        if len(w) <= 1: return False
        if w in stopwords: return False
        if re.search(r'\d', w): return False 
        if re.match(r'^[A-Za-z_]+$', w): return False
        return True
        
    filtered_words = [w for w in words if is_valid_word(w)]
    raw_counts = Counter(filtered_words)
    
    focus_words = {"指南": 2, "價格": 3, "好吃": 3, "糖粉": 5, "魷魚": 5, "作弊": 3, "洩題": 4, "宿舍": 2}
    for fw, mult in focus_words.items():
        if fw in raw_counts:
            raw_counts[fw] *= mult
            
    word_counts = raw_counts.most_common(50)
    wordcloud_data = [[w, c] for w, c in word_counts]
    
    score_distribution = {str(i): 0 for i in range(1, 11)}
    sentiment_distribution = {"正面": 0, "中立": 0, "負面": 0}
    
    for post in filtered_posts:
        score = post.get('analysis', {}).get('crisis_score', 0)
        sentiment = post.get('analysis', {}).get('sentiment', '中立')
        
        if 1 <= score <= 10:
            score_distribution[str(score)] += 1
            
        if sentiment in sentiment_distribution:
            sentiment_distribution[sentiment] += 1
            
    chart_data = {
        "scores": list(score_distribution.values()),
        "sentiments": [sentiment_distribution["正面"], sentiment_distribution["中立"], sentiment_distribution["負面"]]
    }
    
    return jsonify({
        "status": "success", 
        "posts": filtered_posts, 
        "wordcloud": wordcloud_data,
        "chart_data": chart_data,
        "new_count": new_count,
        "updated_count": updated_count
    })

@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    thread = threading.Thread(target=run_scraper_and_analyzer)
    thread.start()
    return jsonify({"status": "success", "message": "已在背景啟動小規模爬取與分析任務，請稍後重整頁面查看結果。"})

@app.route('/api/add_manual_post', methods=['POST'])
def add_manual_post():
    data = request.json
    raw_url = data.get('url', '').strip()
    
    url = raw_url.split('?')[0].replace('threads.com', 'threads.net').rstrip('/')
    
    if "threads.net" not in url or "@" not in url or "post" not in url:
        return jsonify({"status": "error", "message": "無效的 Threads 網址，請確認連結包含 threads 域名與文章標識。"})
        
    try:
        os.chdir("..")
        venv_python = get_python_executable()
        print(f"手動執行單筆抓取 (使用直譯器: {venv_python}): {url}")
        
        result = subprocess.run([venv_python, "manual_add.py", url], capture_output=True, text=True)
        os.chdir("dashboard")
        
        output = result.stdout
        
        if "---OUTPUT_START---" in output and "---OUTPUT_END---" in output:
            json_str = output.split("---OUTPUT_START---")[1].split("---OUTPUT_END---")[0].strip()
            parsed = json.loads(json_str)
            if parsed.get("status") == "success":
                return jsonify(parsed)
                
        return jsonify({"status": "error", "message": "無法抓取或解析該網址，請確認連結權限或格式。\n" + output[-200:]})
    except Exception as e:
        if os.getcwd().endswith('threads_monitor'):
            os.chdir("dashboard")
        return jsonify({"status": "error", "message": f"伺服器錯誤: {str(e)}"})

@app.route('/api/delete_post', methods=['POST'])
def delete_post():
    data = request.json
    url_to_delete = data.get('url')
    if not url_to_delete:
        return jsonify({"status": "error", "message": "Missing URL"}), 400
        
    try:
        # 【改為使用 SQL 指令刪除】
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 刪除貼文本體
        cursor.execute("DELETE FROM posts WHERE url = ?", (url_to_delete,))
        # 刪除分析資料
        cursor.execute("DELETE FROM post_analysis WHERE post_url = ?", (url_to_delete,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "success", 
            "message": f"已成功移除資料庫中的貼文。"
        })
    except Exception as e:
        print(f"資料庫刪除錯誤: {e}")
        return jsonify({"status": "error", "message": f"刪除失敗：{str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)