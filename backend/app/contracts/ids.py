"""稳定 ID 生成(方案07 §19.2)。

- 新节点/新 ingestion 用 UUIDv7(时间有序,索引友好)。
- 旧数据迁移用基于旧对象身份的确定性 UUIDv5,保证同一旧对象每次迁移得到同一 UUID,
  节点跨版本稳定。
Python 3.14 标准库已提供 uuid7 / uuid5。
"""
from __future__ import annotations

import uuid

# 迁移用命名空间(固定,勿改,改了会导致确定性 UUID 漂移)。
NAMESPACE_LEGACY = uuid.UUID("6f3b2a10-0000-5000-a000-000000000001")


def new_uuid7() -> str:
    """新对象 ID(时间有序 UUIDv7),返回字符串形式。"""
    return str(uuid.uuid7())


def deterministic_uuid5(*identity_parts: object) -> str:
    """由旧对象身份确定性派生 UUIDv5,输入相同则输出恒定。

    例: deterministic_uuid5("content_package", 456, "block", "b12")
    """
    name = "|".join(str(p) for p in identity_parts)
    return str(uuid.uuid5(NAMESPACE_LEGACY, name))
