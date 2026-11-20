# Task Board API v2

Справочник по HTTP API доски задач. Все ответы отдаются в JSON, кодировка UTF-8.

Базовый адрес: `http://0.0.0.0:7755`
Корень: `/api/v2`

Сервер по умолчанию принимает соединения на всех интерфейсах и отдаёт `Access-Control-Allow-Origin: *`, так что фронт можно поднимать на любом порту и даже на другом хосте.

Все таймстампы считаются в UTC.

## Аутентификация

Для внутренних методов хватает обычного GET без заголовков. Часть закрытых задач дополнительно требует служебный заголовок `X-Staff-Key`; ключ выдаёт саппорт-инструкция.

## Формат задачи

```json
{
  "id": "9f2c1b4e-7a55-4f0a-9d3e-1b2c3d4e5f60",
  "title": "На проде снова 502 после выкладки биллинга",
  "status": "todo",
  "priority": 2,
  "assignee_id": 19,
  "project_id": 5,
  "deadline": "2026-11-20",
  "created_at": 1760794620,
  "updated_at": 1760794620,
  "description": "В проде с 2025-09-18.",
  "tags": ["billing", "prod"]
}
```

| Поле | Тип | Описание |
|---|---|---|
| `id` | string | Идентификатор задачи, uuid |
| `title` | string | Заголовок, может содержать кавычки |
| `status` | string | `todo`, `doing` или `done` |
| `priority` | number | 1 (низкий), 2 (средний), 3 (высокий) |
| `assignee_id` | number \| null | id исполнителя, `null` если не назначено |
| `project_id` | number | id проекта |
| `deadline` | string \| null | дата срока в формате `YYYY-MM-DD` |
| `created_at` | number | unix-время в секундах |
| `updated_at` | number | unix-время в секундах |
| `description` | string | текст описания, бывает пустым |
| `tags` | string[] | список тегов |

## Список задач

```
GET /api/v2/tasks?page=0&limit=50&sort=-created
```

Параметры:

| Параметр | По умолчанию | Описание |
|---|---|---|
| `page` | 0 | номер страницы, с нуля |
| `limit` | 50 | сколько записей на страницу, максимум 200 |
| `sort` | `-created` | сортировка, минус значит по убыванию |

Ответ:

```json
{
  "data": [ { "id": "...", "title": "..." } ],
  "meta": { "page": 0, "per_page": 50, "total": 546 }
}
```

Полный ответ списка лежит в `examples/list.json`.

С клиента, если лень собирать запрос руками:

```js
const res = await fetch("http://0.0.0.0:7755/api/v2/tasks?page=0&limit=50");
const { data, meta } = await res.json();
for (const row of data) {
  const card = await fetch("http://0.0.0.0:7755/api/v2/tasks/" + row.id);
  const comments = await fetch(
    "http://0.0.0.0:7755/api/v2/tasks/" + row.id + "/comments?page=0"
  );
}
```

## Карточка задачи

```
GET /api/v2/tasks/{id}
```

Возвращает объект задачи целиком, со всеми полями и описанием.

## Комментарии

```
GET /api/v2/tasks/{id}/comments?page=0
```

```json
{
  "data": [
    {
      "id": 1,
      "task_id": 44,
      "author": "mkozlov",
      "created_at": 1760000000,
      "text": "старый комментарий из джиры: won't fix, customer happy"
    }
  ],
  "meta": { "page": 0, "per_page": 50, "total": 1142 }
}
```

## Смена статуса

```
POST /api/v2/tasks/{id}/status
```

Тело: `{ "status": "doing" }`. Возвращает обновлённую задачу.

## Поиск

```
GET /api/v2/search?q=биллинг
```

```json
{ "results": [ { "id": "...", "title": "..." } ] }
```

## Справочники

```
GET /api/v2/users
GET /api/v2/projects
```

```json
{ "users": [ { "id": 11, "name": "И. Петров", "login": "petrov@corp.local", "active": true } ] }
```

```json
{ "projects": [ { "id": 1, "slug": "billing", "title": "Биллинг" } ] }
```

## Живость сервиса

```
GET /health
```

```json
{ "status": "ok", "token": "TB-LIVE-8F2C41A7" }
```

Токен меняется при перезапуске сервиса, его имеет смысл показывать в интерфейсе: по нему видно, что поднялся свежий инстанс, а не закэшированный ответ.

## Заголовки

В каждом ответе есть:

| Заголовок | Значение |
|---|---|
| `X-RateLimit-Limit` | сколько запросов в секунду можно сделать подряд |
| `X-RateLimit-Remaining` | сколько осталось в текущем окне |

При превышении сервер отвечает `429` с телом `{ "error": "rate_limited" }`.
