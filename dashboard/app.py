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



def get_actual_post_time(time_str, reference_datetime=None):
    if not time_str:
        return None
    if not reference_datetime:
        reference_datetime = datetime.now()

    time_str = time_str.strip().lower()

    if time_str in ('近期', '剛剛', 'now', 'just now', 'recently'):
        return reference_datetime

    match = re.search(r'^(\d+)\s*天', time_str)
    if match:
        return reference_datetime - timedelta(days=int(match.group(1)))

    match = re.search(r'^(\d+)\s*(h|小時)', time_str)
    if match:
        return reference_datetime - timedelta(hours=int(match.group(1)))

    match = re.search(r'^(\d+)\s*(m|分鐘)', time_str)
    if match:
        return reference_datetime - timedelta(minutes=int(match.group(1)))

    match = re.search(r'^(\d+)\s*(s|秒)', time_str)
    if match:
        return reference_datetime - timedelta(seconds=int(match.group(1)))

    match = re.search(r'^(\d+)\s*(w|週)', time_str)
    if match:
        return reference_datetime - timedelta(weeks=int(match.group(1)))

    # ISO 8601 含時間，例如 2026-05-19T07:44:00.000Z
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})[t ](\d{1,2}):(\d{2})', time_str)
    if match:
        try:
            from datetime import timezone
            dt_utc = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)),
                              int(match.group(4)), int(match.group(5)), tzinfo=timezone.utc)
            return dt_utc.astimezone().replace(tzinfo=None)
        except:
            pass

    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', time_str)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except:
            return None

    try:
        parts = time_str.split('/')
        if len(parts) == 3:
            return datetime.strptime(time_str, "%m/%d/%y")
        elif len(parts) == 2:
            dt = datetime.strptime(time_str, "%m/%d")
            return dt.replace(year=reference_datetime.year)
    except:
        pass

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
                       p.reposts, p.shares, p.views, p.post_date, p.created_at,
                       a.summary, a.sentiment, a.crisis_score
                FROM posts p
                LEFT JOIN post_analysis a ON p.url = a.post_url
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            
            for row in rows:
                post = dict(row)
                created_at = post.get("created_at")
                actual_post_dt = None
                if created_at:
                    try:
                        actual_post_dt = datetime.fromisoformat(created_at)
                    except:
                        actual_post_dt = None

                real_post_time = get_actual_post_time(post.get("post_date", ""), actual_post_dt)
                if real_post_time:
                    real_post_time_display = real_post_time.strftime('%Y/%m/%d %H:%M')
                else:
                    real_post_time_display = '日期不明'

                content_str = post.get("content", "") or ""
                author_str = post.get("author", "") or ""
                has_reply_marker = bool(re.search(r'正在回覆@|Replying to @', content_str))
                content_starts_with_other = (
                    bool(author_str) and
                    bool(content_str.strip()) and
                    not content_str.strip().startswith(author_str)
                )
                is_reply = has_reply_marker or content_starts_with_other
                item = {
                    "url": post.get("url"),
                    "author": post.get("author", "未知帳號"),
                    "content": content_str,
                    "likes": post.get("likes") or 0,
                    "comments": post.get("comments") or 0,
                    "reposts": post.get("reposts") or 0,
                    "shares": post.get("shares") or 0,
                    "views": post.get("views") or 0,
                    "time": post.get("post_date", ""),
                    "real_post_time_display": real_post_time_display,
                    "is_reply": is_reply,
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
    # 從SQLite讀取trend_data（沿用前面已開啟的連線）
    trend_data = {}
    time_series = []
    api_status = {"gemini": "Unknown", "groq": "Unknown", "last_updated": ""}
    overall_summary = None
    try:
        conn = get_db_connection()
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

        cursor.execute("SELECT data FROM time_series ORDER BY date")
        for row in cursor.fetchall():
            data_str = row[0]
            if data_str:
                time_series.extend(json.loads(data_str))

        cursor.execute("SELECT service_name, status, last_checked FROM api_status")
        for row in cursor.fetchall():
            service_name, status, last_checked = row
            api_status[service_name.lower()] = status
            if service_name.lower() in ("gemini", "groq"):
                api_status["last_updated"] = last_checked

        try:
            cursor.execute("SELECT summary_text, generated_at FROM overall_summary ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                overall_summary = {"text": row[0], "generated_at": row[1]}
        except:
            pass

        conn.close()
    except Exception as e:
        print(f"❌ 讀取附加資料錯誤: {e}")
            
    for item in data:
        rpt = item.get('real_post_time_display', '')
        if rpt and rpt != '日期不明':
            try:
                dt = datetime.strptime(rpt[:10], '%Y/%m/%d')
                item['timestamp'] = dt.timestamp()
                item['time_display'] = dt.strftime('%Y/%m/%d')
            except:
                item['timestamp'] = 0.0
                item['time_display'] = '日期不明'
        else:
            item['timestamp'] = 0.0
            item['time_display'] = '日期不明'

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

    ts_by_url = collections.defaultdict(list)
    for row in time_series:
        ts_by_url[row['url']].append(row)
            
    if not os.environ.get('GROQ_API_KEY') and not os.environ.get('GEMINI_API_KEY'):
        summary_text = "尚未設定 LLM API Key，摘要功能將於啟用後自動生成。"
    else:
        summary_text = "系統已啟用 LLM 摘要功能，將於下一次資料更新時產生本期間摘要。"

    return render_template('index.html', posts=data, chart_data=chart_data, ts_by_url=dict(ts_by_url), api_status=api_status, summary_text=summary_text, overall_summary=overall_summary)

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

VIRAL_ENGAGEMENT_THRESHOLD = 10000

def filter_by_date_range(posts, start_date_str=None, end_date_str=None):
    """根據時間範圍篩選貼文。

    除了發布日期在範圍內的貼文，也會納入發布在範圍外但在篩選期間
    按讚數或留言數增加 >= VIRAL_ENGAGEMENT_THRESHOLD 的炎上貼文。
    若尚無快照資料，以當前互動數 >= 門檻值作為近似判斷。
    """
    if not start_date_str and not end_date_str:
        return posts

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
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
        except:
            pass

    # 查詢快照資料，找出在篩選期間互動增量 >= 門檻值的貼文
    viral_urls = set()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        range_start = (start_dt or datetime(2000, 1, 1)).isoformat()
        range_end = (end_dt or datetime.now()).isoformat()
        cursor.execute("""
            SELECT url,
                MAX(likes) - MIN(likes) AS likes_growth,
                MAX(comments) - MIN(comments) AS comments_growth
            FROM post_snapshots
            WHERE captured_at >= ? AND captured_at <= ?
            GROUP BY url
            HAVING likes_growth >= ? OR comments_growth >= ?
        """, (range_start, range_end, VIRAL_ENGAGEMENT_THRESHOLD, VIRAL_ENGAGEMENT_THRESHOLD))
        viral_urls = {row[0] for row in cursor.fetchall()}
        conn.close()
    except:
        pass

    filtered = []
    for post in posts:
        rpt = post.get('real_post_time_display', '')
        if not rpt or rpt == '日期不明':
            continue
        try:
            post_dt = datetime.strptime(rpt[:10], '%Y/%m/%d')
        except:
            continue

        in_range = True
        if start_dt and post_dt < start_dt:
            in_range = False
        if end_dt and post_dt > end_dt:
            in_range = False

        if in_range:
            filtered.append(post)
        elif post.get('url') in viral_urls:
            # 快照資料顯示此貼文在篩選期間互動暴增
            post_copy = dict(post)
            post_copy['viral_during_range'] = True
            filtered.append(post_copy)

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
            SELECT p.url, p.author, p.content, p.likes, p.comments, p.post_date, p.created_at,
                   a.summary, a.sentiment, a.crisis_score
            FROM posts p
            LEFT JOIN post_analysis a ON p.url = a.post_url
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        for row in rows:
            post = dict(row)

            created_at = post.get("created_at")
            actual_post_dt = None
            if created_at:
                try:
                    actual_post_dt = datetime.fromisoformat(created_at)
                except:
                    pass
            real_post_time = get_actual_post_time(post.get("post_date", ""), actual_post_dt)
            if real_post_time:
                time_display = real_post_time.strftime('%Y/%m/%d')
                timestamp = real_post_time.timestamp()
            else:
                time_display = '日期不明'
                timestamp = 0.0
            
            _content = post.get("content", "") or ""
            _author = post.get("author", "") or ""
            _is_reply = (
                bool(re.search(r'正在回覆@|Replying to @', _content)) or
                (bool(_author) and bool(_content.strip()) and not _content.strip().startswith(_author))
            )
            data.append({
                "url": post.get("url"),
                "author": _author,
                "content": _content,
                "likes": post.get("likes", "0"),
                "comments": post.get("comments", "0"),
                "time": post.get("post_date", ""),
                "time_display": time_display,
                "timestamp": timestamp,
                "is_reply": _is_reply,
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

@app.route('/api/generate_summary', methods=['POST'])
def generate_summary():
    from google import genai as google_genai

    if not os.environ.get('GEMINI_API_KEY'):
        return jsonify({"status": "error", "message": "未設定 GEMINI_API_KEY"})

    try:
        body = request.get_json(silent=True) or {}
        posts = body.get('posts', [])

        if not posts:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.summary, a.sentiment, a.crisis_score
                FROM post_analysis a
                WHERE a.summary IS NOT NULL AND a.summary != '' AND a.summary != '分析中...'
                ORDER BY a.crisis_score DESC
                LIMIT 30
            """)
            posts = [dict(row) for row in cursor.fetchall()]
            conn.close()

        if not posts:
            return jsonify({"status": "error", "message": "尚無分析資料可供摘要，請先執行危機分析。"})

        post_summaries = "\n".join([
            f"- [{p.get('sentiment', '中立')}｜危機{p.get('crisis_score', 0)}分] {p.get('summary', '')}"
            for p in posts
        ])

        prompt = f"""你是政大秘書處的資深公關顧問。以下是近期 Threads 平台上與政大相關的 {len(posts)} 篇貼文分析摘要：

{post_summaries}

請根據以上資料，用繁體中文撰寫一份約 150-200 字的綜觀輿情摘要報告，說明：
1. 目前學生最關注的主要議題
2. 整體情緒傾向
3. 是否有潛在危機需要關注
4. 一句話的處置建議

請直接輸出摘要內文，不要加任何標題或格式符號。"""

        client = google_genai.Client()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=google_genai.types.GenerateContentConfig(temperature=0.3)
        )
        summary_result = response.text.strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS overall_summary (
                id INTEGER PRIMARY KEY,
                summary_text TEXT,
                generated_at TEXT,
                post_count INTEGER
            )
        """)
        cursor.execute("DELETE FROM overall_summary")
        cursor.execute(
            "INSERT INTO overall_summary (summary_text, generated_at, post_count) VALUES (?, ?, ?)",
            (summary_result, datetime.now().isoformat(), len(posts))
        )
        conn.commit()
        conn.close()

        return jsonify({"status": "success", "summary": summary_result})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/api/trend_info')
def get_trend_info():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({"status": "error", "message": "Missing URL"})
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT trend, reasoning, gemini_sentiment_score, negative_words, pr_analysis, top_3_complaints
            FROM trend_analysis WHERE post_url = ?
        """, (url,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return jsonify({"status": "not_found"})
        return jsonify({
            "status": "success",
            "trend_info": {
                "trend": row['trend'],
                "reasoning": row['reasoning'],
                "gemini_sentiment_score": row['gemini_sentiment_score'],
                "negative_words": json.loads(row['negative_words']) if row['negative_words'] else [],
                "pr_analysis": row['pr_analysis'],
                "top_3_complaints": json.loads(row['top_3_complaints']) if row['top_3_complaints'] else []
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


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

@app.route('/api/wordcloud', methods=['POST'])
def get_wordcloud():
    body = request.get_json(silent=True) or {}
    urls = body.get('urls', [])
    if not urls:
        return jsonify({'status': 'success', 'words': []})

    try:
        import jieba
        import logging as _logging
        jieba.setLogLevel(_logging.WARNING)

        placeholders = ','.join('?' * len(urls))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT author, content FROM posts WHERE url IN ({placeholders})",
            urls
        )
        rows = cursor.fetchall()
        conn.close()

        stopwords = {
            '的','了','是','在','有','和','也','都','而','及','與','著','或','被','把',
            '讓','給','向','對','從','到','於','但','如','若','雖','因','所','以',
            '我','你','他','她','它','我們','你們','他們','她們','自己','大家',
            '這','那','這個','那個','這些','那些','這樣','那樣','這裡','那裡',
            '什麼','哪裡','誰','怎麼','為什麼','如何','怎樣',
            '今天','昨天','明天','現在','以後','以前','之後','之前','最近','當時',
            '真的','確實','其實','一直','一些','一起','一個','已經','還是','只是',
            '可以','應該','必須','需要','希望','認為','覺得','感覺','感到','知道',
            '看到','說到','沒有','不是','不會','不要','不能','還有','也有','就是',
            '非常','十分','很','太','最','比較','超','特別','相當','真',
            '謝謝','感謝','哈哈','哈','啊','喔','喜歡','開心','好',
            '政大','nccu',
        }

        emoji_re = re.compile(
            '[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF'
            '\U00002600-\U000027BF\U0001F1E0-\U0001F1FF]+',
            flags=re.UNICODE
        )

        word_count = {}
        for row in rows:
            text = row['content'] or ''
            author = row['author'] or ''

            if author:
                text = text.replace(author, ' ')
            text = re.sub(r'\d+\s*(小時|分鐘|秒|天|週|周|個月|年)前?', ' ', text)
            text = re.sub(r'#\S+', ' ', text)
            text = re.sub(r'https?://\S+', ' ', text)
            text = emoji_re.sub(' ', text)
            text = re.sub(r'\d+', ' ', text)
            text = re.sub(r'[^一-鿿㄀-ㄯ˙a-zA-Z\s]', ' ', text)

            for word in jieba.cut(text):
                word = word.strip()
                if len(word) < 2:
                    continue
                if word.lower() in stopwords:
                    continue
                if re.fullmatch(r'[\d\s]+', word):
                    continue
                word_count[word] = word_count.get(word, 0) + 1

        top_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)[:80]
        return jsonify({'status': 'success', 'words': [[w, c] for w, c in top_words]})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


if __name__ == '__main__':
    app.run(debug=True, port=5000)