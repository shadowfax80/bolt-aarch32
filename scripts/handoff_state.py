"""Read current work tables from HANDOFF without interpreting historical logs."""
from pathlib import Path
import re


def read_items(path):
    text = Path(path).read_text(encoding="utf-8")
    try:
        claims = text.split("## Claims (consolidated TODO)", 1)[1].split(
            "## Coverage goal", 1)[0]
    except IndexError as error:
        raise ValueError("Missing current Claims section") from error
    items, seen, header = [], set(), None
    done = False
    for line in claims.splitlines():
        if line.startswith("### "):
            done = line == "### Done"
            header = None
        if not line.startswith("|"):
            continue
        cells = [cell.strip().replace(r"\|", "|")
                 for cell in re.split(r"(?<!\\)\|", line)[1:-1]]
        if "ID" in cells and "Item" in cells:
            header = cells
            if not done and "Status" not in header:
                raise ValueError("Current work table has no Status column")
            continue
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if header is None:
            raise ValueError("Work row without table header")
        if len(cells) != len(header):
            raise ValueError("Malformed current work row: " + line)
        row = dict(zip(header, cells))
        item_id = row["ID"]
        if not item_id or item_id in seen:
            raise ValueError("Empty or duplicate current work ID: " + item_id)
        seen.add(item_id)
        items.append({
            "number": item_id,  # Keep the monitor's existing key; IDs may be R*/T*/M*.
            "item": row["Item"],
            "status": "Done" if done else row["Status"],
            "priority": row.get("Priority", ""),
            "owner": row.get("Owner", ""),
            "remaining": row.get("Notes", row.get("Scope", row.get("Patch / evidence", ""))),
        })
    if not items:
        raise ValueError("No current work items found")
    return items
