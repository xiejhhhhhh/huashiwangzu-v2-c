import logging
import os
from app.services.knowledge.extract.types import PageResult

logger = logging.getLogger(__name__)


class ExcelExtractor:

    def extract(self, file_path: str) -> list[PageResult]:
        import pandas as pd
        ext = os.path.splitext(file_path)[1].lower()
        pages = []

        if ext == ".csv":
            try:
                df = pd.read_csv(file_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding="gbk")
            sheets = [("Sheet1", df)]
        else:
            xls = pd.ExcelFile(file_path, engine="openpyxl")
            sheets = [(name, pd.read_excel(xls, sheet_name=name)) for name in xls.sheet_names]

        for sheet_idx, (sheet_name, df) in enumerate(sheets, start=1):
            if len(df) > 500:
                lines = df.head(500).to_string(index=True) + f"\n... (truncated, total {len(df)} rows)"
            else:
                lines = df.to_string(index=True)
            cell_count = df.size
            rows, cols = df.shape
            layout_blocks = [
                {
                    "type": "sheet",
                    "name": sheet_name,
                    "rows": rows,
                    "cols": cols,
                    "columns": list(df.columns),
                    "dtypes": {str(k): str(v) for k, v in df.dtypes.items()},
                    "sample": df.head(5).to_dict(orient="records") if rows > 0 else [],
                }
            ]
            pages.append(PageResult(
                page_num=sheet_idx,
                script_text=lines,
                layout_data={"blocks": layout_blocks, "sheet_name": sheet_name, "cell_count": int(cell_count)},
            ))

        return pages
