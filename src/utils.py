import json
import logging
from argparse import ArgumentParser, MetavarTypeHelpFormatter
from pathlib import Path

from yaml import safe_load
from src.connectors.ddojo import check_engagement, create_engagement, create_product
import httpx
from src.models import Args, Config, DDojoEnvironment, Product


def init_logger(args: Args) -> None:
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    try:
        file_handler = logging.FileHandler(args.log_path)
    except PermissionError as err:
        logging.error(
            f"Not enough permissions to create log file '{args.log_path}': {err}"
        )
        exit(1)

    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    handlers = (
        [file_handler, stream_handler]
        if args.log_to_console
        else [
            file_handler,
        ]
    )
    logging.basicConfig(level=args.log_level, handlers=handlers)


def parse_args() -> Args:
    parser = ArgumentParser(
        description="Nessus report importer for Defect Dojo",
        formatter_class=MetavarTypeHelpFormatter,
    )
    parser.add_argument(
        "--projects",
        type=str,
        nargs="+",
        default=[],
        help="Project IDs to import, format '<Scanfactory project UUID>:<Defect Dojo Engagement ID>'. Error if not exist.",
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
        action="store_true",
        default=False,
        help="Log additionally to console, defaults to False",
    )
    parser.add_argument(
        "--log-level",
        type=int,
        default=2,
        help="Lowest level of logging, defaults to 2 - INFO. Possible values are [1 - 5]: 1 - DEBUG, 2 - INFO, 3 - WARNING, 4 - ERROR, 5 - CRITICAL",
    )
    # TODO: Добавить дебаг режим
    # parser.add_argument(
    #     "--debug",
    #     action="store_true",
    #     default=False,
    #     help="Enable debug mode, defaults to False. First run without uploading docs and products creation.",
    # )
    try:
        return Args.from_namespace(parser.parse_args())
    except Exception as err:
        logging.exception(
            f"Аргументы не распознаны, проверьте аргументы и попробуйте снова: {err}"
        )
        exit(1)


def get_report_path(reports: list[str]) -> str | None:
    for report in reports:
        if report.endswith(".xml"):
            return report

    for report in reports:
        if report.endswith(".csv"):
            return report
    return None


def load_products(path: Path) -> list[Product]:
    try:
        with open(path, "r") as file:
            return [Product(**product) for product in json.load(file)]
    except json.JSONDecodeError as err:
        logging.error(f"Failed to load products from file: {err}")
        return []


async def create_missing_products(
    env: DDojoEnvironment,
    projects: list[tuple[str, str]],
    products: list[Product],
    config: Config,
    client: httpx.AsyncClient,
) -> list[Product]:
    existing_projects = [product.project_id for product in products]
    new_projects = [project_id for project_id, _ in projects]
    for project_id, project_name in projects:
        if project_id not in existing_projects:
            res = await create_product(env, project_name, config, client)
            if not res:
                continue
            product_id, product_name = res
            res = await create_engagement(env, product_id, project_name, config, client)
            if not res:
                continue
            engagement_id, engagement_name = res
            products.append(
                Product(
                    id_=product_id,
                    name=product_name,
                    engagement=engagement_name,
                    engagement_id=engagement_id,
                    project_name=project_name,
                    project_id=project_id,
                )
            )

    return [product for product in products if product.project_id in new_projects]


def update_products_cache(products: list[Product], path: Path) -> None:
    with open(path, "w") as file:
        json.dump([product.model_dump() for product in products], file, indent=4)


async def update_and_get_products(
    env: DDojoEnvironment,
    projects: list[tuple[str, str]],
    path: Path,
    config: Config,
    client: httpx.AsyncClient,
) -> list[Product]:
    products = await create_missing_products(
        env, projects, load_products(path), config, client
    )
    update_products_cache(products, path)
    return products


def parse_products(projects: list[str]) -> list[Product]:
    res = []
    for project in projects:
        project_id, engagement_id = project.split(":")
        product = Product(
            id_=0,
            name=f"non-existent-{project_id}",
            engagement=f"engagement-id-{engagement_id}",
            engagement_id=int(engagement_id),
            project_name=f"project-id-{project_id}",
            project_id=project_id,
        )
        if product not in res:
            res.append(product)
    return res


async def filter_products(
    env: DDojoEnvironment,
    products: list[Product],
    client: httpx.AsyncClient,
) -> list[Product]:
    return [
        product for product in products if await check_engagement(env, product, client)
    ]


def load_config(base_path: Path) -> Config:
    with open(base_path / "config/config.yaml", "r") as config_file:
        try:
            return Config.from_dict(safe_load(config_file))
        except Exception as err:
            logging.critical(
                f"Ошибка загрузки файла конфигураций. Измените файл в соответствии с документацией: {err}"
            )
            exit(1)


def get_resources_path(base_path: Path) -> Path:
    resources_path = base_path / "res/products.json"
    resources_path.touch(exist_ok=True)
    return resources_path
