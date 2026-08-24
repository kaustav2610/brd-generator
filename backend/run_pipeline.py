import argparse
import json

from app.services.pipeline import AnalysisPipeline


def main():
    parser = argparse.ArgumentParser(description="Run repository intelligence POC")
    parser.add_argument("--repo", required=True, help="GitHub URL or local repository path")
    parser.add_argument("--branch", default=None)
    parser.add_argument("--module-hints", default="")
    parser.add_argument("--upload-source", action="store_true")
    args = parser.parse_args()

    hints = [x.strip() for x in args.module_hints.split(",") if x.strip()]

    result = AnalysisPipeline().run(
        repo_url=args.repo,
        branch=args.branch,
        module_hints=hints,
        upload_source=args.upload_source,
    )

    print(json.dumps(result["summary"], indent=2))
    print("\nLocal output:", result["output_dir"])


if __name__ == "__main__":
    main()
