# DECISIONS.md

> Читается первым. Здесь фиксирую развилки: вопрос → что выбрал → почему.
> Пометка `[TBD]` — решение ещё не принято.

## 0. Как читать этот файл
- **Источник правды** для каждого места API — раздел 2.
- Нормализация данных (бэкенд) — раздел 3.
- Даты/дедлайны — раздел 4.
- Канбан/карточка/сводка — раздел 5.
- Мониторинг — раздел 6, деплой — раздел 7, ассистенты — раздел 8.

---

## 1. Общая архитектура

| Слой | Что выбрал | Почему |
|---|---|---|
| UI | Angular 19, NgModules | [TBD: почему модули, а не standalone — обосновать] |
| Верстка | Angular Material | Облегчает верстку |
| Стейт | RxJS-сервис | Одностраничник; операторы дают polling/retry/фильтрацию |
| Сеть | HttpClient + сервис-обёртка | [TBD: интерсептор для 429] |
| Бэкенд | `mock_server.py` v0.7 + `normalization.py` + `metrics.py` | Нормализация и метрики вынесены отдельно; DTO стабилен |
| Мониторинг | `/metrics` (Prometheus format) + `/api/v2/metrics/json` + виджет на фронте | См. раздел 7 |
| Деплой | VPS Ubuntu, 1 CPU / 1.5GB / 10GB, `10.100.30.37` (создаётся) | [раздел 8] |

---

## 2. Источник правды по API

> **Главный вывод:** `docs/api.md` — устаревшая вики. **Источник правды = код сервера v0.7**. Зафиксировал конкретные расхождения (ниже). `CHANGELOG.md` ещё не сверял — [TBD].

| Место | docs/api.md (старое) | Код v0.7 / ответы | Источник правды | Почему |
|---|---|---|---|---|
| Список задач | `GET ...?page=0`, в теле `data` | `GET` (page по умолчанию **0**) и **`POST /api/v2/tasks`** с фильтрами/сортировкой в теле; тело отдаёт **и `data`, и `items`**, meta: `page, per_page, total, total_pages, filters, sort` | Код сервера | POST позволяет прокинуть сложные фильтры, GET остался для совместимости |
| `page=0` | docs: первая страница | Теперь **`page=0` — валидная первая страница**; `total_pages = ceil(total/limit)` (без `+1`, баг прошлой версии исправлен) | Код сервера | Фронт может начинать с 0 |
| Детали задачи | `GET .../{id}` | Принимает **id / key `TB-…` / uuid**; `private` без `X-Staff-Key: tb-staff-2024` → 403; `skipped` из reindex → 404 | Код сервера | — |
| Список задач возвращает | сырые объекты | **`TaskDto`** (нормализованные поля + `status_id/label`, `priority_id/label`, `tags_items`, `all_data`) | Код + normalization | Фронт получает каноны, а не грязь |
| Комментарии | `?page=0` | **Курсорная** пагинация: `?cursor=…&limit=25`; ответ `{comments, next_cursor, total}` | Код сервера | page-based не поддерживается |
| Фильтры для UI | не описано | **`GET /api/v2/filters`** → статусы/приоритеты/проекты/исполнители/теги + `unknown` + `archived` + `due_within_days` + `sort` | Код сервера | Фронт не хардкодит списки |
| Сводка | не описано | **`POST /api/v2/summary`** → `compute_summary` (см. 5.1) | Код сервера | — |
| `created_at` / даты | «UTC timestamp» | ISO / число (сек/мс) / без зоны | Код + `parse_dt` | См. 4 |
| 429 | не описано | Burst cap **15/сек**, `X-RateLimit-Limit`, `X-RateLimit-Remaining`; `Retry-After` нет | Код сервера | — |
| Health | `/health` → `{status, token}` | **`/health` и `/api/v2/health` → `{status:"ok", token:HEARTBEAT}`** — токен вернулся | Код сервера | **Токен теперь в `/health`**, но я всё равно беру `pulse` как источник heartbeat (см. ниже) |
| **Heartbeat** | «системный метод» | **`GET /api/v2/system/pulse`** → `{service, heartbeat, version, utc_time, metrics}` — `metrics` встроены в пульс | Код сервера | `heartbeat` = `TB-PULSE-YYYYMMDD` на экран |
| Метрики | не описано | **`GET /metrics`** (Prometheus text v0.0.4) и **`GET /api/v2/metrics/json`** | Код сервера | Внешний сбор + встроенный JSON для фронта |
| Users / Projects | не описаны | `GET /api/v2/users`, `/api/v2/projects` — сырые справочники | Код сервера | Основа нормализации |
| Private | не описано | `private=true` → 403 без `X-Staff-Key: tb-staff-2024` | Код сервера | — |

**Что не сошлось и на чём остановился:** docs говорит `data`/`per_page`/`page=0`, устаревшие `/health` — сервер v0.7 отдаёт и `data`, и `items`, `page=0` теперь первая страница, `total_pages` без `+1`, `/health` снова с токеном, а токен дублируется в `pulse`. Выбрал **сервер v0.7 как источник правды**: фронт работает против него, а не против вики. `CHANGELOG.md` ещё не сверял — [TBD].

---

## 3. Нормализация данных (`normalization.py`)

### 3.1 Политика
Пусто → `None`; распознано → канон; есть, но не распознано → `UNKNOWN`; сырьё в `all_data`.

### 3.2 Статусы (код — источник правды)

| Канон | id | Подпись | Сырые |
|---|---|---|---|
| NEW | 1 | Новый | new, open, tod, todo, ждут |
| IN_PROGRESS | 2 | В работе | in_proges, in-proges, inproges, inprogress, in_progress, in-progress, doing, в работе |
| CODE_REVIEW | 3 | На ревью | reviw, code_rviw, review, code_review, на ревью |
| BLOCKED | 4 | Заблокирован | blocked |
| HOLD | 5 | На паузе | hold |
| DONE | 6 | Готово | done, resolvd, resolved, готв, готово, closed, caneld, canceled, cancelled |

> В коде алиасы шире «финальной таблицы» из задания — опечатки (`reviw`, `resolvd`, `caneld`) реальные. `caneld/canceled/cancelled` → **DONE** [TBD: оставить или вынести CANCELLED].

### 3.3 Приоритеты
P0(1) Крит: 0,p0,крит,critical,blocker · P1(2) Высокий: 1,p1,high,urgent,высокий · P2(3) Средний: 2,p2,normal,medium,средний · P3(4) Низкий: 3,p3,low,низкий.

### 3.4 Проекты / исполнители
- Проект: канон = `title`; алиасы + `PROJECT_ALIASES`. Неизвестные не в UI, но в `all_data`.
- Исполнитель: канон = `name`; матч по id/login/email/токенам; коллизии → `UNKNOWN`. `assignee_active: true/false/null`.

### 3.5 Числовые id
`UNKNOWN_ID=0` — «было, не распознали»; `FILTER_NONE_ID=-1` — «значения не было».

### 3.6 Estimate → часы (8 ч/день), непарсимое → `UNKNOWN`.

### 3.7 Фильтры / сортировка
`status/priority/tag` принимают int-id и строку-канон. Вычисляемые: `overdue,no_assignee,unknown_data,no_due,no_priority,is_due_date_error,due_within_days`. Сортировка `created/due/estimate`.

**Код:** `normalization.py`. **Тесты:** [TBD].

---

## 4. Даты и дедлайны

`parse_dt`: число → `>1e12` = мс (÷1000), иначе сек, UTC; ISO (`Z`→`+00:00`); **без зоны = UTC**; fallback `dd.mm.yyyy HH:MM` и `dd.mm.yyyy`; не распарсилось → `None`/`UNKNOWN`.
В `TaskDto` — строкой `dd.mm.yyyy HH:MM`; для вычислений — из `all_data`.

**Противоречия:** `is_due_date_error=true` если обе даты есть и `due<created` → ⚠ бейдж. Поля `due/due_date/due_utc/due_ts/due_local` — первое непустое [TBD: показывать оба при расхождении]. Нет срока → `no_due`.

**Срочность:** просрочено = `due<now` и `status≠DONE`; «скоро» = `0≤due−now≤N·86400`; N задаёт человек.

**Код:** `parse_dt`, `_is_overdue`, `_is_due_soon`, `_is_due_date_error`. **Тесты:** [TBD].

---

## 5. Канбан, карточка, сводка

- Колонки: NEW, IN_PROGRESS, CODE_REVIEW, BLOCKED, HOLD, DONE (+«Неизвестно», «Нет статуса»).
- Карточка: [TBD — панель/модалка]; поля из `TaskDto`; пусто → «-»; mojibake чинится.
- Комментарии — **курсором** (`next_cursor`), не страницами.

### 5.1 Сводка (`POST /api/v2/summary`)

| Метрика | Правило | Поле | Почему |
|---|---|---|---|
| Просрочено | `due<now` и `status≠DONE` | due (all_data) | завершённые не просрочены |
| Заблокировано | `status==BLOCKED` | status | канон 3.2 |
| Без исполнителя | `assignee is None` | assignee | `UNKNOWN` ≠ «нет» |
| Дедлайн в N дней | `0≤due−now≤N·86400` | due | N по умолчанию 7 |
| Без срока / без приоритета | `due is None` / `priority is None` | — | — |
| Ошибка дат | `due<created` | due,created | `is_due_date_error` |
| Нет активного исполнителя | `assignee is None` или `assignee_active is False` | — | — |

Дополнительно: `total`, `unknown_data`, `by_status`.

> **Сводка считается на сервере** (`POST /api/v2/summary`) с учётом тех же фильтров, что и лента, — фронт не пересчитывает, чтобы не разъезжаться.

---

## 6. Обновление данных и устойчивость

- Polling каждые [TBD — ≥30с]; пауза при скрытой вкладке — [TBD].
- «N минут назад» — от последнего успешного обновления; при ошибке таймер идёт, статус краснеет.
- **429:** burst **15/сек**, `X-RateLimit-Remaining`; `Retry-After` нет. Фронт: exponential backoff + jitter, ориентируется на `Remaining`.
- API пропал: [TBD — заглушка с последними данными].
- **Heartbeat в подвале:** `GET /api/v2/system/pulse` → поле **`heartbeat`** (`TB-PULSE-YYYYMMDD`) на экран. `/health` тоже отдаёт `token`, но беру `pulse` — там ещё `metrics` (см. 7).
- **Метрики в пульсе:** `pulse.metrics` — встроенный JSON, можно рисовать виджет без отдельного запроса.

---

## 7. Мониторинг

### 7.1 Что уже собирает бэкенд (`metrics.py`, видно по `_send`/`_normalized_tasks`)
- `http_requests_total{method,route,status}` — counter.
- `http_errors_total{route,status_class}` — counter.
- `http_request_duration_seconds{route}` — histogram (observe).
- `rate_limit_hits_total` — counter.
- `normalization_errors_total{field}` — counter (по полям status/priority/project/assignee/estimate/created/due).
- `filter_applied_total{name}` — counter.
- `tasks_normalized_total` — counter.
- `summary_requests_total{status}` — counter.

### 7.2 Как забирать снаружи
- `GET /metrics` — **Prometheus text** (`text/plain; version=0.0.4`) → совместимо с Prometheus/любым скрейпером.
- `GET /api/v2/metrics/json` — тот же набор в JSON → для фронт-виджета.
- `GET /api/v2/system/pulse` → встроенный `metrics` (без отдельного запроса).

**Почему свой эндпоинт, а не Prometheus+Grafana:** минимальный стек, нет внешних зависимостей; при необходимости Prometheus подключается к `/metrics` без изменений кода. [TBD: поднимать ли Prometheus+Grafana на VPS — опционально].

### 7.3 Таблица «что открыл бы в 3 часа ночи»

| Метрика | Зачем | Где перестаёт быть полезной |
|---|---|---|
| `rate_limit_hits_total` | «нас душат сами себя» — фронт/боты превышают burst | если стоит один фронт — почти не растёт |
| `http_errors_total{status_class=5xx}` | сервер падает | без разбивки по route не покажет где |
| `http_request_duration_seconds` p95/p99 | деградация | среднее врёт, нужны перцентили по route |
| `normalization_errors_total{field}` | качество данных / новые грязные алиасы | если поток задач мал — шум |
| `http_requests_total` RPS | нагрузка | без окна агрегации — просто счётчик |
| `summary_requests_total{status}` | живой ли дашборд-сводка | — |

### 7.4 Виджет на фронте
- **Состояние API:** up/down по `/health`.
- **Картинка по метрикам:** RPS (по окну), 5xx rate за 5 мин, p95 latency, `rate_limit_hits_total` (растёт → фронт сам себя душит), `normalization_errors_total` (растёт → новые грязные данные).
- **Токен heartbeat** (`TB-PULSE-…`) — в подвале страницы, крупно.
- **Алерт по порогу** [TBD: напр. 5xx rate > 1% за 5 мин → красный баннер на доске].

---

## 8. Деплой

- VPS: Ubuntu, `10.100.30.37`, «Создаётся», 1 CPU / 1.5GB / 10GB. [TBD: провайдер/цена/чек].
- Доступ: `http://IP` (HTTPS нет).
- Автоподъём: [TBD — systemd/compose].
- `DEPLOY.md` + скрипт одной командой: [TBD].
- Что всплыло на VPS: [TBD].

### 8.1 Что трогал в бэкенде и зачем
**Добавлено относительно исходной версии:**
- `normalization.py` — канонизация, числовые id, mojibake, парсер дат, estimate→часы, фильтры, сортировка, summary.
- `metrics.py` — counter/histogram, `/metrics` (Prometheus text) и `/api/v2/metrics/json`.
- `/api/v2/filters` — справочники для UI (со спец-элементами `UNKNOWN`/`FILTER_NONE`).
- `POST /api/v2/tasks` — фильтры/сортировка в теле (сложные фильтры не лезут в query).
- `POST /api/v2/summary` — сводка на сервере по тем же фильтрам.
- Детали задачи теперь отдают **`TaskDto`**, а не сырьё.
- `_load_json` с mtime-кэшем — не читать файлы на каждый запрос.
- `_route_label` — нормализация route для метрик (чтобы `/tasks/{id}` не плодил кардинальность).
- **Исправлены баги прошлой версии:** `total_pages = ceil(total/limit)` (было `+1`); `page=0` — первая страница; тело содержит `data` (для фронта) и `items` (обратная совместимость); `/health` снова отдаёт токен.
- **Параметры rate limit:** `BURST_CAP` поднят **6 → 15/сек**; окно 1.0 с.
- **Логирование:** структурное через `logger.get_logger`; медленные (>0.5с), 4xx, 5xx логируются.

**Известные дефекты (нашёл при ревью — в работе):**
- В `_normalized_tasks()` `result.append(dto)` стоит **вне** цикла `for t in raw_tasks` — вернётся только последняя задача. Критично, проверяю.
- В `_send` дублируется `body = json.dumps(...)`.
- `private`-проверка срабатывает только на детали, в ленте приватные не отфильтрованы — [TBD: скрывать в ленте].

---

## 9. Тесты и качество

- TS strict, `any` — с комментарием.
- Юнит-тесты на хрупкое: `parse_dt` (ISO/без зоны/сек/мс/мусор), дедлайны (overdue/due_soon/date_error, DONE≠overdue), пагинация (`page=0`, `total_pages`). [TBD: где].
- E2E / CI: [TBD].

---

## 10. Работа с ассистентами
| Где помогла модель | Что переписал руками | Почему её вариант не подошёл |
|---|---|---|
| [TBD] | [TBD] | [TBD] |

---

## 11. Что сделал бы иначе
1. [TBD] … 10. [TBD]

---

## 12. Открытые вопросы / долги
- [ ] Сверить с `CHANGELOG.md`.
- [ ] `caneld/canceled` → DONE или CANCELLED?
- [ ] Показывать оба поля срока при расхождении?
- [ ] Приватные задачи — скрывать в ленте?
- [ ] Починить `_normalized_tasks` (append вне цикла), дубль `body` в `_send`.
- [ ] Мониторинг: поднимать ли Prometheus+Grafana; порог алерта.
- [ ] VPS: провайдер, цена, чек.
- [ ] `Retry-After` на бэке?