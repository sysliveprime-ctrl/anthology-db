# Anthology DB Update Channel

Этот репозиторий является рабочим центром Anthology DB update channel.

Он хранит `db_version.json`, release-helper scripts и правила публикации DB.
Большие `.xdb` и `.db` файлы не хранятся в Git: они загружаются в GitHub Release
как assets.

## Как Это Работает Для Игрока

Лаунчер читает:

```text
https://github.com/sysliveprime-ctrl/anthology-db/blob/main/db_version.json
```

Затем он:

1. сравнивает локальные DB-файлы по размеру и SHA-256;
2. скачивает только отсутствующие или изменённые файлы;
3. удаляет лишние DB-архивы из `db/configs` и `db/mods`, если их нет в
   манифесте;
4. сохраняет локальное состояние в `webcache\db_update\db_state.json`.

Git игрокам не нужен.

## Манифест

Пример `db_version.json`:

```json
{
  "version": "2026.05.25.3",
  "mode": "mirror",
  "base_url": "https://github.com/sysliveprime-ctrl/anthology-db/releases/download/2026.05.25.3/",
  "files": [
    {
      "path": "db/configs/configs_anthology.xdb0",
      "asset_name": "db_configs_configs_anthology.xdb0",
      "size": 12496512,
      "sha256": "..."
    }
  ],
  "notes": "Описание обновления"
}
```

`mode = mirror` означает, что локальные DB-архивы, отсутствующие в манифесте,
будут удалены.

## Источники DB

Манифест собирается не из репозитория, а из живой папки игры:

```text
D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\configs
D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\mods
```

## Релиз DB

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py workgit --version YYYY.MM.DD.N --notes "Описание обновления"
```

Скрипт:

1. сканирует живые DB-папки;
2. пересобирает `db_version.json`;
3. коммитит и пушит `main`;
4. создаёт или обновляет GitHub Release с тегом версии;
5. загружает DB-файлы как release assets.

## Связанные Репозитории

```text
launcher repo:  E:\dev\Anthology-Work-Git\projects\AnthologyLauncher
modpack repo:   D:\Games\ANTHOLOGY\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT\mods
engine repo:    E:\dev\xray-monolith
source repo:    E:\dev\anomaly-codex-main\ai_workspace\Source_Anthology
```

Публичные репозитории:

- `sysliveprime-ctrl/AnthologyLauncher`
- `sysliveprime-ctrl/anthology-mo2-modpack`
- `sysliveprime-ctrl/anthology-db`
- `sysliveprime-ctrl/xray-monolith`
- `sysliveprime-ctrl/anthology-source`

`anthology-source` хранит source snapshot для сопровождения и ревью. Лаунчер
его не скачивает и не использует как update channel.

## Release Helper

Источник правил релиза находится здесь:

```text
skills\anthology-release-ops
```

Не поддерживать отдельную копию под `C:\Users\parti\.codex\skills`. Там может
быть только discovery pointer.

## Правила

- Не хранить DB-архивы в Git.
- Не заливать нулевые release assets: GitHub их отклоняет.
- После релиза проверять GitHub contents API, а не только raw URL.
- Тестовые файлы `anthology_release_*` не должны попадать в манифест.
