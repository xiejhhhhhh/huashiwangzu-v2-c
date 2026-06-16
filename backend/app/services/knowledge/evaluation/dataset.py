import json
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parents[5] / "开发文档" / "08_测试验收" / "黄金问题集.json"


def load_golden_dataset() -> dict:
    with open(DATASET_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)
    meta = data.get("元信息") or {}
    questions = data.get("问题列表") or []
    return {
        "name": meta.get("评测集名称", "knowledge golden dataset"),
        "version": meta.get("版本", ""),
        "questions": questions,
    }
