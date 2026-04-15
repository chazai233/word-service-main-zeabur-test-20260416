"""
Word Document Generation Service - Precision Formatting Version (v8.0)
修复重点：
1. 消除大标题(1、)的错误缩进。
2. 实现"人员投入"等关键词的【局部加粗】（而非整行）。
3. 严格控制子标题((1))和统计项的首行缩进。
"""

import base64
import io
import json
import re
import os
from copy import deepcopy
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from enum import Enum

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from docx import Document
from docx.shared import Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

app = FastAPI(title="Word Service Precision", version="8.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- 核心排版逻辑 ----------------

def format_run_font(run, size=10.5, bold=False):
    """统一设置字体格式"""
    run.font.name = 'Times New Roman'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    run.font.size = Pt(size)
    run.bold = bold

def process_and_add_line(cell, line_text):
    """
    智能处理每一行的格式：缩进、加粗、分割
    """
    line_text = line_text.strip()
    if not line_text: return

    # 创建新段落（注意：不使用 add_run("\n") 而是 add_paragraph 以便单独控制每一行的缩进）
    # 如果是单元格刚清空后的第一个段落，直接使用，否则新建
    if len(cell.paragraphs) == 1 and not cell.paragraphs[0].text:
        p = cell.paragraphs[0]
    else:
        p = cell.add_paragraph()

    # --- 1. 规则匹配 ---
    
    # 规则A：大标题 (例如 "1、右岸施工营地")
    # 特征：数字开头 + 顿号或点
    if re.match(r"^\d+[、\.]", line_text):
        p.paragraph_format.first_line_indent = Pt(0) # 【关键】强制不缩进
        run = p.add_run(line_text)
        format_run_font(run, bold=True) # 大标题整行加粗
        return

    # 规则B：统计项 (例如 "人员投入：...")
    # 特征：包含特定关键词
    keywords = ["人员投入", "设备投入", "累计工程量"]
    hit_keyword = None
    for kw in keywords:
        if kw in line_text:
            hit_keyword = kw
            break
    
    if hit_keyword:
        p.paragraph_format.first_line_indent = Pt(24) # 【关键】强制缩进 2 字符
        
        # 【局部加粗逻辑】
        # 将文本切分为两部分：关键词前缀(加粗) + 剩余内容(不加粗)
        # 例如 "人员投入：张三" -> "人员投入：" (粗) + " 张三" (细)
        
        # 尝试找到冒号的位置
        split_index = -1
        if "：" in line_text:
            split_index = line_text.index("：") + 1
        elif ":" in line_text:
            split_index = line_text.index(":") + 1
        else:
            # 如果没有冒号，就只加粗关键词本身
            split_index = line_text.index(hit_keyword) + len(hit_keyword)
            
        prefix = line_text[:split_index]
        content = line_text[split_index:]
        
        # 写入前缀（加粗）
        run1 = p.add_run(prefix)
        format_run_font(run1, bold=True)
        
        # 写入内容（正常）
        run2 = p.add_run(content)
        format_run_font(run2, bold=False)
        return

    # 规则C：子标题 / 具体内容 (例如 "(1) 场地精平")
    # 特征：以 (数字) 或 （数字） 开头
    if re.match(r"^[\(（]\d+[\)）]", line_text):
        p.paragraph_format.first_line_indent = Pt(24) # 【关键】强制缩进 2 字符
        run = p.add_run(line_text)
        format_run_font(run, bold=False) # 内容不加粗
        return

    # 规则D：其他普通文本
    # 默认缩进2字符（因为通常是正文延续），或者0？
    # 根据你的截图，如果不符合上述规则，通常是正文描述，建议缩进2字符对齐
    p.paragraph_format.first_line_indent = Pt(24)
    run = p.add_run(line_text)
    format_run_font(run, bold=False)

# ---------------- 辅助函数 ----------------

def find_target_table(doc: Document, index: int) -> Optional[Any]:
    if 0 <= index < len(doc.tables):
        return doc.tables[index]
    return None

def update_table_row(table, row_name: str, today: str, total: str):
    """表格行更新逻辑"""
    if not table.rows: return
    
    name_col = 1
    cols_count = len(table.rows[0].cells)
    today_col = 4 if cols_count > 4 else cols_count - 2
    total_col = 5 if cols_count > 5 else cols_count - 1
    
    for row in table.rows:
        if len(row.cells) <= max(name_col, today_col, total_col): continue
        cell_text = row.cells[name_col].text.strip()
        if row_name in cell_text: 
            # 填入数字时也应用字体规范
            if today and today != "-":
                cell = row.cells[today_col]
                cell.text = ""
                run = cell.paragraphs[0].add_run(str(today))
                format_run_font(run)
            if total and total != "-":
                cell = row.cells[total_col]
                cell.text = ""
                run = cell.paragraphs[0].add_run(str(total))
                format_run_font(run)
            return


DAILY_STATS_HEADERS = ["序号", "施工部位", "施工内容", "日完成量", "备注"]


def normalize_header_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def find_daily_stats_table(doc: Document):
    """
    自动识别“当日施工统计表”：
    需在同一表头行识别到：序号、施工部位、施工内容、日完成量、备注
    """
    for table in doc.tables:
        for row_index, row in enumerate(table.rows):
            header_map: Dict[str, int] = {}
            for col_index, cell in enumerate(row.cells):
                cell_text = normalize_header_text(cell.text)
                for header in DAILY_STATS_HEADERS:
                    if header in cell_text and header not in header_map:
                        header_map[header] = col_index
            if len(header_map) == len(DAILY_STATS_HEADERS):
                return table, row_index, header_map
    return None, None, None


def pick_first_value(item: Dict[str, Any], keys: List[str], default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return default


def normalize_daily_stats_items(raw_items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        row = {
            "seq": pick_first_value(raw, ["seq", "序号", "sn", "serial"], ""),
            "location": pick_first_value(raw, ["location", "施工部位", "area"], ""),
            "content": pick_first_value(raw, ["content", "施工内容", "activity"], ""),
            "quantity": pick_first_value(raw, ["quantity", "日完成量", "完成工程量", "qty"], ""),
            "remarks": pick_first_value(raw, ["remarks", "备注", "remark"], ""),
        }
        # 施工内容为空的数据直接忽略
        if row["content"]:
            normalized.append(row)
    return normalized


def parse_daily_stats_from_content(content: str) -> Optional[List[Dict[str, str]]]:
    """
    兼容：当 content 直接传入 JSON 数组字符串时，自动识别并切换到统计表模式。
    """
    if not isinstance(content, str):
        return None
    text = content.strip()
    if not text.startswith("["):
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    return normalize_daily_stats_items(data)


def set_cell_text_preserve_style(cell, text: str):
    """
    不破坏模板单元格样式地写入文本：
    - 保留首段落（继承对齐、间距、行距）
    - 仅替换首 run 文本（继承字体、字号等）
    """
    text = "" if text is None else str(text)

    while len(cell.paragraphs) > 1:
        extra = cell.paragraphs[-1]
        extra._element.getparent().remove(extra._element)

    if cell.paragraphs:
        p = cell.paragraphs[0]
    else:
        p = cell.add_paragraph()

    if p.runs:
        p.runs[0].text = text
        for run in list(p.runs[1:]):
            p._element.remove(run._element)
    else:
        p.add_run(text)


def clear_vmerge(cell):
    tc_pr = cell._tc.get_or_add_tcPr()
    for vm in tc_pr.findall(qn('w:vMerge')):
        tc_pr.remove(vm)


def set_vmerge(cell, state: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    for vm in tc_pr.findall(qn('w:vMerge')):
        tc_pr.remove(vm)
    vm = OxmlElement('w:vMerge')
    vm.set(qn('w:val'), state)
    tc_pr.append(vm)


def apply_vertical_merge(table, data_start_row: int, items: List[Dict[str, str]], col_index: int, key_fn):
    # 先清理旧合并标记
    for i in range(len(items)):
        clear_vmerge(table.rows[data_start_row + i].cells[col_index])

    group_start = 0
    while group_start < len(items):
        current_key = key_fn(items[group_start])
        group_end = group_start + 1
        while group_end < len(items) and key_fn(items[group_end]) == current_key:
            group_end += 1

        if group_end - group_start > 1:
            top_cell = table.rows[data_start_row + group_start].cells[col_index]
            set_vmerge(top_cell, "restart")
            for idx in range(group_start + 1, group_end):
                c = table.rows[data_start_row + idx].cells[col_index]
                set_cell_text_preserve_style(c, "")
                set_vmerge(c, "continue")

        group_start = group_end


def render_daily_stats_table(doc: Document, items: List[Dict[str, str]]):
    table, header_row_index, header_map = find_daily_stats_table(doc)
    if table is None:
        raise ValueError("未找到“当日施工统计表”（表头需包含：序号/施工部位/施工内容/日完成量/备注）")

    data_start_row = header_row_index + 1
    style_row_index = data_start_row if len(table.rows) > data_start_row else header_row_index
    style_row_xml = deepcopy(table.rows[style_row_index]._tr)

    # 删除旧数据行（含多余空行），只保留表头
    for row_idx in range(len(table.rows) - 1, header_row_index, -1):
        table._tbl.remove(table.rows[row_idx]._tr)

    # 根据入参动态新增数据行
    for _ in items:
        table._tbl.append(deepcopy(style_row_xml))

    seq_col = header_map["序号"]
    location_col = header_map["施工部位"]
    content_col = header_map["施工内容"]
    quantity_col = header_map["日完成量"]
    remarks_col = header_map["备注"]

    # 写入数据（样式继承自模板行）
    for idx, item in enumerate(items):
        row = table.rows[data_start_row + idx]
        set_cell_text_preserve_style(row.cells[seq_col], item["seq"])
        set_cell_text_preserve_style(row.cells[location_col], item["location"])
        set_cell_text_preserve_style(row.cells[content_col], item["content"])
        set_cell_text_preserve_style(row.cells[quantity_col], item["quantity"])
        set_cell_text_preserve_style(row.cells[remarks_col], item["remarks"])

    # 纵向合并：支持“一个序号对应多个施工内容”
    apply_vertical_merge(
        table,
        data_start_row,
        items,
        seq_col,
        key_fn=lambda x: x["seq"],
    )

    # 同步合并施工部位（与序号分组一致时保持模板阅读习惯）
    apply_vertical_merge(
        table,
        data_start_row,
        items,
        location_col,
        key_fn=lambda x: (x["seq"], x["location"]),
    )

# ---------------- 模型定义 ----------------

class FillTemplateRequest(BaseModel):
    template_base64: str
    content: str
    daily_stats: Optional[List[Dict[str, Any]]] = None
    table_index: int = 0
    row_index: int = 4
    col_index: int = 2
    update_date_weather: bool = False
    upload_to_feishu: bool = False
    feishu_token: Optional[str] = None

class UpdateDateWeatherRequest(BaseModel):
    document_base64: str
    feishu_token: Optional[str] = None

class UpdatePersonnelRequest(BaseModel):
    document_base64: str
    personnel_text: str 
    feishu_token: Optional[str] = None

class AppendixTableData(BaseModel):
    table_index: int
    row_name: str
    today_qty: str
    total_qty: str

class UpdateAppendixRequest(BaseModel):
    document_base64: str
    data: List[AppendixTableData]
    feishu_token: Optional[str] = None

# ---------------- API 接口实现 ----------------

@app.post("/fill-template")
async def fill_template(req: FillTemplateRequest):
    try:
        file_bytes = base64.b64decode(req.template_base64)
        doc = Document(io.BytesIO(file_bytes))

        # 模式1：当日施工统计表动态更新（优先）
        use_daily_stats_mode = False
        normalized_items: List[Dict[str, str]] = []
        if req.daily_stats is not None:
            use_daily_stats_mode = True
            normalized_items = normalize_daily_stats_items(req.daily_stats)
        else:
            parsed = parse_daily_stats_from_content(req.content)
            if parsed is not None:
                use_daily_stats_mode = True
                normalized_items = parsed

        if use_daily_stats_mode:
            render_daily_stats_table(doc, normalized_items)
        else:
            # 模式2：兼容旧版单单元格逐行排版
            if doc.tables and len(doc.tables) > req.table_index:
                table = doc.tables[req.table_index]
                if len(table.rows) > req.row_index:
                    cell = table.cell(req.row_index, req.col_index)

                    # 清空单元格
                    cell.text = ""

                    # 逐行处理，精确控制格式
                    lines = req.content.split('\n')
                    for line in lines:
                        process_and_add_line(cell, line)
        
        out = io.BytesIO()
        doc.save(out)
        return {"success": True, "document_base64": base64.b64encode(out.getvalue()).decode()}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}

@app.post("/update-date-weather")
async def update_date_weather(req: UpdateDateWeatherRequest):
    try:
        file_bytes = base64.b64decode(req.document_base64)
        doc = Document(io.BytesIO(file_bytes))
        
        now = datetime.now()
        date_str = f"{now.year}年{now.month}月{now.day}日"
        weather_str = "天气：晴                气温：20℃~30℃"
        
        if doc.tables:
            table = doc.tables[0]
            if len(table.rows) > 0:
                cells = table.rows[0].cells
                if len(cells) > 0: 
                    cells[0].text = ""
                    run = cells[0].paragraphs[0].add_run(date_str)
                    format_run_font(run)
                if len(cells) > 1: 
                    cells[-1].text = ""
                    run = cells[-1].paragraphs[0].add_run(weather_str)
                    format_run_font(run)
        
        out = io.BytesIO()
        doc.save(out)
        return {"success": True, "document_base64": base64.b64encode(out.getvalue()).decode()}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/update-personnel-stats")
async def update_personnel_stats(req: UpdatePersonnelRequest):
    try:
        file_bytes = base64.b64decode(req.document_base64)
        doc = Document(io.BytesIO(file_bytes))
        
        # 统计信息在文末追加，默认不需要特殊缩进，但需要字体规范
        p = doc.add_paragraph()
        run = p.add_run("\n" + req.personnel_text)
        format_run_font(run)
        
        out = io.BytesIO()
        doc.save(out)
        return {"success": True, "document_base64": base64.b64encode(out.getvalue()).decode()}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/update-appendix-tables")
async def update_appendix_tables(req: UpdateAppendixRequest):
    try:
        file_bytes = base64.b64decode(req.document_base64)
        doc = Document(io.BytesIO(file_bytes))
        
        for item in req.data:
            target_table = find_target_table(doc, item.table_index)
            if target_table:
                update_table_row(target_table, item.row_name, item.today_qty, item.total_qty)
        
        out = io.BytesIO()
        doc.save(out)
        return {"success": True, "document_base64": base64.b64encode(out.getvalue()).decode()}
    except Exception as e:
        return {"success": False, "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
