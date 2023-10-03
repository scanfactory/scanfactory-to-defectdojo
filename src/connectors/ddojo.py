from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from src.models import Config, Product, ReportDeliverable, DDojoEnvironment
import httpx
import logging
from datetime import timedelta
import asyncio


def check_access_or_exit(env: DDojoEnvironment) -> None:
    headers = {"Authorization": f"Token {env.token}"}
    response = httpx.get(f"{env.url}/api/v2/users/", headers=headers)
    if response.status_code == 200:
        logging.info("Успешная авторизация в Defect Dojo.")
    else:
        logging.critical("Ошибка доступа к Defect Dojo. Проверьте адрес и API ключ.")
        exit(1)


async def create_product(
    env: DDojoEnvironment, project_name: str, config: Config, client: httpx.AsyncClient
) -> tuple[int, str] | None:
    response = await client.post(
        f"{env.url}/api/v2/products/",
        headers={"Authorization": f"Token {env.token}"},
        json=config.get_product_payload(project_name),
    )
    if response.status_code != 201:
        logging.error(
            f"Ошибка создания продукта для проекта '{project_name}': {response.text}"
        )
        return None
    data: dict[str, Any] = response.json()
    if (id_ := data.get("id", "")) and (name := data.get("name", "")):
        logging.info(f"Продукт для проекта '{project_name}' успешно создан")
        return id_, name


async def create_engagement(
    env: DDojoEnvironment,
    product_id: int,
    project_name: str,
    config: Config,
    client: httpx.AsyncClient,
) -> tuple[int, str] | None:
    now = datetime.now(tz=timezone.utc)
    engagement_payload = {
        "name": f"default {project_name}",
        "description": f"Default engagement for '{project_name}'",
        "target_start": now.strftime("%Y-%m-%d"),
        "target_end": (now + timedelta(days=365)).strftime("%Y-%m-%d"),
        "product": product_id,
        "environment": "Prod",
        "engagement_type": "Interactive",
        "lead": config.lead_user_id,
        "deduplication_on_engagement": config.deduplication_on_engagement,
    }
    response = await client.post(
        f"{env.url}/api/v2/engagements/",
        headers={"Authorization": f"Token {env.token}"},
        json=engagement_payload,
    )
    if response.status_code != 201:
        logging.error(
            f"Ошибка создания Engagement'а для '{project_name}': {response.text}"
        )
        return None
    data = response.json()
    if (id_ := data.get("id", "")) and (name := data.get("name", "")):
        logging.info(f"Engagement для продукта '{project_name}' created successfully")
        return id_, name


async def push_report(
    env: DDojoEnvironment,
    config: Config,
    report: ReportDeliverable,
    client: httpx.AsyncClient,
) -> None:
    files: Mapping[str, tuple[str, bytes, str]] = {
        "file": (
            f"nessus_{report.task_id}.{report.ext}",
            report.content,  # type: ignore
            "application/octet-stream",
        )
    }
    try:
        response = await client.post(
            url=f"{env.url}/api/v2/import-scan/",
            headers={
                "Content-type": "multipart/form-data; boundary=someboundary",
                "Authorization": f"Token {env.token}",
            },
            data={
                "scan_type": config.scan_type,
                "verified": True,
                "active": True,
                "engagement": report.product.engagement_id,
                "auto_create_context": config.auto_create_context,
                "deduplication_on_engagement": config.deduplication_on_engagement,
            },
            files=files,
        )
    except Exception:
        logging.exception(
            f"Внутренняя ошибка. Не удалось экспортировать скан для '{report.product.project_name}/{report.task_id}'"
        )
        return
    if response.status_code != 201:
        logging.error(
            f"Ошибка экспорта скана для '{report.product.project_name}/{report.task_id}': {response.text}"
        )
        return
    logging.info(
        f"Скан для '{report.product.project_name}/{report.task_id}' успешно экспортирован"
    )


async def push_all_reports(
    env: DDojoEnvironment,
    config: Config,
    reports: list[ReportDeliverable],
    client: httpx.AsyncClient,
    limiter: asyncio.Semaphore,
) -> None:
    async with limiter:
        all_tasks = [
            asyncio.create_task(push_report(env, config, report, client))
            for report in reports
        ]
        for task in asyncio.as_completed(all_tasks):
            await task


async def check_engagement(env: DDojoEnvironment, product: Product, client: httpx.AsyncClient) -> bool:
    try:
        response = await client.get(
            f"{env.url}/api/v2/engagements/{product.engagement_id}/", headers={"Authorization": f"Token {env.token}"}
        )
    except Exception:
        logging.exception(f"Ошибка проверки Engagement '{product.engagement_id}' для проекта {product.project_id}. Для него не будут импортированы отчеты.")
        return False
    if response.status_code != 200:
        logging.error(f"Engagement с ID '{product.engagement_id}' не найден: HTTP {response.status_code}")
        return False
    data: dict[str, Any] = response.json()
    if data.get("active", False):
        logging.info(f"Engagement {product.engagement_id} активен")
        return True
    logging.error(f"Engagement {product.engagement_id} не активен, создайте другой активный engagement для проекта {product.project_id}")
    return False