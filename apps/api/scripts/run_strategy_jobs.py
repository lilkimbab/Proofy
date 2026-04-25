from __future__ import annotations

from app.services.demo_service import service


def main() -> None:
    result = service.process_strategy_jobs(limit=50)
    print(f"[strategy-worker] processed={result['processedCount']}")
    for item in result["processed"]:
        print(
            "[strategy-worker] "
            f"user={item['userId']} job={item['jobId']} status={item['status']} "
            f"reason={item['reason']} provider={item.get('provider') or '-'}"
        )


if __name__ == "__main__":
    main()
