import requests
import json
import base64
from pathlib import Path

BASE_URL = "http://localhost:8000"
TEMPLATE_PATH = Path(r"D:\工作\模板-施工日报.docx")

# 读取测试数据
with open("test_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

if not TEMPLATE_PATH.exists():
    raise FileNotFoundError(f"模板不存在: {TEMPLATE_PATH}")

daily_stats_json = json.dumps(data["daily_stats"], ensure_ascii=False)

payload = {
    "template_base64": base64.b64encode(TEMPLATE_PATH.read_bytes()).decode("utf-8"),
    "content": "",
    # 推荐：UTF-8 JSON -> base64，避免中文链路乱码
    "daily_stats_base64": base64.b64encode(daily_stats_json.encode("utf-8")).decode("utf-8"),
}

r = requests.post(f"{BASE_URL}/fill-template", json=payload, timeout=120)
result = r.json()

if result.get("success"):
    out_file = Path("output_daily.docx")
    out_file.write_bytes(base64.b64decode(result["document_base64"]))
    print("生成成功!")
    print(f"输出文件: {out_file.resolve()}")
else:
    print("错误:", result)
