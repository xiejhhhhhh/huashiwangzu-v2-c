import time

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEvaluation
from app.services.knowledge.evaluation.dataset import load_golden_dataset
from app.services.knowledge.evaluation.scoring import score_question
from app.services.knowledge.retrieval.hybrid import hybrid_search


async def overview(db: AsyncSession) -> dict:
    total = await db.scalar(select(func.count()).select_from(KnowledgeEvaluation)) or 0
    latest = await _latest(db)
    return {"totalRuns": total, "latest": serialize(latest) if latest else None}


async def history(db: AsyncSession, limit: int = 20) -> list[dict]:
    result = await db.execute(
        select(KnowledgeEvaluation).order_by(desc(KnowledgeEvaluation.id)).limit(limit)
    )
    return [serialize(record) for record in result.scalars().all()]


async def detail(db: AsyncSession, record_id: int) -> dict | None:
    record = await db.get(KnowledgeEvaluation, record_id)
    return serialize(record, include_details=True) if record else None


async def run_evaluation(db: AsyncSession, top_k: int = 10) -> dict:
    dataset = load_golden_dataset()
    details = []
    for question in dataset["questions"]:
        started_at = time.perf_counter()
        result = await hybrid_search(db, question.get("问题", ""), top_k=top_k)
        details.append(score_question(question, result, started_at))
    record = _build_record(dataset, details)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return serialize(record, include_details=True)


async def _latest(db: AsyncSession) -> KnowledgeEvaluation | None:
    result = await db.execute(select(KnowledgeEvaluation).order_by(desc(KnowledgeEvaluation.id)).limit(1))
    return result.scalar_one_or_none()


def _build_record(dataset: dict, details: list[dict]) -> KnowledgeEvaluation:
    total = len(details)
    passed = sum(1 for item in details if item["passed"])
    hallucinated = sum(1 for item in details if item["forbiddenHits"])
    avg_score = sum(item["score"] for item in details) / total if total else 0.0
    avg_latency = sum(item["latencyMs"] for item in details) / total if total else 0
    summary = {"categories": _category_summary(details)}
    return KnowledgeEvaluation(
        dataset_name=dataset["name"], dataset_version=dataset["version"],
        question_count=total, passed_count=passed, average_score=round(avg_score, 2),
        recall_rate=round(passed / total, 4) if total else 0,
        hallucination_rate=round(hallucinated / total, 4) if total else 0,
        average_latency_ms=int(avg_latency), summary=summary, details={"items": details},
    )


def _category_summary(details: list[dict]) -> dict:
    summary: dict[str, dict] = {}
    for item in details:
        row = summary.setdefault(item["category"], {"total": 0, "passed": 0})
        row["total"] += 1
        row["passed"] += 1 if item["passed"] else 0
    return summary


def serialize(record: KnowledgeEvaluation, include_details: bool = False) -> dict:
    data = {
        "id": record.id, "datasetName": record.dataset_name, "datasetVersion": record.dataset_version,
        "status": record.status, "questionCount": record.question_count, "passedCount": record.passed_count,
        "averageScore": record.average_score, "recallRate": record.recall_rate,
        "hallucinationRate": record.hallucination_rate, "averageLatencyMs": record.average_latency_ms,
        "summary": record.summary or {}, "error": record.error,
        "createdAt": record.created_at.isoformat() if record.created_at else None,
    }
    if include_details:
        data["details"] = (record.details or {}).get("items", [])
    return data
