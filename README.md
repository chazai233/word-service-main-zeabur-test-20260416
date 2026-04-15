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
