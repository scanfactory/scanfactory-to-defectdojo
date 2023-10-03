from argparse import Namespace
from typing import Any
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class SFEnvironment(BaseSettings):
    username: str = Field(validation_alias="SF_USERNAME")
    password: str = Field(validation_alias="SF_PASSWORD")
    kc_url: str = Field(validation_alias="KEYCLOAK_URL")
    sf_url: str = Field(validation_alias="SCANFACTORY_URL")
    realm: str = Field("scanfactory", validation_alias="KEYCLOAK_REALM")
    client_id: str = Field(validation_alias="SCANFACTORY_URL")
    token: str | None = None

    @field_validator(
        "username", "password", "kc_url", "sf_url", mode="after", check_fields=True
    )
    def check_exists(cls, value: str):
        if not value:
            raise ValueError("Missing environment variable")
        return value

    @field_validator("sf_url", "kc_url")
    def fix_url(cls, v: str):
        return v.removesuffix("/")

    @field_validator("client_id")
    def extract_client_id(cls, v: str):
        return urlparse(v).netloc.split(".", 1)[0].removeprefix("yx-")


class DDojoEnvironment(BaseSettings):
    url: str = Field(validation_alias="DDOJO_URL")
    token: str = Field(validation_alias="DDOJO_TOKEN")

    @field_validator(
        "url", "token", mode="after", check_fields=True
    )
    def check_exists(cls, value: str):
        if not value:
            raise ValueError("Missing environment variable")
        return value

    @field_validator("url")
    def fix_url(cls, v: str):
        return v.removesuffix("/")


class Config(BaseModel):
    scan_type: str
    auto_create_context: bool = True
    deduplication_on_engagement: bool = True
    product_payload: dict[str, Any]
    lead_user_id: int
    max_requests: int
    minimum_severity: str

    @staticmethod
    def from_dict(raw_data: dict[str, Any]) -> "Config":
        data = raw_data.get("base_config", {})
        data["product_payload"] = raw_data.get("product_creation_config", {})
        return Config.model_validate(data)

    @field_validator("scan_type")
    def check_scan_type(cls, value: str):
        value = value.strip().title()
        if value not in ("Nessus Scan", "Tenable Scan"):
            raise ValueError(
                f"Invalid scan type '{value}'. Scan type should be 'Tenable Scan' or 'Nessus Scan'"
            )
        return value

    @field_validator("max_requests")
    def check_max_requests(cls, value: int):
        if value < 1 or value > 10:
            raise ValueError("Invalid max requests: value should be in range 1-10")
        return value

    @field_validator("minimum_severity")
    def check_minimum_severity(cls, value: str):
        value = value.strip().capitalize()
        if value not in ("Info", "Low", "Medium", "High", "Critical"):
            raise ValueError(
                f"Invalid minimum severity '{value}'. Minimum severity should be 'Info', 'Low', 'Medium', 'High' or 'Critical'"
            )
        return value

    def get_product_payload(self, project_name: str):
        payload = self.product_payload.copy()
        payload["name"] = project_name
        desc: str = payload["description"]
        if "{}" in desc:
            payload["description"] = desc.format(project_name)
        else:
            payload["description"] = f"{desc} {project_name}".strip()
        return payload


class Product(BaseModel):
    id_: int
    name: str

    engagement: str
    engagement_id: int

    project_name: str
    project_id: str


class ReportDeliverable(BaseModel):
    ext: str
    path: str
    task_id: str
    product: Product
    content: bytes | None = None
    content_type: str = ""

    @model_validator(mode="after")
    def assign_content_type(self):
        self.content_type = "application/xml" if self.ext == "xml" else "text/csv"
        return self

    @field_validator("path")
    def fix_path(cls, value: str):
        return value.strip("/")

    @field_validator("ext")
    def extract_ext(cls, value: str):
        ext = value.rsplit(".")[-1]
        if ext not in ("xml", "csv"):
            raise ValueError(f"Invalid file extension '{ext}'")
        return ext


# TODO: Добавить дебаг режим
class Args(BaseModel):
    env_path: str
    log_path: str
    log_to_console: bool
    log_level: int
    # debug: bool
    projects: list[str]

    @staticmethod
    def from_namespace(namespace: Namespace) -> "Args":
        data = namespace.__dict__
        # data["log_level"] = 1 if data["debug"] else data["log_level"]
        return Args.model_validate(data)

    @field_validator("log_level")
    def check_log_level(cls, value: int):
        if value < 1 or value > 5:
            raise ValueError("Invalid log level")
        return int(value * 10)
