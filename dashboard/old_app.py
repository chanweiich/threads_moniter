from flask import Flask, render_template, jsonify, request
import json
import os
import subprocess
import threading
from dotenv import load_dotenv
from datetime import datetime, timedelta
import re

# 讀取上一層目錄 (專案根目錄) 的 .env 檔案
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)

def parse_threads_time(time_str, content_str=""):
    now = datetime.now()
    
    # 1. 優先提取原文內容 (content) 中的絕對日期 (YYYY-MM-DD 或 YYYY/MM/DD)
    if content_str:
        match_content = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', content_str)
        if match_content:
            try:
                return datetime(int(match_content.group(1)), int(match_content.group(2)), int(match_content.group(3)))
            except:
                pass
                
    # 若原文中沒日期，我們再處理 `time_str` (如果還是空的，代表徹底失敗，回傳 None)
    if not time_str:
        return None
        
    time_str = time_str.strip().lower()
    
    # 支援 "X天"
    match = re.search(r'^(\d+)\s*天', time_str)
    if match:
        return now - timedelta(days=int(match.group(1)))
        
    # 支援 "Xh" 或 "X小時"
    match = re.search(r'^(\d+)\s*(h|小時)', time_str)
    if match:
        return now - timedelta(hours=int(match.group(1)))
        
    # 支援 "Xm" 或 "X分鐘"
    match = re.search(r'^(\d+)\s*(m|分鐘)', time_str)
    if match:
        return now - timedelta(minutes=int(match.group(1)))
        
    # 支援 "Xs" 或 "X秒"
    match = re.search(r'^(\d+)\s*(s|秒)', time_str)
    if match:
        return now - timedelta(seconds=int(match.group(1)))
        
    # 支援 "Xw" 或 "X週"
    match = re.search(r'^(\d+)\s*(w|週)', time_str)
    if match:
        return now - timedelta(weeks=int(match.group(1)))
        
    # 支援時間欄位中的 YYYY-MM-DD 或是 "YYYY/MM/DD
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', time_str)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except:
            pass
            
    # 支援 Threads 其他絕對時間表示 (如 "12/02/25" 月/日/年 或 "03/19")
    try:
        parts = time_str.split('/')
        if len(parts) == 3:
            return datetime.strptime(time_str, "%m/%d/%y")
        elif len(parts) == 2:
            dt = datetime.strptime(time_str, "%m/%d")
            return dt.replace(year=now.year)
    except:
        pass
        
    return None

def run_scraper_and_analyzer():
    try:
        print("啟動小規模爬蟲...")
        subprocess.run(["python3", "scrape_threads.py"], check=True, cwd=os.path.join(os.path.dirname(__file__), ".."))
        print("啟動分析模組...")
        subprocess.run(["python3", "analyze_crisis.py"], check=True, cwd=os.path.join(os.path.dirname(__file__), ".."))
        print("啟動輿情追蹤模組...")
        subprocess.run(["python3", "track_trends.py"], check=True, cwd=os.path.join(os.path.dirname(__file__), ".."))
        print("任務完成")
    except Exception as e:
        print(f"執行出錯: {e}")

@app.route('/')
def index():
    report_path = os.path.join(os.path.dirname(__file__), "..", "final_crisis_report.json")
    trend_path = os.path.join(os.path.dirname(__file__), "..", "trend_data.json")
    
    data = []
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
    trend_data = {}
    if os.path.exists(trend_path):
        with open(trend_path, "r", encoding="utf-8") as f:
            trend_data = json.load(f)
            
    # 【執行要求：紀錄成功提取的日期數量】
    extracted_count = 0
            
    # 為每筆資料增加 timestamp，並將顯示時間統一化為 YYYY/MM/DD
    for item in data:
        dt = parse_threads_time(item.get('time', ''), item.get('content', ''))
        if dt:
            item['timestamp'] = dt.timestamp()
            item['time_display'] = dt.strftime('%Y/%m/%d')
            extracted_count += 1
        else:
            item['timestamp'] = 0.0
            item['time_display'] = '日期不明'
            
        # 【新增】將 trend_data 放進去
        item['trend_info'] = trend_data.get(item.get('url'))
            
    # 在終端機輸出提取結果
    print(f"\\n✅ 【日誌】已成功從內容提取 {extracted_count} 筆日期！\\n")
            
    # 【雙重排序邏輯】
    # 第一層：危機指數 (10 -> 1) 降序
    # 第二層：發文時間 (timestamp) 降序
    data.sort(
        key=lambda x: (
            x.get('analysis', {}).get('crisis_score', 0), 
            x.get('timestamp', 0.0)
        ), 
        reverse=True
    )
    
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
            
    # 【新增】載入並轉換時序資料
    ts_path = os.path.join(os.path.dirname(__file__), "..", "time_series_data.json")
    time_series = []
    if os.path.exists(ts_path):
        with open(ts_path, "r", encoding="utf-8") as f:
            time_series = json.load(f)
            
    import collections
    ts_by_url = collections.defaultdict(list)
    for row in time_series:
        ts_by_url[row['url']].append(row)
        
    api_status = {"gemini": "Unknown", "groq": "Unknown", "last_updated": ""}
    api_status_path = os.path.join(os.path.dirname(__file__), "api_status.json")
    if os.path.exists(api_status_path):
        try:
            with open(api_status_path, "r", encoding="utf-8") as f:
                api_status = json.load(f)
        except: pass
            
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
    from flask import request
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({"status": "error", "queries": []})
        
    queries = get_search_queries(keyword)
    return jsonify({"status": "success", "queries": queries})

@app.route('/api/search', methods=['GET'])
def search_posts():
    from flask import request
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({"status": "error", "message": "請提供搜尋關鍵字"})
        
    search_queries = get_search_queries(keyword)
    
    new_count = 0
    updated_count = 0
    
    try:
        import subprocess
        os.chdir("..")
        venv_python = os.path.abspath(os.path.join(os.getcwd(), ".venv", "bin", "python3"))
        if not os.path.exists(venv_python):
            venv_python = "python3"
            
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
    
    try:
        with open("../threads_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
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
            
    if not filtered_posts:
        return jsonify({"status": "success", "posts": [], "wordcloud": [], "chart_data": None})
        
    import jieba
    from collections import Counter
    import re
    
    text_clean = re.sub(r'[^\w\s]', '', all_text_for_cloud)
    words = jieba.lcut(text_clean)
    
    stopwords = set(["的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一個", "上", "也", "很", "到", "說", "要", "去", "你", "會", "著", "沒有", "看", "好", "自己", "這", "那", "呢", "嗎", "啊", "吧", "呀", "惹", "這", "與", "及", "等", "但", "因為", "所以", "如果", "雖然", "而且", "可以", "我們", "他們", "什麼", "怎麼", "還是", "就是", "覺得", "知道", "政大", "然後", "感覺", "不少", "給到"])
    
    def is_valid_word(w):
        if len(w) <= 1: return False
        if w in stopwords: return False
        if re.search(r'\d', w): return False # Drop words with digits (17, 60, Day2)
        if re.match(r'^[A-Za-z_]+$', w): return False # Drop pure english usernames or noise
        return True
        
    filtered_words = [w for w in words if is_valid_word(w)]
    raw_counts = Counter(filtered_words)
    
    # 黑話加權
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
    # 啟動背景執行序來處理爬取與分析，避免前端長時間等待 TimeOut
    thread = threading.Thread(target=run_scraper_and_analyzer)
    thread.start()
    return jsonify({"status": "success", "message": "已在背景啟動小規模爬取與分析任務，請稍後重整頁面查看結果。"})

@app.route('/api/add_manual_post', methods=['POST'])
def add_manual_post():
    from flask import request, jsonify
    data = request.json
    raw_url = data.get('url', '').strip()
    
    url = raw_url.split('?')[0].replace('threads.com', 'threads.net').rstrip('/')
    
    if "threads.net" not in url or "@" not in url or "post" not in url:
        return jsonify({"status": "error", "message": "無效的 Threads 網址，請確認連結包含 threads 域名與文章標識。"})
        
    try:
        # 切換到上一層目錄執行
        import subprocess
        os.chdir("..")
        venv_python = os.path.abspath(os.path.join(os.getcwd(), ".venv", "bin", "python3"))
        if not os.path.exists(venv_python):
            venv_python = "python3"
            
        print(f"手動執行單筆抓取 (使用直譯器: {venv_python}): {url}")
        
        # 執行 manual_add.py，並取得輸出
        result = subprocess.run([venv_python, "manual_add.py", url], capture_output=True, text=True)
        os.chdir("dashboard")
        
        output = result.stdout
        
        # 找尋 JSON 輸出
        if "---OUTPUT_START---" in output and "---OUTPUT_END---" in output:
            json_str = output.split("---OUTPUT_START---")[1].split("---OUTPUT_END---")[0].strip()
            parsed = json.loads(json_str)
            if parsed.get("status") == "success":
                return jsonify(parsed)
                
        return jsonify({"status": "error", "message": "無法抓取或解析該網址，請確認連結權限或格式。\\n" + output[-200:]})
    except Exception as e:
        if os.getcwd().endswith('threads_monitor'):
            os.chdir("dashboard")
        return jsonify({"status": "error", "message": f"伺服器錯誤: {str(e)}"})

@app.route('/api/delete_post', methods=['POST'])
def delete_post():
    from flask import request
    data = request.json
    url_to_delete = data.get('url')
    if not url_to_delete:
        return jsonify({"status": "error", "message": "Missing URL"}), 400
        
    def remove_from_json(filename):
        filepath = os.path.join(os.path.dirname(__file__), "..", filename)
        if not os.path.exists(filepath):
            return 0
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                items = json.load(f)
            original_len = len(items)
            items = [item for item in items if item.get('url') != url_to_delete]
            if len(items) < original_len:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(items, f, ensure_ascii=False, indent=4)
                return original_len - len(items)
        except Exception as e:
            print(f"Error modifying {filename}: {e}")
        return 0

    c1 = remove_from_json("threads_data.json")
    c2 = remove_from_json("final_crisis_report.json")
    c3 = remove_from_json("crisis_watchlist.json")
    
    return jsonify({
        "status": "success", 
        "message": f"已成功移除資料庫中的貼文。"
    })

if __name__ == '__main__':
    # Flask 開發伺服器
    app.run(debug=True, port=5000)
