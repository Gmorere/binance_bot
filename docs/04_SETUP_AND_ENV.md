# 04 - Setup and Environment

## Stack auditado
- Python local auditado: `.venv` con `3.14.0`
- pandas `2.2.3`
- numpy `2.1.3`
- pyyaml `6.0.2`
- python-dateutil `2.9.0.post0`
- matplotlib `3.9.2`
- requests `2.32.3`

## Estado cloud confirmado
- `config/base.yaml` ya no usa rutas absolutas Windows.
- Los paths de `data/` y `outputs/` se resuelven desde la base del proyecto.
- Se pueden sobreescribir por entorno con `BOT_CONFIG_PATH`, `BOT_BASE_DIR`, `BOT_RAW_DATA_PATH`, `BOT_PROCESSED_DATA_PATH` y `BOT_OUTPUTS_PATH`.
- El repo incluye `Dockerfile`, `.dockerignore` y `render.yaml`.

## Instalacion local
```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Variables de entorno
El backtest y el paper local no requieren credenciales si operan sobre CSVs existentes.

Si se habilita refresh incremental desde Binance REST, el runtime usa endpoints publicos de market data y no necesita `BINANCE_API_KEY`.

Si mas adelante se habilitan chequeos de cuenta u ordenes reales, se debe completar `.env` a partir de `.env.example` con:
- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`

Variables cloud ya soportadas:
- `BOT_CONFIG_PATH`: ruta al YAML activo. Default: `config/base.yaml`.
- `BOT_BASE_DIR`: base dir para resolver paths relativos del YAML.
- `BOT_RAW_DATA_PATH`: override explicito de `data.raw_data_path`.
- `BOT_PROCESSED_DATA_PATH`: override explicito de `data.processed_data_path`.
- `BOT_OUTPUTS_PATH`: override explicito de `data.outputs_path`.

## Configuracion operativa relevante
```yaml
runtime:
  mode: backtest  # backtest | paper | live
  poll_interval_seconds: 15
  paper_risk_bucket: normal

data:
  raw_data_path: data/raw
  processed_data_path: data/processed
  outputs_path: outputs
  refresh_from_binance_rest: false
  candle_close_grace_seconds: 3

binance:
  use_testnet: true
  recv_window_ms: 5000
  timeout_seconds: 30
  market_data_limit: 500
```

## Archivos de deploy
- Config portable base: [config/base.yaml](/D:/binance_futures_bot/config/base.yaml)
- Config de Render paper: [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml)
- Blueprint Render: [render.yaml](/D:/binance_futures_bot/render.yaml)
- Imagen Docker: [Dockerfile](/D:/binance_futures_bot/Dockerfile)

## Que significa cada flag nueva
- `data.refresh_from_binance_rest`: si `true`, antes de cada snapshot de paper mode se refresca el CSV del timeframe de entrada desde Binance REST.
- `data.candle_close_grace_seconds`: segundos extra de espera despues del cierre teorico de la vela antes de permitir otro refresh REST.
- `binance.market_data_limit`: tamanio maximo de cada request de klines REST. Binance permite hasta `1500`.
- `binance.use_testnet`: hoy gobierna tambien la base URL usada por el refresh REST.

## Comandos locales utiles
```bash
# ejecutar backtest completo
.\.venv\Scripts\python.exe run_backtest.py

# ejecutar paper mode local
.\.venv\Scripts\python.exe run_paper.py

# ejecutar un solo ciclo de paper mode
.\.venv\Scripts\python.exe run_paper.py --once

# ejecutar N ciclos y salir
.\.venv\Scripts\python.exe run_paper.py --max-cycles 5

# bootstrap de historicos desde Binance Data
.\.venv\Scripts\python.exe scripts/download_binance_klines.py

# correr tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Render
- El deploy actual pensado es un `worker` con runtime Docker.
- Usa [render.yaml](/D:/binance_futures_bot/render.yaml).
- Usa [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml).
- Necesita disco persistente porque este bot escribe estado y datasets locales.
- Todavia no se puede aplicar desde este workspace porque no existe repo git/remoto.

## Fuente de datos
- Descarga historica bulk: `scripts/download_binance_klines.py`
- Refresh incremental para runtime: `src/data/binance_kline_updater.py`
- Servicio de polling actual: `src/live/market_data_runtime.py`
- Mercado actual: Binance USD-M futures
- Formato persistido: `data/raw/{SYMBOL}_{TIMEFRAME}.csv`
- Timeframe refrescado por runtime hoy: solo `15m`

## Limitaciones confirmadas
- El refresh REST incorpora solo velas cerradas.
- El servicio actual evita golpear REST antes del proximo cierre esperado de vela mas una gracia configurable.
- El runtime de paper sigue cargando solo el timeframe de entrada real que hoy usa la estrategia operable.
- `1h` y `4h` no se refrescan en runtime porque contexto/score todavia no gobiernan aperturas reales.
- Esto no reemplaza websocket ni user stream.

## Checklist de setup reproducible
- [ ] Config activa accesible via `BOT_CONFIG_PATH` o `config/base.yaml`
- [ ] Rutas resueltas correctamente en `data/` y `outputs/`
- [ ] Dataset base disponible en `data/raw` o refresh REST activo
- [ ] Tests corren en local o en contenedor
- [ ] Si se quiere paper mode, `runtime.mode` cambiado explicitamente a `paper`
- [ ] Si se quiere refresh automatico, `data.refresh_from_binance_rest=true`
- [ ] Si se quiere ajustar latencia post-close, revisar `data.candle_close_grace_seconds`
- [ ] Si se quiere Render, el repo debe existir en GitHub/GitLab/Bitbucket
