import io
import json
import base64
import requests
from docx import Document

BASE_URL = "http://localhost:8000"

# 构造一个最小可测模板（含“当日施工统计表”表头 + 1条样式行）
doc = Document()
table = doc.add_table(rows=2, cols=5)
headers = ["序号", "施工部位", "施工内容", "日完成量", "备注"]
for i, h in enumerate(headers):
    table.rows[0].cells[i].text = h
table.rows[1].cells[0].text = "1"
table.rows[1].cells[1].text = "右岸道路"
table.rows[1].cells[2].text = "模板样式行"
table.rows[1].cells[3].text = "1项"
table.rows[1].cells[4].text = ""

buf = io.BytesIO()
doc.save(buf)

daily_stats = [
    {
        "seq": "1",
        "location": "右岸道路",
        "content": "R2道路K2+300-K2+500段路基开挖、平整及碾压",
        "quantity": "1项",
        "remarks": ""
    },
    {
        "seq": "1",
        "location": "右岸道路",
        "content": "K2+040-K2+070挡墙墙背回填",
        "quantity": "1140m³",
        "remarks": ""
    },
    {
        "seq": "2",
        "location": "右岸砂石骨料加工系统",
        "content": "D型衡重式挡墙第7仓混凝土浇筑",
        "quantity": "92m³",
        "remarks": ""
    }
]

payload = {
    "template_base64": base64.b64encode(buf.getvalue()).decode("utf-8"),
    "content": "",
    "daily_stats_base64": base64.b64encode(
        json.dumps(daily_stats, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")
}

r = requests.post(f"{BASE_URL}/fill-template", json=payload, timeout=120)
result = r.json()

if result.get("success"):
    with open("test_fill_template.docx", "wb") as f:
        f.write(base64.b64decode(result["document_base64"]))
    print("填充成功! 文档已保存: test_fill_template.docx")
else:
    print("错误:", result)
