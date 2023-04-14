from argparse import ArgumentParser, MetavarTypeHelpFormatter, Namespace
import asyncio
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Any
import httpx
from dotenv import load_dotenv
import logging
import os
from urllib.parse import urlparse, urljoin


class LoginType(str, Enum):
    TOKEN = "TOKEN"
    PWD = "PWD"


@dataclass
class Credentials:
    type_: LoginType
    token: str = ""
    username: str = ""
    password: str = ""

    def __init__(self, **args) -> None:
        if not args.get("token") and (
            not args.get("username") or not args.get("password")
        ):
            logging.error(
                "You have to provide Defect Dojo access token (preferable) or username and password"
            )
            raise ValueError("Credentials not specified")
        if token := args.get("token"):
            self.type_ = LoginType.TOKEN
            self.token = token
        elif (uname := args.get("username")) and (pwd := args.get("password")):
            self.type_ = LoginType.PWD
            self.username = uname
            self.password = pwd


@dataclass(init=True)
class Const:
    KEYCLOAK_URL: str
    KEYCLOAK_REALM: str
    USERNAME: str
    PASSWORD: str
    SCANFACTORY_URL: str

    DDOJO_URL: str
    DDOJO_USERNAME: str
    DDOJO_PASSWORD: str
    DDOJO_TOKEN: str
    DDOJO_PRODUCT_NAME: str
    DDOJO_ENGAGEMENT_NAME: str

    DDOJO_AUTO_CREATE_CONTEXT: bool = False
    DDOJO_DEDUPLICATION_ON_ENGAGEMENT: bool = False

    HEALTH_CHECK_URL: str = ''
    HEALTH_CHECK_ENDPOINTS: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.SCANFACTORY_URL = self.SCANFACTORY_URL[:-1] if self.SCANFACTORY_URL[-1] == "/" else self.SCANFACTORY_URL
        self.KEYCLOAK_REALM = "scanfactory" if not self.KEYCLOAK_REALM.strip() else self.KEYCLOAK_REALM
        self.DDOJO_AUTO_CREATE_CONTEXT = (
            self.DDOJO_AUTO_CREATE_CONTEXT.lower() in ("true", "1", "t")
            if isinstance(self.DDOJO_AUTO_CREATE_CONTEXT, str)
            else self.DDOJO_AUTO_CREATE_CONTEXT
        )
        self.DDOJO_DEDUPLICATION_ON_ENGAGEMENT = (
            self.DDOJO_DEDUPLICATION_ON_ENGAGEMENT.lower() in ("true", "1", "t")
            if isinstance(self.DDOJO_DEDUPLICATION_ON_ENGAGEMENT, str)
            else self.DDOJO_DEDUPLICATION_ON_ENGAGEMENT
        )
        self.HEALTH_CHECK_ENDPOINTS = (
            self.HEALTH_CHECK_ENDPOINTS.strip().split(" ")
            if isinstance(self.HEALTH_CHECK_ENDPOINTS, str)
            else self.HEALTH_CHECK_ENDPOINTS
        )
        if len(self.HEALTH_CHECK_ENDPOINTS) == 2:
            self.check_start, self.check_end = self.HEALTH_CHECK_ENDPOINTS
        elif len(self.HEALTH_CHECK_ENDPOINTS) == 1:
            self.check_start = self.check_end = self.HEALTH_CHECK_ENDPOINTS[0]
        self.client_id = urlparse(self.SCANFACTORY_URL).netloc.split(".", 1)[0].removeprefix("yx-")


def send_health_check_request(url: str, endpoint: str = '') -> None:
    if not url:
        return
    url += "/" if url[-1] != "/" else ''
    if endpoint:
        url = urljoin(url, endpoint)
    try:
        httpx.get(url)
    except Exception as err:
        logging.error(f"An error occurred while sending request to health check: {err}")


def init_logger(path: str, level: int = logging.INFO, console: bool = True) -> None:
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    try:
        file_handler = logging.FileHandler(path)
    except PermissionError as err:
        logging.error(f"Not enough permissions to create log file '{path}': {err}")
        exit(1)

    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    handlers = [file_handler, stream_handler] if console else [file_handler,]
    logging.basicConfig(level=level, handlers=handlers)


def parse_args() -> Namespace:
    parser = ArgumentParser(
        description="Nessus report importer for Defect Dojo",
        formatter_class=MetavarTypeHelpFormatter,
    )
    parser.add_argument(
        "--env-path",
        type=str,
        default="/root/.env",
        help="Path to the environment file, defaults to /root/.env",
    )
    parser.add_argument(
        "--log-path",
        type=str,
        default="/var/www/nessus_importer.log",
        help="Path to the log file, defaults to /var/www/nessus_importer.log",
    )
    parser.add_argument(
        "--log-to-console",
        action='store_true',
        default=False,
        help="Log additionally to console, defaults to False",
    )
    parser.add_argument(
        "--log-level",
        type=int,
        default=2,
        help="Lowest level of logging, defaults to 2 - INFO. Possible values are [0 - 5]: 0 - NOTSET, 1 - DEBUG, 2 - INFO, 3 - WARNING, 4 - ERROR, 5 - CRITICAL",
    )
    return parser.parse_args()


def load_environment(dotenv_path: str) -> tuple[Credentials, Const]:
    REQUIRED_ARGS = [
        "KEYCLOAK_URL",
        "USERNAME",
        "PASSWORD",
        "DDOJO_URL",
        "DDOJO_PRODUCT_NAME",
        "DDOJO_ENGAGEMENT_NAME",
        "SCANFACTORY_DOMAIN_TEMPLATE"
    ]
    try:
        if not Path(dotenv_path).exists():
            logging.error("Environment file does not exist")
            exit(1)
    except PermissionError as err:
        logging.error(f"Not enough permissions to load environment file '{dotenv_path}': {err}")
        exit(1)

    load_dotenv(dotenv_path)
    data: dict[str, Any] = {}
    for field in Const.__dataclass_fields__:
        value = os.environ.get(field, "")
        if not value and field in REQUIRED_ARGS:
            logging.error(f"Env var '{field}' should not be empty")
            exit(1)

        data[field] = value.strip()

    consts = Const(**data)
    creds = Credentials(**{
        "username": consts.DDOJO_USERNAME,
        "password": consts.DDOJO_PASSWORD,
        "token": consts.DDOJO_TOKEN,
    })

    return creds, consts


async def get_token(cts: Const) -> str | None:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.post(
            f"{cts.KEYCLOAK_URL}/auth/realms/{cts.KEYCLOAK_REALM}/protocol/openid-connect/token",
            data={
                "client_id": cts.client_id,
                "username": cts.USERNAME,
                "password": cts.PASSWORD,
                "grant_type": "password"
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        if response.status_code != 200 or "error" in response.text:
            logging.critical(f"Can't authorize to cluster via keycloak: {response.text}")
            return None
        return response.json().get("access_token", None)


async def get_project_ids(token: str, cts: Const, client: httpx.AsyncClient) -> list[str] | None:
    try:
        response = await client.get(f"{cts.SCANFACTORY_URL}/api/projects/?token={token}")
    except Exception:
        logging.critical("Check your scanfactory url and try again.")
        exit(1)
    if response.status_code != 200:
        logging.error(f"Error getting projects for {cts.client_id}: {response.text}")
        return None
    return [project.get('id') for project in response.json()['items'] if project.get('id', None)]


async def get_alive_hosts_for_project(token: str, cts: Const, project_id: str, client: httpx.AsyncClient) -> tuple[str, list[str]]:
    response = await client.get(f"{cts.SCANFACTORY_URL}/api/hosts/?project_id={project_id}&alive=1&token={token}")
    if response.status_code != 200:
        logging.error(f"Error getting hosts for project '{cts.client_id}:{project_id}': {response.text}")
        return project_id, []
    return project_id, [item.get("ipv4") for item in response.json()["items"] if item.get("ipv4")]


async def get_latest_task_for_host(token: str, cts: Const, project_id: str, ipv4: str, client: httpx.AsyncClient) -> tuple[str, list[str] | None]:
    response = await client.get(f"{cts.SCANFACTORY_URL}/api/tasks/?project_id={project_id}&type=infrascan&sort=-mdate&status=6&target_id={ipv4}&token={token}")
    if response.status_code != 200:
        logging.error(f"Error getting tasks for project '{cts.client_id}:{project_id}:{ipv4}': {response.text}")
        return project_id, []
    data = response.json()
    return project_id, data["items"][0]["id"] if data["count"] else None


async def get_defect_dojo_token(creds: Credentials, cts: Const) -> str:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{cts.DDOJO_URL}/api/v2/api-token-auth/",
                json={"username": creds.username, "password": creds.password},
            )
        except Exception:
            logging.critical("Failed to authenticate to Defect Dojo. Check url and credentials.")
            exit(1)
        if response.status_code != 200:
            logging.critical(f"Login error for '{creds.username}': {response.json()}")
            exit(1)
        return response.json().get("token")


async def get_and_push_report(creds: Credentials, cts: Const, token: str, project_id: str, task_id: str, client: httpx.AsyncClient) -> None:
    for type, accept in [("nessus", "application/xml"), ("csv", "text/csv")]:
        async with client.stream(
            method="GET",
            url=f"{cts.SCANFACTORY_URL}/api/projects/{project_id}/infrascan_report/{task_id}?token={token}",
            headers={"accept": accept}
        ) as stream:
            content = await stream.aread()
            if b"Report not found" in content or stream.status_code != 200:
                logging.error(f"Report '{type}' for project_id/task_id '{project_id}/{task_id}' not found")
                continue

            files = {"file": (f"nessus_{task_id}.{type}", content, "application/octet-stream")}
            headers = {"Content-type": "multipart/form-data; boundary=someboundary"}
            if creds.type_ == LoginType.TOKEN:
                headers["Authorization"] = f"Token {creds.token}"
            elif creds.type_ == LoginType.PWD:
                token = await get_defect_dojo_token(creds, cts)
                creds.type_ = LoginType.TOKEN
                creds.token = token
                headers["Authorization"] = f"Token {token}"

            response = await client.post(
                url=f"{cts.DDOJO_URL}/api/v2/import-scan/",
                headers=headers,
                data={
                    "scan_type": "Nessus Scan",
                    "verified": True,
                    "active": True,
                    "product_name": cts.DDOJO_PRODUCT_NAME,
                    "engagement_name": cts.DDOJO_ENGAGEMENT_NAME,
                    "auto_create_context": cts.DDOJO_AUTO_CREATE_CONTEXT,
                    "deduplication_on_engagement": cts.DDOJO_DEDUPLICATION_ON_ENGAGEMENT
                },
                files=files
            )
            if response.status_code != 201:
                logging.error(f"Error error uploading scan for project/task '{project_id}/{task_id}': {response.text}")
                continue

            logging.info(f"Reported scan for project/task '{project_id}/{task_id}' uploaded successfully")
            return

    logging.error(f"No reports was uploaded for project/task '{project_id}/{task_id}'")


async def main():
    args = parse_args()
    init_logger(args.log_path, int(args.log_level * 10), args.log_to_console)
    creds, cts = load_environment(args.env_path)
    send_health_check_request(cts.HEALTH_CHECK_URL, cts.check_start)

    if creds.type_ == LoginType.PWD:
        token = await get_defect_dojo_token(creds, cts)
        creds.token = token
        creds.type_ = LoginType.TOKEN
        logging.info("Successfully authenticated into Defect Dojo")

    token = await get_token(cts)
    if not token:
        return

    async with httpx.AsyncClient(follow_redirects=True, headers={"Accept": "application/json"}) as client:
        project_ids = await get_project_ids(token, cts, client)
        if not project_ids:
            return
        logging.info(f"Received projects: {project_ids}")

        tasks = []
        for project_id in project_ids:
            tasks.append(asyncio.create_task(get_alive_hosts_for_project(token, cts, project_id, client)))

        alive_hosts: dict[str, list[str]] = {}
        for project_id, hosts in await asyncio.gather(*tasks):
            alive_hosts[project_id] = hosts

        logging.info(f"Received hosts (10 latest showed): {json.dumps({project: hosts[:10] for project, hosts in alive_hosts.items()})}")

        tasks = []
        for project_id, hosts in alive_hosts.items():
            for host in hosts:
                tasks.append(asyncio.create_task(get_latest_task_for_host(token, cts, project_id, host, client)))

        tasks_: dict[str, list[str]] = {}
        for project_id, task_ in await asyncio.gather(*tasks):
            if task_:
                tasks_.setdefault(project_id, []).append(task_)
        logging.info(f"Received tasks (10 latest showed): {json.dumps({project: tasks[:10] for project, tasks in tasks_.items()})}")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = []
        for project_id, task_ids in tasks_.items():
            for task_id in task_ids:
                tasks.append(asyncio.create_task(get_and_push_report(creds, cts, token, project_id, task_id, client)))

        await asyncio.gather(*tasks)

    send_health_check_request(cts.HEALTH_CHECK_URL, cts.check_end)


if __name__ == "__main__":
    asyncio.run(main())
