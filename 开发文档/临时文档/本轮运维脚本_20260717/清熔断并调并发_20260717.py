"""阶段4:清熔断 + 并发调到30 + 让worker重跑剩余LLM三阶段。
- 清 task_worker.json 的 model_auto_pause(置 enabled=false,清空 paused_stages)+ 顶层 paused_stages/paused_task_types/paused_lanes(确保门控开)
- 清 knowledge_model_rate_limit_state.json 的陈旧计数(llm count=30 是13:48的,窗口300s早过期)
- 并发30:models.json 的 pipeline_concurrency.model_call_global=30(直接限并发模型调用,防429);
  task_worker.json 的 provider_limits.knowledge_llm 与 lane_limits.llm_analysis 适度放到6(LLM任务并发,graph扇出仅6→约36≈30)
所有改动前先备份原文件到 data/backup/。

用法: cd backend && .venv/bin/python 清熔断并调并发_20260717.py
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

CFG = Path("data/config")
BK = Path("data/backup")
BK.mkdir(parents=True, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _备份(p: Path):
    if p.exists():
        dst = BK / f"{p.name}.bak_阶段4_{ts}"
        shutil.copy2(p, dst)
        print(f"[备份] {p.name} -> {dst}")


def _原子写(p: Path, data: dict):
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def 改task_worker():
    p = CFG / "task_worker.json"
    _备份(p)
    d = json.loads(p.read_text(encoding="utf-8"))

    # 1) 清熔断门控(顶层)
    d["paused_task_types"] = []
    d["paused_stages"] = {}
    d["paused_lanes"] = {}

    # 2) 清陈旧 model_auto_pause 状态标记
    d["model_auto_pause"] = {
        "enabled": False,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "cleared_reason": "阶段4人工清熔断:13:48的429窗口(300s)早已过期,恢复LLM三阶段补跑",
    }

    # 3) 并发30:LLM任务并发放到6(graph扇出仅6→约36≈30;fusion靠model_call_global压)
    disp = d.setdefault("dispatcher", {})
    disp.setdefault("provider_limits", {})["knowledge_llm"] = 6
    disp.setdefault("lane_limits", {})["llm_analysis"] = 6

    _原子写(p, d)
    print("[写入] task_worker.json: paused全清, model_auto_pause禁用, knowledge_llm=6, llm_analysis=6")


def 改models():
    p = CFG / "models.json"
    _备份(p)
    d = json.loads(p.read_text(encoding="utf-8"))
    mr = d.setdefault("module_routing", {}).setdefault("knowledge", {})
    pc = mr.setdefault("pipeline_concurrency", {})
    旧 = pc.get("model_call_global")
    pc["model_call_global"] = 30  # ★华哥要的"并发30":全局并发模型调用上限(每进程),直接防429
    _原子写(p, d)
    print(f"[写入] models.json: pipeline_concurrency.model_call_global {旧} -> 30")


def 清rate_state():
    p = CFG / "knowledge_model_rate_limit_state.json"
    _备份(p)
    # 清空计数,让阈值判定从0重新开始
    _原子写(p, {"groups": {}, "cleared_at": datetime.now(timezone.utc).isoformat()})
    print("[写入] knowledge_model_rate_limit_state.json: 计数清零")


if __name__ == "__main__":
    改task_worker()
    改models()
    清rate_state()
    print("\n[完成] 熔断已清、并发已设。worker热加载配置(dispatcher每1-8秒读一次)后自动按新并发捡pending任务。")
