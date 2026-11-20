# Кандидату

Сначала `TASK.md`. Рядом `CHANGELOG.md`, `docs/api.md`, `openapi.yaml`, мок и `data/`.

Мок на голом Python, зависимостей нет:

```bash
python3 mock_server.py
```

Порт по умолчанию 7755, другой: `python3 mock_server.py 8801`.

Контракт HTTP: `docs/api.md`. Схема: `openapi.yaml`. Пример списка, как в вики: `examples/list.json`. Мок нужен чтобы поднять стенд, это не спецификация.

Проверка, что порт отвечает:

```bash
curl "http://127.0.0.1:7755/api/v2/tasks?page=0&limit=50"
```
# TaskBoard
## Запуск локально
1. Бэк:
   ```bash
   python3 mock_server.py 7755
Фронт:
```bash
ng build
```
Открыть http://localhost:4200
