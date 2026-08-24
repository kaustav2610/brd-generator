import json
from pathlib import Path


def create_review_file(analysis: dict, output_dir: Path):
    review = {
        "status": "PENDING_SME_REVIEW",
        "reviewer": None,
        "comments": [],
        "business_rules": [
            {
                "id": x.get("id"),
                "status": "PENDING",
                "corrected_text": None,
                "comment": None,
            }
            for x in analysis.get("business_rules", [])
        ],
        "workflows": [
            {
                "id": x.get("id"),
                "status": "PENDING",
                "corrected_text": None,
                "comment": None,
            }
            for x in analysis.get("workflows", [])
        ],
    }
    path = output_dir / "review.json"
    path.write_text(json.dumps(review, indent=2), encoding="utf-8")
    return path


def update_review(output_dir: Path, item_type: str, item_id: str, status: str,
                  corrected_text: str | None, comment: str | None, reviewer: str):
    path = output_dir / "review.json"
    if not path.exists():
        raise FileNotFoundError("Review file does not exist")

    data = json.loads(path.read_text(encoding="utf-8"))
    collection = data.get(item_type)
    if not isinstance(collection, list):
        raise ValueError("item_type must be business_rules or workflows")

    for item in collection:
        if item.get("id") == item_id:
            item["status"] = status
            item["corrected_text"] = corrected_text
            item["comment"] = comment
            data["reviewer"] = reviewer
            if all(x.get("status") in {"ACCEPTED", "REJECTED"} for x in collection):
                data["status"] = "REVIEWED"
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data

    raise ValueError(f"Item {item_id} not found")
