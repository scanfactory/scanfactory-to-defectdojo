import asyncio
from pathlib import Path
import httpx
from dotenv import load_dotenv
import logging

from src.connectors.scanfactory import (
    all_latest_tasks,
    get_all_alive_hosts,
    get_projects,
    update_deliverable_with_report,
    update_sf_env_with_token,
)
from src.connectors.ddojo import check_access_or_exit, push_report
from src.models import (
    SFEnvironment,
    DDojoEnvironment,
    Product,
)
from src.utils import (
    filter_products,
    get_resources_path,
    load_config,
    parse_args,
    init_logger,
    parse_products,
    update_and_get_products,
)


async def main():
    args = parse_args()
    load_dotenv(args.env_path)
    init_logger(args)
    dd_env = DDojoEnvironment()  # type: ignore
    sf_env = SFEnvironment()  # type: ignore
    base_path = Path(__file__).parent
    resources_path = get_resources_path(base_path)
    config = load_config(base_path)
    check_access_or_exit(dd_env)
    limiter = asyncio.Semaphore(config.max_requests)

    async with httpx.AsyncClient(
        follow_redirects=True, headers={"Accept": "application/json"}, verify=False, timeout=25
    ) as client:
        await update_sf_env_with_token(sf_env)
        if args.projects:
            products = parse_products(args.projects)
            products = await filter_products(dd_env, products, client)
        else:
            projects = await get_projects(sf_env, client)
            if not projects:
                logging.info("Проекты не найдены.")
                return
            logging.info(f"Получены проекты: {projects}")

            products = await update_and_get_products(
                dd_env, projects, resources_path, config, client
            )

        alive_hosts: list[tuple[Product, list[str]]] = await get_all_alive_hosts(
            sf_env, products, client, limiter
        )
        blank_deliverables = await all_latest_tasks(
            sf_env, alive_hosts, client, limiter
        )

        for deliverable in blank_deliverables:
            await update_deliverable_with_report(sf_env, deliverable, client)
            if deliverable.content:
                await push_report(dd_env, config, deliverable, client)


if __name__ == "__main__":
    asyncio.run(main())
