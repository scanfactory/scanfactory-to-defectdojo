import asyncio
import logging
from typing import Any
import httpx
from src.models import Product, ReportDeliverable, SFEnvironment
from src.utils import get_report_path


async def update_sf_env_with_token(env: SFEnvironment) -> None:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.post(
                f"{env.kc_url}/realms/{env.realm}/protocol/openid-connect/token",
                data={
                    "client_id": env.client_id,
                    "username": env.username,
                    "password": env.password,
                    "grant_type": "password",
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        except Exception:
            logging.critical("Ошибка выполнения авторизации в Scanfactory.")
            exit(1)
        if response.status_code != 200 or "error" in response.text:
            logging.critical(
                f"Ошибка авторизации. Проверьте данные для входа в Scanfactory и попробуйте снова: {response.text}"
            )
            exit(1)
        if token := response.json().get("access_token", None):
            env.token = token


async def get_projects(
    env: SFEnvironment, client: httpx.AsyncClient
) -> list[tuple[str, str]] | None:
    try:
        response = await client.get(f"{env.sf_url}/api/projects/?token={env.token}")
    except Exception as err:
        logging.critical(f"Check your scanfactory url and try again: {err}")
        exit(1)
    if response.status_code != 200:
        logging.error(f"Error getting projects for  {response.text}")
        exit(1)
    projects: list[dict[str, Any]] = response.json()["items"]
    return [
        (project.get("id", ""), project.get("name", ""))
        for project in projects
        if project.get("id", None)
    ]


async def get_alive_hosts_for_project(
    env: SFEnvironment, product: Product, client: httpx.AsyncClient
) -> tuple[Product, list[str]]:
    try:
        response = await client.get(
            f"{env.sf_url}/api/hosts/?project_id={product.project_id}&alive=1&token={env.token}"
        )
    except Exception:
        logging.exception(f"Ошибка получения хостов проекта {product.project_id}")
        return product, []
    if response.status_code != 200:
        logging.error(
            f"Error getting hosts for project '{product.project_id}': {response.text}"
        )
        return product, []
    return product, [
        item.get("ipv4") for item in response.json()["items"] if item.get("ipv4")
    ]


async def get_all_alive_hosts(
    env: SFEnvironment,
    products: list[Product],
    client: httpx.AsyncClient,
    limiter: asyncio.Semaphore,
) -> list[tuple[Product, list[str]]]:
    result = []
    async with limiter:
        all_tasks = [
            asyncio.create_task(get_alive_hosts_for_project(env, product, client))
            for product in products
        ]

        for task in asyncio.as_completed(all_tasks):
            product, hosts = await task
            if hosts:
                result.append((product, hosts))
    return result


async def get_latest_task_for_host(
    env: SFEnvironment, product: Product, ipv4: str, client: httpx.AsyncClient
) -> ReportDeliverable | None:
    try:
        response = await client.get(
            f"{env.sf_url}/api/tasks/?"
            f"project_id={product.project_id}&"
            "tool=infrascan&"
            "sort=-mdate&"
            "status=6&"
            f"host={ipv4}&"
            "limit=1&"
            f"token={env.token}"
        )
    except Exception:
        logging.exception(
            f"Ошибка выполенения запроса на получение данных хоста '{ipv4}'"
        )
        return None
    if response.status_code != 200:
        logging.error(
            f"Error getting tasks for project '{product.project_id}:{ipv4}': {response.text}"
        )
        return None
    data = response.json()
    tasks: list[dict[str, Any]] = data.get("items", [{}])
    task = tasks[0] if tasks else {}
    task_id = task.get("id", "")

    if filename := get_report_path(task.get("uploaded_files", [])):
        return ReportDeliverable(
            ext=filename, path=filename, task_id=task_id, product=product
        )
    return None


async def latest_tasks_of_product(
    env: SFEnvironment,
    product: Product,
    hosts: list[str],
    client: httpx.AsyncClient,
    limiter: asyncio.Semaphore,
) -> list[ReportDeliverable]:
    result = []
    async with limiter:
        all_tasks = [
            asyncio.create_task(get_latest_task_for_host(env, product, host, client))
            for host in hosts
        ]
        for task in asyncio.as_completed(all_tasks):
            if blank_deliverable := await task:
                result.append(blank_deliverable)
    return result


async def all_latest_tasks(
    env: SFEnvironment,
    alive_hosts: list[tuple[Product, list[str]]],
    client: httpx.AsyncClient,
    limiter: asyncio.Semaphore,
) -> list[ReportDeliverable]:
    result: list[ReportDeliverable] = []
    async with limiter:
        all_tasks = [
            asyncio.create_task(
                latest_tasks_of_product(env, product, hosts, client, limiter)
            )
            for product, hosts in alive_hosts
        ]
        for task in asyncio.as_completed(all_tasks):
            if res := await task:
                result.extend(res)
    return result


async def update_deliverable_with_report(
    env: SFEnvironment,
    deliverable: ReportDeliverable,
    client: httpx.AsyncClient,
) -> None:
    async with client.stream(
        method="GET",
        url=f"{env.sf_url}/api/{deliverable.path}?token={env.token}",
        headers={"accept": deliverable.content_type},
    ) as stream:
        content = await stream.aread()
        if b"File not found" in content or stream.status_code != 200:
            logging.error(
                f"Отчет '{deliverable.ext}' для проекта '{deliverable.product.project_name}/{deliverable.task_id}' не найден"
            )
        else:
            deliverable.content = content
            return
