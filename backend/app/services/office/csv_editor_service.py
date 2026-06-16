import os
import csv
import io
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.file import File
from app.core.exceptions import NotFound
from app.config import get_settings

logger = logging.getLogger(__name__)


class CsvEditorService:

    async def read(self, db: AsyncSession, file_id: int) -> dict:
        file = await db.get(File, file_id)
        if not file or file.deleted:
            raise NotFound("文件不存在")

        storage_root = Path(get_settings().UPLOAD_DIR)
        full_path = storage_root / file.storage_path

        if not full_path.exists():
            raise NotFound("文件物理路径不存在")

        delimiter = self._detect_delimiter(full_path)

        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        mtime = os.path.getmtime(full_path)

        return {
            "content": content,
            "delimiter": delimiter,
            "mtime": str(mtime),
        }

    async def save(self, db: AsyncSession, file_id: int, content: str, delimiter: str = ",", client_mtime: str | None = None) -> None:
        file = await db.get(File, file_id)
        if not file or file.deleted:
            raise NotFound("文件不存在")

        storage_root = Path(get_settings().UPLOAD_DIR)
        full_path = storage_root / file.storage_path

        if client_mtime and full_path.exists():
            current_mtime = str(os.path.getmtime(full_path))
            if current_mtime != client_mtime:
                raise ValueError("文件已被其他用户修改，请刷新后重试")

        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8", newline="") as f:
            f.write(content)

    def _detect_delimiter(self, file_path: Path) -> str:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(4096)
        if sample.count("\t") > sample.count(","):
            return "\t"
        return ","

    async def parse_to_json(self, db: AsyncSession, file_id: int) -> list[dict]:
        data = await self.read(db, file_id)
        reader = csv.DictReader(io.StringIO(data["content"]), delimiter=data["delimiter"])
        return list(reader)
