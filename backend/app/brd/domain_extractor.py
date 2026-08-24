import json
from pathlib import Path


def extract_domains(analysis: dict) -> dict:
    capabilities = analysis.get("business_capabilities", [])
    return {
        "domain_count": len(capabilities),
        "domains": [
            {
                "domain": item.get("name", ""),
                "description": item.get("description", ""),
                "evidence": item.get("evidence", []),
                "confidence": item.get("confidence", ""),
            }
            for item in capabilities
        ],
    }


if __name__ == "__main__":
    path = Path("output/analysis_summary.json")
    if not path.exists():
        raise SystemExit("Run the main pipeline first.")
    result = extract_domains(json.loads(path.read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2))
