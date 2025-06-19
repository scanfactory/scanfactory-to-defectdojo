# Nessus Reports Importer

Скрипт, который импортирует последние сгенерированные отчеты Nessus в Defect Dojo

## Первый запуск

Программа была написана и тестировалась на Python 3.11, для начала вам необходимо его установить  
Затем установить все зависимости командой `pip install -r requirements.txt`  
Далее следовать документации  

## Параметры запуска

Пример для крона:  
`python3 path/to/nessus_importer.py --log-path=/path/to/.log --env-path=/root/nessus_importer.env --projects 2e32d40e-16ac-11ee-ba6f-f71abd6fb617:6`

---

Внимание! Скрипт имеет 2 основных режима работы.

1. Автоматически создавать продукты DD под каждый из проектов Scanfactory и при последующих запусках проверять необходимость создания новых. В данном случае параметр `--projects` не используется при запуске.
2. Скрипт будет импортировать отчеты только для указанных вами проектов и engagement'ов. Режим включается параметром `--projects`. Примеры показаны ниже

`python3 nessus_importer.py -h` -> Посмотреть параметры запуска  

```text
usage: nessus_importer.py [-h] [--projects str [str ...]] [--env-path str] [--log-path str] [--log-to-console] [--log-level int]

Nessus report importer for Defect Dojo

options:
  -h, --help                show this help message and exit
  --projects str [str ...]  Project IDs to import, format '<Scanfactory project UUID>:<Defect Dojo Engagement ID>'. Error if not exist.
  --env-path str            Path to the environment file, defaults to /root/.env
  --log-path str            Path to the log file, defaults to /var/www/nessus_importer.log
  --log-to-console          Log additionally to console, defaults to False
  --log-level int           Lowest level of logging, defaults to 2 - INFO. Possible values are [1 - 5]: 1 - DEBUG, 2 - INFO, 3 - WARNING, 4 - ERROR, 5 - CRITICAL
```

Все пути к файлам указывать желательно полностью, без сокращений и без относительных путей.  
Вы можете не указывать путь к `.env` файлу, однако эти переменные должны быть экспортированы в окружение. Пример команды `export ENV_VAR_NAME=value`

### Пример с объяснением

`python nessus_importer.py --env-path my.env --log-path .log --log-to-console --log-level 3 --projects 2e32d40e-16ac-11ee-ba6f-f71abd6fb617:6 34bcdd25-55c0-4a71-9a1f-8ca87fc49547:4`

* Указан путь до файла с переменными среды
* Указан путь до файла с логами
* Скрипт будет писать логи в том числе и в консоль
* Уровень логирования - WARNING.
* Указаны ID проектов Scanfactory, для которых будет производиться экспорт сканов в engagement'ы, ID которых указаны через `:` после ID проектов

## Файл конфигурации

Файл `config.yaml` расположен в папке `config`  
В нем находится базовый конфиг и конфиг, используемый для создания продуктов в DD

### Содержание конфига

```yaml
base_config:
  max_requests: 3  # Количество одновременных запросов к серверу Scanfactory. min: 1, max: 10
  # не рекомендуется выставлять более 5

  scan_type: "Tenable Scan"  # Тип скана, который будет загружен в DD.
  # Для версияй DD >= 2.25.0 тип скана "Tenable Scan", иначе "Nessus Scan"

  # Минимальный уровень уязвимости при импорте
  minimum_severity: "info" # Info, Low, Medium, High, Critical

  # https://demo.defectdojo.org/api/v2/doc/ -> /import-scan/
  auto_create_context: True # Если False, то дедупликация не будет выполняться
  deduplication_on_engagement: True  # Дедупликацию можно включить и настроить тут
  # Боковая панель -> System settings

  # ID админа, который может создавать продукты и engagements
  # По умолчанию 1, первый созданный админ.
  lead_user_id: 1


product_creation_config:
  # Этот конфиг соответствует API Defect Dojo. Более подробно смотрите в документации
  # https://demo.defectdojo.org/api/v2/oa3/swagger-ui/ POST products
  tags: [Scanfactory]
  # Продукты будут называться так же, как и проекты в Scanfactory
  # В описании можете использовать плейсхолдер {}, который будет заменен на имя проекта
  # Если же такого плейсхолдера нет, то Имя проекта будет добавлено в конец строки
  description: 'Продукт проекта Scanfactory "{}"'
  prod_numeric_grade: 0
  business_criticality: "very high"
  platform:
  lifecycle:
  origin:
  user_records:
  revenue:
  external_audience: False
  internet_accessible: False
  enable_product_tag_inheritance: False
  enable_simple_risk_acceptance: False
  enable_full_risk_acceptance: True
  disable_sla_breach_notifications: False
  prod_type: 1
  sla_configuration: 1
```

## .env файл

Как такового .env файла может и не быть. Но необходимо, чтобы все эти переменные были в окружении

```conf
KEYCLOAK_URL=https://keycloak.domain.com
KEYCLOAK_REALM=factory
USERNAME=  # Юзернейм админа
PASSWORD=

SCANFACTORY_URL=https://project.sf-cloud.ru

# Адрес по которому расположен Defect Dojo
DDOJO_URL=http://yourdefectdojourl.com
# Токен для авторизации в DefectDojo. Находится тут: http://yourdefectdojourl.com/api/key-v2
DDOJO_TOKEN=
```

## res/products.json

Автоматически генерируемый файл, управляется программой.  
Файл используется для хранения связей между проектами Scanfactory и продуктами, engagement'ами Defect Dojo. Его нельзя перемещать или переименовывать, иначе вы потеряете связи и программа создаст их заново с нуля.  
Если вы хотите изменить связи (не рекомендуется):  
Вам надо будет изменить поля `id_`, `name`, `engagement_id` и `engagement`, чтобы связать уже существующий проект Scanfactory с новыми созданными вами продуктом и engagement'ом DD  

```json
{
  "id_": 7, // ID Продукта DD
  "name": "TEST", // Имя продукта DD
  "engagement": "default TEST",  // Имя engagement'a
  "engagement_id": 6,  // ID engagement'a
  "project_name": "TEST",  // Имя проекта Scanfactory
  "project_id": "34bcdd25-55c0-4a71-9a1f-8ca87fc49547"  // ID Проекта Scanfactory
}
```
