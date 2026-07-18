# -*- coding: utf-8 -*-
"""grok-4.5 批量实体定类(填 type_id + category)。修旧脚本三处病根:
  ①同时写 type_id 外键(旧脚本只写 category,导致 18 类体系挂载=0)
  ②喂证据(df + 真实上下文,旧脚本光看名字判)
  ③用 grok-4.5(本地中转 8317)

高频优先(df 降序,影响召回最大的先定)。噪音红线:第一波只标 type_id=18+落隔离表,不删不改status。
owner=4。幂等断点续跑(WHERE type_id IS NULL)。
用法: cd backend && ./.venv/bin/python ../开发文档/临时文档/本轮定类脚本_20260718/批_grok定类_20260718.py --conc 8 --limit 50 --dry
"""
import asyncio, sys, json, time, argparse, re
sys.path.insert(0, "backend"); sys.path.insert(0, ".")
from app.database import AsyncSessionLocal
from sqlalchemy import text as T

OWNER = 4
PROFILE = "grok-local-gateway"
# type_name → type_id 映射(owner=4,启动时动态加载,不硬编码)
TYPE_MAP: dict[str, int] = {}
TYPES = "成分/原料/功效/品类/产品/品牌/系列/规格/肤质/人物/组织/地点/事件/时间/技术标准/视觉素材/营销内容/噪音"

SYS = (
    "你是护肤品/化妆品行业实体分类专家。给你一个实体名、当前类目、它在库里的文档频率和真实上下文,"
    "判断它最准确的类型。\n"
    f"可选类型(严格选一个,只能是这些):{TYPES}\n"
    "各类型边界:\n"
    "- 成分=活性化学/生物成分(积雪草苷/玻尿酸/烟酰胺)\n- 原料=植物或天然原料及提取物形态\n"
    "- 功效=功能/作用/效果(美白/祛斑/抗衰)\n- 品类=护肤品品类通名,非具体SKU(面霜/精华/原液)\n"
    "- 产品=具体商品/SKU,带品牌或型号(清颜玻尿酸原液)\n- 品牌=品牌/商标(娇薇诗/苏蜜雅)\n"
    "- 系列=产品系列线(青春蕴能系列)\n- 规格=包装/规格/套装\n- 肤质=皮肤类型/适用人群\n"
    "- 人物=人名/角色/客户身份\n- 组织=企业/机构/协会/门店\n- 地点=地址/行政区域/场所\n"
    "- 事件=真实活动/事件\n- 时间=日期/节假日/周期\n- 技术标准=专利/检测报告/安全评估/规范文件/检验编号\n"
    "- 视觉素材=设计/构图/材质/色彩等视觉元素/图片描述\n- 营销内容=营销方案/话术/文案\n"
    "- 噪音=非实体:疑问词/分词碎片/OCR乱码/无意义短语/纯数字/分辨率/条形码/纯英文标语\n"
    "只输出JSON,不解释:{\"类型\":\"选一个\",\"置信\":0.0到1.0}"
)

# 噪音纯规则预筛(不烧 grok):命中即判噪音
_NOISE_PATTERNS = [
    re.compile(r"^\d{8,}$"),                       # 纯长数字(条形码/编号)
    re.compile(r"\d+\s*[×x*]\s*\d+\s*px", re.I),   # 分辨率 5168×3448px
    re.compile(r"^\d+(\.\d+)?\s*(px|dpi|mm|cm|kb|mb)$", re.I),  # 纯尺寸单位
    re.compile(r"^[A-Za-z][A-Za-z\s]{6,}$"),       # 纯英文长串(≥7字,无中文=标语/OCR)
]


def 规则预筛噪音(name: str) -> bool:
    s = (name or "").strip()
    if not s:
        return True
    for p in _NOISE_PATTERNS:
        if p.search(s):
            return True
    return False


async def 查上下文(db, entity_id: int, 条数: int = 2, 每条长: int = 140) -> list[str]:
    """捞该实体在干净文本层的真实原文片段(它到底怎么用)。走 chunk_entities 关联,LIMIT 提前停。"""
    r = await db.execute(T("""
        SELECT left(c.text, :len) FROM kb_chunks c
        JOIN kb_chunk_entities ce ON ce.chunk_id = c.id AND ce.owner_id = :o
        WHERE ce.entity_id = :eid AND c.index_layer = 'base_parse' AND c.text <> ''
        LIMIT :n
    """), {"o": OWNER, "eid": entity_id, "len": 每条长, "n": 条数})
    return [str(t).replace("\n", " ").strip() for (t,) in r.all() if t]


async def 写回(db, eid: int, name: str, cat: str, typ: str, conf: float, df: int, dry: bool):
    """噪音=红线,只标 type_id=18+落隔离表(不删不改status);正向=写 type_id+category(即时收益)。"""
    tid = TYPE_MAP.get(typ)
    if tid is None:
        return
    if dry:
        return
    if typ == "噪音":
        await db.execute(T("UPDATE kb_entity_dictionary SET type_id=:t, updated_at=now() WHERE id=:id AND owner_id=:o"),
                         {"t": tid, "id": eid, "o": OWNER})
        await db.execute(T("""
            INSERT INTO kb_entity_noise_review(owner_id,entity_id,name,old_category,judged_by,block_count)
            VALUES(:o,:id,:n,:oc,'grok-4.5',:df)
            ON CONFLICT(owner_id,entity_id) DO NOTHING
        """), {"o": OWNER, "id": eid, "n": name, "oc": cat, "df": df})
    elif conf < 0.85:
        # 低置信正向归类:错判集中在此段。只写 type_id(救出垃圾桶),不写死 category,
        # 待二次复核。category 留原值仍可召回,不污染。
        await db.execute(T("UPDATE kb_entity_dictionary SET type_id=:t, updated_at=now() WHERE id=:id AND owner_id=:o"),
                         {"t": tid, "id": eid, "o": OWNER})
    else:
        # 高置信正向:即时收益,写 type_id+category
        await db.execute(T("""
            UPDATE kb_entity_dictionary SET type_id=:t, category=:c, updated_at=now()
            WHERE id=:id AND owner_id=:o
        """), {"t": tid, "c": typ, "id": eid, "o": OWNER})
    await db.commit()


async def 定类一个(sem, eid, name, cat, df, dry, stats):
    async with sem:
        # 规则预筛噪音(不烧 grok)
        if 规则预筛噪音(name):
            async with AsyncSessionLocal() as wdb:
                await 写回(wdb, eid, name, cat, "噪音", 1.0, df, dry)
            stats["规则噪音"] += 1
            stats["结果"][eid] = "噪音(规则)"
            return
        async with AsyncSessionLocal() as rdb:
            ctxs = await 查上下文(rdb, eid)
        证据 = f"实体名:{name}\n当前类目:{cat}\n文档频率:{df}篇"
        if ctxs:
            证据 += "\n真实上下文:\n" + "\n".join(f"  - {c}" for c in ctxs)
        证据 += "\n最准确的类型是?"
        try:
            from app.gateway.router import gateway_router
            res = await asyncio.wait_for(
                gateway_router.chat([{"role": "system", "content": SYS},
                                     {"role": "user", "content": 证据}], profile_key=PROFILE),
                timeout=90,
            )
            text = res.get("content", "") or ""
            m = re.search(r'\{.*\}', text, re.S)
            if not m:
                stats["解析失败"] += 1
                return
            obj = json.loads(m.group(0))
            typ = str(obj.get("类型", "")).strip()
            conf = float(obj.get("置信", 0) or 0)
            # grok 可能返回复合分类"成分/原料",取第一个合法的
            if typ not in TYPE_MAP:
                for part in re.split(r"[/、,，\s]+", typ):
                    if part in TYPE_MAP:
                        typ = part
                        break
            if typ not in TYPE_MAP:
                stats["非法类型"] += 1
                return
            async with AsyncSessionLocal() as wdb:
                await 写回(wdb, eid, name, cat, typ, conf, df, dry)
            stats["grok定类"] += 1
            stats["结果"][eid] = f"{name}→{typ}({conf})"
            stats["分布"][typ] = stats["分布"].get(typ, 0) + 1
        except Exception as e:
            stats["异常"] += 1
            stats["末次异常"] = str(e)[:120]


async def main(conc, limit, dry):
    global TYPE_MAP
    async with AsyncSessionLocal() as db:
        r = await db.execute(T("SELECT type_name, id FROM kb_semantic_types WHERE owner_id=:o"), {"o": OWNER})
        TYPE_MAP = {str(n): int(i) for n, i in r.all()}
        print(f"type_map 加载: {len(TYPE_MAP)} 类", flush=True)
        # 待定类:type_id 为空,candidate/confirmed,高频优先(df 降序)
        r = await db.execute(T("""
            WITH ef AS (SELECT entity_id, count(DISTINCT document_id) df FROM kb_chunk_entities WHERE owner_id=:o GROUP BY entity_id)
            SELECT ed.id, ed.name, ed.category, COALESCE(ef.df,0) df
            FROM kb_entity_dictionary ed LEFT JOIN ef ON ef.entity_id=ed.id
            WHERE ed.owner_id=:o AND ed.status IN ('candidate','confirmed')
              AND ed.type_id IS NULL AND ed.name <> ''
            ORDER BY COALESCE(ef.df,0) DESC, ed.id LIMIT :lim
        """), {"o": OWNER, "lim": limit})
        ents = [(int(i), n, c, int(d)) for i, n, c, d in r.all()]
    print(f"待定类:{len(ents)} 并发={conc} {'[DRY-RUN 只判不写]' if dry else '[写库]'}", flush=True)
    stats = {"grok定类": 0, "规则噪音": 0, "解析失败": 0, "非法类型": 0, "异常": 0, "分布": {}, "结果": {}, "末次异常": ""}
    sem = asyncio.Semaphore(conc)
    t0 = time.time()
    await asyncio.gather(*(定类一个(sem, e, n, c, d, dry, stats) for e, n, c, d in ents))
    dt = time.time() - t0
    print(f"\n完成 用时{dt:.0f}s ({len(ents)/max(dt,1):.1f}个/秒)", flush=True)
    print(f"grok定类={stats['grok定类']} 规则噪音={stats['规则噪音']} 解析失败={stats['解析失败']} 非法类型={stats['非法类型']} 异常={stats['异常']}", flush=True)
    if stats["末次异常"]:
        print(f"末次异常: {stats['末次异常']}", flush=True)
    print("类型分布:", sorted(stats["分布"].items(), key=lambda x: -x[1]), flush=True)
    if dry:
        print("\n=== DRY-RUN 抽样(供人工核精度) ===", flush=True)
        for eid, txt in list(stats["结果"].items())[:60]:
            print(f"  {txt}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--conc", type=int, default=10)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.conc, a.limit, a.dry))
