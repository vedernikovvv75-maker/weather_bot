from __future__ import annotations

import csv
import io
from typing import Any, Iterable


def build_tasks_csv(tasks: Iterable[dict[str, Any]]) -> bytes:
    """
    Генерирует CSV (в виде bytes), который удобно открыть в Excel/LibreOffice.

    Формат:
      - разделитель: `;`
      - кодировка: `utf-8-sig` (помогает Excel корректно определить UTF-8)
      - колонки: id,text,user,created_at
    """

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    # Заголовок CSV.
    writer.writerow(["id", "text", "user", "created_at"])

    for task in tasks:
        writer.writerow(
            [
                task.get("id", ""),
                task.get("text", ""),
                task.get("user", ""),
                task.get("created_at", ""),
            ]
        )

    csv_text = output.getvalue()

    # utf-8-sig добавляет BOM — полезно для Excel.
    return csv_text.encode("utf-8-sig")

