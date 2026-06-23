"""Workbook parser - 1:1 from old 解析_工作簿.php"""
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

SPREAD_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def read_workbook_list(zf: zipfile.ZipFile) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Read workbook.xml to get sheet list and rid mappings"""
    try:
        content = zf.read('xl/workbook.xml')
    except KeyError:
        return ['Sheet1'], {}, {}

    root = ET.fromstring(content)
    all_sheets: list[str] = []
    sheet_map: dict[str, str] = {}
    rid_map: dict[str, str] = {}

    # Read relationships
    try:
        rels_content = zf.read('xl/_rels/workbook.xml.rels')
        rels_root = ET.fromstring(rels_content)
        rel_ns = 'http://schemas.openxmlformats.org/package/2006/relationships'
        for rel in rels_root:
            rid = rel.get('Id', '')
            target = rel.get('Target', '')
            if target:
                target = target.lstrip('/')
                if target.startswith('xl/'):
                    target = target[3:]
                rid_map[rid] = target
    except KeyError:
        pass

    for sheet in root.findall(f'.//{{{SPREAD_NS}}}sheet'):
        name = sheet.get('name', 'Sheet1')
        rid = sheet.get(f'{{{REL_NS}}}id', '')
        all_sheets.append(name)
        sheet_map[name] = rid

    if not all_sheets:
        all_sheets = ['Sheet1']

    return all_sheets, sheet_map, rid_map
