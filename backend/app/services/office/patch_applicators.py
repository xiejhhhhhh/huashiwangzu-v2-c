import re


def extract_excel_ref(json_path: str) -> tuple[str, str]:
    m = re.match(r"^@excel:(.+?)!([A-Z]+\d+)$", json_path)
    if not m:
        raise ValueError("定位路径格式无效，应为 @excel:Sheet名!A1 格式")
    return m.group(1), m.group(2)


def extract_docx_id(json_path: str) -> str:
    m = re.search(r"id=='([^']+)'", json_path)
    if not m:
        raise ValueError("定位路径格式无效，无法解析段落 ID")
    return m.group(1)


def apply_text_patch(json_content: dict, patch: dict) -> dict:
    path = patch["json_path"]
    content = json_content.get("content", json_content)
    if path == "@text:body":
        content["raw"] = patch["after_content"]
    elif m := re.match(r"^@text:段落(\d+)$", path):
        idx = int(m.group(1))
        paragraphs = content.get("paragraphs", [])
        if idx >= len(paragraphs):
            raise ValueError("定位路径无效：段落索引不存在")
        paragraphs[idx] = patch["after_content"]
        content["paragraphs"] = paragraphs
    else:
        raise ValueError("定位路径格式无效")
    if "content" in json_content:
        json_content["content"] = content
    return json_content


def apply_excel_patch(json_data: dict, patch: dict) -> dict:
    sheet_name, cell_ref = extract_excel_ref(patch["json_path"])
    sheets = json_data.get("sheets", [])
    if not sheets:
        inner = json_data.get("content", {})
        sheets = inner.get("sheets", []) if inner else []
    target = None
    for s in sheets:
        if s.get("name") == sheet_name:
            target = s
            break
    if target is None:
        raise ValueError(f"工作表不存在: {sheet_name}")
    cells = target.setdefault("cells", {})
    cell_key = cell_ref.upper()
    if cell_key in cells and "formula" in cells[cell_key]:
        raise ValueError(f"不允许修改公式单元格: {cell_key}")
    cells[cell_key] = {
        "value": patch["after_content"],
        "type": "number" if patch["after_content"].replace(".", "").replace("-", "").isdigit() else "string",
    }
    return json_data


def apply_docx_patch(json_data: dict, patch: dict) -> dict:
    target_id = extract_docx_id(patch["json_path"])
    content_items = json_data.get("content", [])
    found = False
    for item in content_items:
        if item.get("id") == target_id:
            if item.get("type") != "paragraph":
                raise ValueError(f"目标元素不是段落: {target_id}")
            if len(patch["after_content"]) > 5000:
                raise ValueError("段落内容超过 5000 字符限制")
            item["content"] = patch["after_content"]
            found = True
            break
    if not found:
        raise ValueError(f"未找到目标段落: {target_id}")
    json_data["content"] = content_items
    return json_data


def apply_pptx_patch(json_data: dict, patch: dict) -> dict:
    target_id = extract_docx_id(patch["json_path"])
    slides = json_data.get("content", [])
    found = False
    for slide in slides:
        for elem in slide.get("elements", []):
            if elem.get("id") == target_id:
                if elem.get("type") not in ("textbox", "paragraph"):
                    raise ValueError(f"目标不是文本框: {target_id}")
                if len(patch["after_content"]) > 5000:
                    raise ValueError("文本框内容超过 5000 字符限制")
                elem["content"] = patch["after_content"]
                found = True
                break
        if found:
            break
    if not found:
        raise ValueError(f"未找到目标文本框: {target_id}")
    return json_data
