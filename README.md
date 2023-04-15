# Nessus Reports Importer

Скрипт, который импортирует последние сгенерированные отчеты Nessus в Defect Dojo

## Аргументы командной строки

При запуске кроном:  
`python3 path/to/nessus_importer.py --log-path=/path/to/.log --env-path=/root/nessus_importer.env`  

---
`python3 nessus_importer.py -h` -> Посмотреть параметры запуска  

```text
usage: nessus_importer.py [-h] [--env-path str] [--log-path str] [--log-to-console] [--log-level int]

Automatic cleaner of old docker images

options:
  -h, --help        show this help message and exit
  --env-path str    Path to the environment file, defaults to /root/.env
  --log-path str    Path to the log file, defaults to /var/www/nessus_importer.log
  --log-to-console  Log additionally to console, defaults to False  ### Не принимает значений, включает стриминг логов в косоль помимо файла,
                    для запуска руками или первой настройки
  --log-level int   Lowest level of logging, defaults to 2 - INFO. Possible values are [0 - 5]: 0 - NOTSET, 1 - DEBUG, 2 - INFO, 3 - WARNING, 4 - ERROR, 5 - CRITICAL

```

Все пути к файлам указывать желательно полностью, без сокращений и без относительных путей

```text
python nessus_importer.py --log-path=.log --env-path=nessus_importer.env --log-level=1 --log-to-console
// Файл с логами будет находиться в папке запуска/.log,
// будет искать .env там же в папке запуска,
// будет выводить все логи, т.к. будет включен режим отладки,
// будет дополнительно писать логи в консоль
```

## .env файл

В файле nessus_importer.env есть примеры правильного использования переменных  

```conf
# Обязательные переменеые
# Пожалуйста, указывайте адреса в точночти как в примере

KEYCLOAK_URL=https://keycloak.domain.com
KEYCLOAK_REALM= # можно оставить пустым
USERNAME=  # Юзернейм админа
PASSWORD=

SCANFACTORY_URL=

# Адрес по которому расположен Defect Dojo
DDOJO_URL=http://yourdefectdojourl.com
# Можно получить с главной страницы проекта
DDOJO_PRODUCT_NAME=
# Можно получить с главной страницы engagement'а или со списка в проекте
DDOJO_ENGAGEMENT_NAME=

# Можно указать либо токен (более предпочтительно), либо юзернейм с паролем
DDOJO_USERNAME=
DDOJO_PASSWORD=
DDOJO_TOKEN=

# https://demo.defectdojo.org/api/v2/doc/ -> /import-scan/
# Включает дедупликацию данных при импорте отчетов (необходима тонкая настройка Defect Dojo)
DDOJO_AUTO_CREATE_CONTEXT=True
DDOJO_DEDUPLICATION_ON_ENGAGEMENT=True

# Опционально, можно не использовать
# Адрес, куда отправить GET запрос для подтверждения работы скрипта
# https://someurlexample.com/health-check
HEALTH_CHECK_URL=
# Либо список пустой, либо там 2 значения для отправки запроса на эндпоинт при старте и при окончании работы скрипта
# Если эндпоинт один, запрос будет отправлен на него при старте и при завершении работы
# Endpoints for tracking downtime. Example: Sends GET request to $HEALTH_CHECK_URL/start when script starts and to $HEALTH_CHECK_URL/end when ends
# Leave blank if you only need the url
HEALTH_CHECK_ENDPOINTS="start end"
```
