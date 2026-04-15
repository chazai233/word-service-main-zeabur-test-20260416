# Word Document Generation Service

FastAPI 服务，用于对 Word 模板进行填充和更新。

## 运行

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API 端点

- `POST /fill-template` - 按行排版填充模板指定单元格
- `POST /update-date-weather` - 更新文档日期与天气栏
- `POST /update-personnel-stats` - 在文末追加人员统计信息
- `POST /update-appendix-tables` - 按行名更新附表“当日/累计”数量
- `GET /docs` - Swagger API 文档

## 当日施工统计表（推荐调用方式）

为避免中文在调用链路中变成 `?`，建议将 JSON 列表按 UTF-8 编码后传入 `daily_stats_base64`：

```python
import json
import base64
import requests

daily_stats = [
    {"seq": "1", "location": "右岸道路", "content": "R2道路K2+300-K2+500段路基开挖、平整及碾压", "quantity": "1项", "remarks": ""},
    {"seq": "1", "location": "右岸道路", "content": "K2+040-K2+070挡墙墙背回填", "quantity": "1140m³", "remarks": ""}
]

payload = {
    "template_base64": "<docx模板文件base64>",
    "content": "",
    "daily_stats_base64": base64.b64encode(
        json.dumps(daily_stats, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")
}

resp = requests.post("http://localhost:8000/fill-template", json=payload, timeout=120)
print(resp.json())
```
