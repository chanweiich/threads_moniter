import json

with open("threads_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

count = 0
for post in data:
    analysis = post.get("analysis", {})
    if analysis.get("summary") == "分析失敗" or analysis.get("engine") == "Failed" or analysis.get("crisis_score") == 1:
        post["needs_reanalysis"] = True
        count += 1

with open("threads_data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)

print(f"✅ 已標記 {count} 筆失敗貼文準備重新分析")
