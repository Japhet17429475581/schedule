"""Read-only analytics report using the same definitions as /stats and the admin UI."""

import asyncio
import json

from src.database import UserRepository, close_db


async def main() -> None:
    try:
        repo = UserRepository()
        report = await repo.activity_stats()
        report["groups"] = await repo.group_stats()
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
