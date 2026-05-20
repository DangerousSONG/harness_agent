# custom_tool

Workspace skill proposed from Chat request: 帮我写一个查询互联网的工具

## Inputs

- `city`: required city or region.
- `date`: optional date, defaults to `today`.
- `units`: `metric` or `imperial`.
- `language`: response language, defaults to `zh-CN`.

## Provider Requirements

- Configure the weather provider outside this asset.
- Read credentials from environment configuration at runtime.
- Do not write provider credentials into this repository, logs, or eval cases.

## Behavior

- Ask for `city` when it is missing.
- Return normalized weather data only when a configured provider succeeds.
- Explain provider failures without fabricating realtime weather.
