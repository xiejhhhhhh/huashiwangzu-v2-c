# -*- coding: utf-8 -*-
"""词层分词器 —— 替代 cognitive_index_service 里那行贪婪正则。

病根:旧 `[一-鿿]{2,}` 把连续中文整句抓成一坨,词层塞满句子。
解药链:
  ① jieba + 业务词典(kb_entity_dictionary + 通名表)→ 专名不碎
  ② 英文/编号串分词前保护(HUA SHI WANG ZU / 报告编号不切碎)
  ③ 双向剥离:剥头部噪音前缀 + 剥尾部通名后缀
  ④ 尾部通名 → 主体直接定类目(0 LLM)
  ⑤ 剥完仍带谓语/超长 → 判句子碎片,踢出词层
  ⑥ 剥完拿不准的纯专名 → 标 pending,留给 LLM 兜底(可选)

对外只暴露三个函数:
  载入业务词典(词列表)  —— 进程内一次性把业务词灌进 jieba
  切词带类目(text)       —— 富提取,返回 [{主体,通名,类目,状态}],给语料/derive 用
  提取词(text, limit)     —— 简易列表,返回主体字符串,兼容旧 extract_terms 签名
"""
from __future__ import annotations

import re
from collections import Counter

# ── 头部噪音前缀(剥头) ──
_头部噪音 = [
    "送检单位及生产企业均为", "送检单位为", "生产企业为", "核心对象为", "印章文字包含",
    "文档还关注客户对", "页面底部可见", "页面底部有", "页面带有", "本页为一张",
    "本页为", "该页为", "本文档为", "本文件为", "并推荐", "包括", "主打", "少量",
    "盖有", "并叠加", "详见", "适合", "现行有效的", "文档重点强调", "日出具的",
    "月出具的", "样品出具的", "并加盖", "营销海报和", "备注和", "包含负责", "还关注客户对",
]
_头部噪音.sort(key=len, reverse=True)  # 长的先剥

# ── 尾部通名表:(类目, 是否剥主体) ──
# 剥离型(剥掉通名留主体):机构/岗位——"广州娇宇化妆品有限公司"主体是企业名"广州娇宇化妆品"
# 保留型(只定类,不剥):成分/产品/报告/标准——"沙棘果提取物"是规范全称,剥成"沙棘果"会撞词、丢信息
_通名类目 = {
    # 机构(剥主体)
    "有限公司": ("机构", True), "股份有限公司": ("机构", True), "检测中心": ("机构", True),
    "检验检测中心": ("机构", True), "研究所": ("机构", True), "研究院": ("机构", True),
    "检测服务有限公司": ("机构", True), "检验检测有限公司": ("机构", True),
    "科技有限公司": ("机构", True), "生物科技有限公司": ("机构", True), "门店": ("机构", True), "分公司": ("机构", True),
    # 人名/岗位(剥主体)
    "老师": ("人名", True), "经理": ("部门岗位", True), "总监": ("部门岗位", True), "主管": ("部门岗位", True),
    "专家": ("部门岗位", True), "顾问": ("部门岗位", True), "总经理": ("部门岗位", True),
    # 产品(保留全称,只定类)
    "精华液": ("产品", False), "面霜": ("产品", False), "面膜": ("产品", False), "洁面乳": ("产品", False),
    "喷雾": ("产品", False), "套盒": ("产品", False), "套装": ("产品", False), "礼盒": ("产品", False),
    "冻干粉": ("产品", False), "身体乳": ("产品", False), "乳液": ("产品", False), "爽肤水": ("产品", False),
    "精华水": ("产品", False), "眼霜": ("产品", False),
    # 成分(保留全称,只定类)
    "提取物": ("成分", False), "发酵提取物": ("成分", False), "果提取物": ("成分", False),
    "根提取物": ("成分", False), "叶提取物": ("成分", False),
    # 证书报告(保留全称)
    "检验报告": ("检验报告", False), "安全性检验报告": ("检验报告", False), "检测报告": ("检验报告", False),
    "质检证明": ("质检证书", False), "合规证明": ("质检证书", False), "质量证明": ("质检证书", False),
    "检验检测专用章": ("专用章", False), "专用章": ("专用章", False),
    # 标准法规(保留全称)
    "技术规范": ("标准法规", False), "安全技术规范": ("标准法规", False), "管理规范": ("标准法规", False),
    "服务规范": ("标准法规", False), "操作规范": ("标准法规", False), "行为规范": ("标准法规", False),
}
_通名列表 = sorted(_通名类目.keys(), key=len, reverse=True)

# ── 谓语/虚词(剥完还含 = 句子碎片,踢) ──
_谓语词 = re.compile(
    r"(不会|不能|可以|需要|应该|如果|由于|因为|所以|因此|把自己|说出来|奉献|展开|增加|造成|"
    r"能不能|是否|通常|已经|正在|出具|盖有|均为|包含|关注|强调|适合作为|更适合|凭着|通过|基于|而应|就会|就是)"
)

# ── OCR/技术噪音黑名单(整体丢弃) ──
_噪音黑名单 = re.compile(
    r"^(主色为|图片格式为|尺寸为|分辨率为|色彩模式|边缘密度约|平均亮度约|占比约|整体视觉轮廓为|"
    r"本页以下空白|页脚|水印|像素|以下空白)$"
)
_纯色值 = re.compile(r"^#?[0-9a-fA-F]{6}$")
_技术碎片 = re.compile(r"^(RGB|RGBA|PNG|JPEG|JPG|DPI|BBB|EI|NE|CS)$", re.I)

# ── 英文/编号串保护:分词前挖出整体保护,jieba 只切中文,最后放回 ──
_保护_RE = re.compile(
    r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+){2,}"        # 编号:KC-JL-GY-JS-308-2022
    r"|[A-Za-z]{2,}(?:\s+[A-Za-z]{2,}){1,}"        # 英文词组:HUA SHI WANG ZU
    r"|[A-Z]{2,}\d{3,}[-A-Za-z0-9]*"               # 报告号:CH2407-039N
)

_jieba = None
_词典已载 = False


def _取jieba():
    """懒加载 jieba,通名后缀先灌进去(业务词典由 载入业务词典 补)。"""
    global _jieba
    if _jieba is None:
        import jieba
        jieba.setLogLevel(20)
        for suf in _通名列表:
            jieba.add_word(suf, freq=5000)
        _jieba = jieba
    return _jieba


def 载入业务词典(词列表) -> int:
    """把库里的实体名灌进 jieba,专名优先按整词切。进程内调一次即可。"""
    global _词典已载
    jieba = _取jieba()
    n = 0
    for w in 词列表:
        w = (w or "").strip()
        if 2 <= len(w) <= 12:
            jieba.add_word(w, freq=10000)
            n += 1
    _词典已载 = True
    return n


def _norm(s):
    return re.sub(r"\s+", "", str(s or "").strip())


def _剥头(w):
    changed = True
    while changed:
        changed = False
        for p in _头部噪音:
            if w.startswith(p) and len(w) > len(p) + 1:
                w = w[len(p):]
                changed = True
                break
    return w


def _剥尾定类(w):
    """返回 (主体, 通名, 类目)。
    剥离型通名(机构/岗位):主体=企业名,剥掉通名(广州娇宇化妆品有限公司→广州娇宇化妆品)。
    保留型通名(成分/产品/报告/标准):全称本身就是规范实体名,通名只定类不剥
    (沙棘果提取物 保留全称,别剥成'沙棘果';否则和'沙棘果油'撞一起)。"""
    for suf in _通名列表:
        if w.endswith(suf) and len(w) > len(suf):
            类目, 需剥主体 = _通名类目[suf]
            if 需剥主体:
                return w[:-len(suf)], suf, 类目
            return w, suf, 类目  # 保留型:主体=全称
    return w, None, None


def _是句子碎片(w):
    return len(w) > 12 or bool(_谓语词.search(w))


def _是噪音(w):
    return bool(_噪音黑名单.match(w) or _纯色值.match(w) or _技术碎片.match(w))


def _保护英文编号(text):
    映射 = {}

    def _rep(m):
        key = f"\x00{len(映射)}\x00"
        映射[key] = m.group(0).strip()
        return f" {key} "

    return _保护_RE.sub(_rep, text), 映射


def 切词带类目(text):
    """富提取:返回 [{'主体','通名','类目','状态'}]。
    状态 confirmed=通名已定类;pending=纯专名待 LLM 兜底。"""
    jieba = _取jieba()
    结果 = []
    保护文本, 映射 = _保护英文编号(str(text or ""))
    值集 = set(映射.values())
    for tok in jieba.cut(保护文本):
        tok = 映射.get(tok.strip(), tok).strip()
        if len(_norm(tok)) < 2:
            continue
        # 英文/编号串:整体保留,不进剥头剥尾
        if tok in 值集:
            结果.append({"主体": tok, "通名": "", "类目": "", "状态": "pending"})
            continue
        if _是噪音(tok):
            continue
        w = _剥头(tok)
        主体, 通名, 类目 = _剥尾定类(w)
        主体 = _剥头(主体).strip()
        if len(_norm(主体)) < 2:
            主体 = w
        if _是句子碎片(主体) or _是噪音(主体):
            continue
        结果.append({
            "主体": 主体, "通名": 通名 or "", "类目": 类目 or "",
            "状态": "confirmed" if 类目 else "pending",
        })
    return 结果


def 提取词(text: str, *, limit: int = 80) -> list[str]:
    """简易列表:返回主体词字符串,按频次排序。兼容旧 extract_terms 签名。"""
    counts: Counter[str] = Counter()
    for item in 切词带类目(text):
        counts[item["主体"]] += 1
    return [w for w, _ in counts.most_common(limit)]
