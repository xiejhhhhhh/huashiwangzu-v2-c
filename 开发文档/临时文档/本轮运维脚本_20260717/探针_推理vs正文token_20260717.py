# -*- coding: utf-8 -*-
"""
推理token vs 正文token 分字段探针
目的:分清 deepseek-v4-flash 的推理消耗和正文消耗是两个字段。
方法(华哥指定):打几个"不开推理/低推理"探针 + 放量(开大max_tokens),
看正文本身要多少、会不会吃满预算;再对比开推理吃多少。
只打几个快探针,不全量跑。分字段打印,不打印全文。
"""
import json, time, os, sys
import urllib.request
import psycopg2

DEEPSEEK_ANTHROPIC_BASE = "https://api.deepseek.com/anthropic/v1/messages"
KEY = "sk-e1e439e3f34649c79dcef71310d81c55"   # 华哥给的deepseek官方,比武用不落库
MODEL = "deepseek-v4-flash"

# 取图谱system(库表最新) + 一个厚样本输入
def 取图谱system():
    conn = psycopg2.connect(host="127.0.0.1", port=5432, dbname="华世王镞_v2",
                            user="postgres", password="123rgE123")
    try:
        cur = conn.cursor()
        cur.execute("SELECT content FROM framework_prompt_templates WHERE name=%s", ("knowledge_entity_extraction",))
        row = cur.fetchone()
        return row[0] if row else ""
    finally:
        conn.close()

def 取厚样本user():
    p = "backend/data/model_bakeoff/samples/图谱_07.json"
    d = json.load(open(p, encoding="utf-8"))
    # 样本结构未知,兜底:找"输入/原始输入/融合正文/input"等字段
    for k in ("原始输入", "输入", "融合正文", "input", "user"):
        if k in d and d[k]:
            v = d[k]
            return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    # 再兜底:整个json里最长的字符串值
    best = ""
    def 扫(x):
        nonlocal best
        if isinstance(x, str):
            if len(x) > len(best): best = x
        elif isinstance(x, dict):
            for vv in x.values(): 扫(vv)
        elif isinstance(x, list):
            for vv in x: 扫(vv)
    扫(d)
    return best

def 打一发(标签, system, user, max_tokens, thinking):
    """thinking: None=不带thinking字段 / dict=带(enabled+budget 或 disabled)"""
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if thinking is not None:
        body["thinking"] = thinking
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        DEEPSEEK_ANTHROPIC_BASE, data=data, method="POST",
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[{标签}] HTTP错误 {e.code}: {e.read().decode('utf-8')[:200]}")
        return
    except Exception as e:
        print(f"[{标签}] 异常: {e}")
        return
    耗时 = round(time.time() - t0, 1)
    # 分字段:content数组里 type=thinking(推理) vs type=text(正文)
    推理字符 = 正文字符 = 0
    正文JSON完整 = False
    正文样本 = ""
    for blk in resp.get("content", []):
        if blk.get("type") == "thinking":
            推理字符 += len(blk.get("thinking", "") or "")
        elif blk.get("type") == "text":
            t = blk.get("text", "") or ""
            正文字符 += len(t)
            正文样本 = t
    # 正文能不能解析成JSON(结构化提取的关键)
    if 正文样本:
        s = 正文样本.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        try:
            json.loads(s); 正文JSON完整 = True
        except Exception:
            正文JSON完整 = False
    usage = resp.get("usage", {})
    stop = resp.get("stop_reason", "")
    print(f"[{标签}] 耗时{耗时}s | stop={stop} | "
          f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} | "
          f"推理字符={推理字符} 正文字符={正文字符} | 正文JSON完整={正文JSON完整} | "
          f"{'⚠吃满被截断' if stop=='max_tokens' else '✓自然停'}")

if __name__ == "__main__":
    sys = 取图谱system()
    user = 取厚样本user()
    print(f"system长度={len(sys)} 厚样本user长度={len(user)}  模型={MODEL}\n" + "="*70)
    # 探针1:不带thinking + 放量(开大),看正文自己要多少、会不会吃满
    打一发("A·无thinking字段·放量16k", sys, user, 16000, None)
    # 探针2:明确关thinking + 放量,对照
    打一发("B·thinking disabled·放量16k", sys, user, 16000, {"type": "disabled"})
    # 探针3:小预算无thinking,看正文4k够不够(结构化JSON通常够)
    打一发("C·无thinking·仅4k", sys, user, 4000, None)
    # 探针4:开thinking(给推理预算),看推理吃多少、正文还剩多少
    打一发("D·thinking enabled·16k(budget8k)", sys, user, 16000, {"type": "enabled", "budget_tokens": 8000})
    print("="*70 + "\n看点:A/B若'自然停'且正文JSON完整→正文本身不吃满,放量不是问题;C看4k够不够;D看开推理是否吃满")

