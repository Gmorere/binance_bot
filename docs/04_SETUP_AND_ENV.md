# 04 - Setup and Environment

## Stack auditado
- Python local auditado: `.venv` con `3.14.0`
- pandas `2.2.3`
- numpy `2.1.3`
- pyyaml `6.0.2`
- python-dateutil `2.9.0.post0`
- matplotlib `3.9.2`
- requests `2.32.3`

## Estado portable confirmado
- [config/base.yaml](/D:/binance_futures_bot/config/base.yaml) ya no usa rutas absolutas Windows.
- Los paths de `data/` y `outputs/` se resuelven desde la base del proyecto.
- Se pueden sobreescribir por entorno con:
  - `BOT_CONFIG_PATH`
  - `BOT_BASE_DIR`
  - `BOT_RAW_DATA_PATH`
  - `BOT_PROCESSED_DATA_PATH`
  - `BOT_OUTPUTS_PATH`
- El repo incluye artefactos cloud listos:
  - [Dockerfile](/D:/binance_futures_bot/Dockerfile)
  - [.dockerignore](/D:/binance_futures_bot/.dockerignore)
  - [render.yaml](/D:/binance_futures_bot/render.yaml)

## Instalacion local
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Variables de entorno
Backtest y paper local no requieren credenciales si operan sobre CSVs existentes.

Si se habilita refresh incremental desde Binance REST para market data publica, no hace falta `BINANCE_API_KEY`.

Si mas adelante se habilitan chequeos de cuenta u ordenes reales, se debe completar `.env` a partir de [.env.example](/D:/binance_futures_bot/.env.example) con:
- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`

Variables cloud ya soportadas:
- `BOT_CONFIG_PATH`: YAML activo. Default: `config/base.yaml`
- `BOT_BASE_DIR`: base dir para resolver paths relativos del YAML
- `BOT_RAW_DATA_PATH`: override explicito de `data.raw_data_path`
- `BOT_PROCESSED_DATA_PATH`: override explicito de `data.processed_data_path`
- `BOT_OUTPUTS_PATH`: override explicito de `data.outputs_path`

## Configuracion operativa relevante
```yaml
strategy:
  name: continuation_breakout_core_v3
  dynamic_risk_by_score:
    enabled: true
    preserve_symbol_base_risk: true
  backtest_policy:
    enabled: true
    enforce_context_alignment: true
    excluded_symbols: [BNBUSDT, SOLUSDT, XRPUSDT]
    allowed_sides:
      BTCUSDT: [SHORT]
      ETHUSDT: [SHORT]

score_thresholds:
  min_trade: 75
  aggressive: 85
  exceptional: 93

filters:
  stop_buffer_atr_fraction: 0.10
  min_breakout_volume_multiple: 1.0
  max_consolidation_range_atr_multiple: 1.2
  max_trigger_candle_atr_multiple: 1.6
  by_symbol:
    BTCUSDT:
      max_consolidation_range_atr_multiple: 1.2
    ETHUSDT:
      max_consolidation_range_atr_multiple: 1.4

trade_management:
  max_bars_in_trade: 24
  by_symbol:
    BTCUSDT:
      max_bars_in_trade: 16
    ETHUSDT:
      max_bars_in_trade: 32

position_limits:
  max_notional_pct:
    BTCUSDT: 0.80
    ETHUSDT: 0.90

execution:
  fee_rate_entry: 0.0004
  fee_rate_exit: 0.0004
  slippage:
    BTCUSDT: 0.0002
    ETHUSDT: 0.0003

risk:
  backtest_by_symbol:
    ETHUSDT:
      risk_pct: 0.0100

runtime:
  mode: backtest  # backtest | paper | live
  poll_interval_seconds: 15
  backtest_risk_bucket: strong
  paper_risk_bucket: strong

data:
  raw_data_path: data/raw
  processed_data_path: data/processed
  outputs_path: outputs
  refresh_from_binance_rest: false
  candle_close_grace_seconds: 3

binance:
  use_testnet: true
  use_testnet_market_data: false
  recv_window_ms: 5000
  timeout_seconds: 30
  market_data_limit: 500
  rest_max_retries: 2
  rest_retry_backoff_ms: 1000
```

## Archivos de deploy
- Config portable base: [config/base.yaml](/D:/binance_futures_bot/config/base.yaml)
- Config experimental XRP: [config/research.xrp_long.yaml](/D:/binance_futures_bot/config/research.xrp_long.yaml)
- Config experimental ETH breakout+pullback: [config/research.eth_pullback.yaml](/D:/binance_futures_bot/config/research.eth_pullback.yaml)
- Config de Render paper: [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml)
- Blueprint Render: [render.yaml](/D:/binance_futures_bot/render.yaml)
- Imagen Docker: [Dockerfile](/D:/binance_futures_bot/Dockerfile)

## Significado de las flags operativas
- `runtime.backtest_risk_bucket`: bucket fijo de riesgo para el backtest actual. Default operativo del `core`: `strong`.
- `runtime.paper_risk_bucket`: bucket fijo de riesgo para paper mode. En el `core` alineado vigente: `strong`.
- `strategy.dynamic_risk_by_score.enabled`: si `true`, backtest y paper resuelven el score del setup antes del sizing. Live todavia no lo consume.
- `strategy.dynamic_risk_by_score.preserve_symbol_base_risk`: si `true`, el score no puede bajar el `risk_pct` por debajo del baseline research ya validado por simbolo.
- `score_thresholds.min_trade`: bloquea setups por debajo del minimo antes del sizing. En el `core` vigente esta en `75` para eliminar setups flojos que no justifican capital.
- `risk.backtest_by_symbol`: override research por simbolo reutilizado hoy por backtest y paper para mantener alineacion economica del `core`. En el setup vigente, `ETHUSDT` corre con `risk_pct = 0.0100` aunque el bucket base siga siendo `strong = 0.0085`.
- `strategy.backtest_policy.enabled`: activa el gating research adicional en backtest.
- `strategy.backtest_policy.enforce_context_alignment`: exige que el breakout coincida con el sesgo `4h/1h`.
- `strategy.backtest_policy.excluded_symbols`: saca simbolos completos del research actual.
- `strategy.backtest_policy.allowed_sides`: restringe los lados permitidos por simbolo en backtest.
- `filters.by_symbol`: permite overrides parciales de filtros research por simbolo sin duplicar el bloque global.
- `filters.stop_buffer_atr_fraction`: buffer ATR usado para construir el stop inicial del setup. Ya no viene hardcodeado desde el runner y puede heredarse o overridearse por simbolo via `filters.by_symbol`.
- `trade_management.max_bars_in_trade`: timeout global de backtest si un trade no cierra antes.
- `trade_management.by_symbol`: override por simbolo para la ventana maxima del trade en research.
- `position_limits.max_notional_pct`: cap maximo de notional por simbolo como porcentaje del capital de referencia. En el `core` vigente, `ETHUSDT` ya pesa mas que `BTCUSDT`.
- `execution.slippage`: slippage adverso simple por simbolo. Ya se aplica en backtest y paper tanto en entrada como en salidas normales. Los stops con gap siguen usando el open adverso y no duplican castigo con otro slippage encima.
- `data.refresh_from_binance_rest`: si `true`, antes de cada snapshot de paper mode se refresca el CSV del timeframe de entrada desde Binance REST.
- `data.candle_close_grace_seconds`: segundos extra de espera despues del cierre teorico de la vela antes de permitir otro refresh REST.
- `binance.market_data_limit`: tamanio maximo de cada request de klines REST. Binance permite hasta `1500`.
- `binance.rest_max_retries`: reintentos maximos del refresh REST ante errores transitorios (`429/5xx` o fallos de red). No reintenta errores no transitorios como `451`.
- `binance.rest_retry_backoff_ms`: backoff base en milisegundos para reintentos REST. Se aplica exponencial (`base * 2^n`).
- `binance.use_testnet`: gobierna el cliente Binance para account/orders.
- `binance.use_testnet_market_data`: permite separar el feed de market data del path de ordenes. Default recomendado para paper: `false`, asi el paper usa velas reales de produccion aunque el cliente Binance siga en testnet.

## Comandos locales utiles
```bash
.\.venv\Scripts\python.exe run_backtest.py
.\.venv\Scripts\python.exe run_backtest.py --symbols BTCUSDT ETHUSDT
.\.venv\Scripts\python.exe run_backtest.py  # core v3 por default
$env:BOT_CONFIG_PATH="config/research.xrp_long.yaml"; .\.venv\Scripts\python.exe run_backtest.py
$env:BOT_CONFIG_PATH="config/research.eth_pullback.yaml"; .\.venv\Scripts\python.exe run_backtest.py
.\.venv\Scripts\python.exe run_paper.py
.\.venv\Scripts\python.exe run_paper.py --once
$env:BOT_CONFIG_PATH="config/render.paper.yaml"; .\.venv\Scripts\python.exe run_paper.py --once
.\.venv\Scripts\python.exe run_paper.py --max-cycles 5
.\.venv\Scripts\python.exe scripts\download_binance_klines.py
.\.venv\Scripts\python.exe scripts\rebuild_backtest_baseline.py
.\.venv\Scripts\python.exe scripts\analyze_backtest_baseline.py
.\.venv\Scripts\python.exe scripts\validate_eth_pullback_walkforward.py --freq quarterly
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Smoke minimo de paper alineado al core
Si queres verificar el path operativo de `paper` con el mismo gating research y score dinamico del `core`, el smoke minimo hoy es:

```bash
$env:BOT_CONFIG_PATH="config/render.paper.yaml"
.\.venv\Scripts\python.exe run_paper.py --once
```

Lo que deberia quedar claro en logs y estado:
- usa `BTCUSDT` y `ETHUSDT` solamente,
- aplica `SHORT` only con gating `4h/1h`,
- usa `runtime.paper_risk_bucket=strong` como base,
- puede bloquear setups por score bajo antes del sizing,
- cuando abre, persiste `risk_bucket` en `outputs/paper/paper_state.json`.

## Fuente de datos
- Descarga historica bulk: [download_binance_klines.py](/D:/binance_futures_bot/scripts/download_binance_klines.py)
- Refresh incremental para runtime: [binance_kline_updater.py](/D:/binance_futures_bot/src/data/binance_kline_updater.py)
- Servicio de polling actual: [market_data_runtime.py](/D:/binance_futures_bot/src/live/market_data_runtime.py)
- Mercado soportado hoy: Binance USD-M futures
- Formato persistido: `data/raw/{SYMBOL}_{TIMEFRAME}.csv`
- Timeframes que el runtime puede refrescar hoy: `15m`, `1h`, `4h` si estan configurados

## Render
- El deploy actual pensado es un `worker` con runtime Docker.
- Usa [render.yaml](/D:/binance_futures_bot/render.yaml).
- Usa [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml).
- Necesita disco persistente porque escribe estado y datasets locales.
- El bloqueo "falta repo remoto" ya no aplica. El paso pendiente es aplicar y validar el worker en Render.

## Limitaciones confirmadas
- El refresh REST incorpora solo velas cerradas.
- El servicio actual evita golpear REST antes del proximo cierre esperado de vela mas una gracia configurable.
- Paper mode ya puede cargar `1h` y `4h` para aplicar el mismo gating research de contexto/lado que usa el backtest.
- El slippage actual es un modelo simple y adverso por simbolo; no modela libro, profundidad ni latencia intrabar real.
- El score ya gobierna riesgo en backtest y paper cuando la config lo habilita; todavia no gobierna live.
- Esto no reemplaza websocket ni user stream.

## Checklist de setup reproducible
- [x] Config activa accesible via `BOT_CONFIG_PATH` o `config/base.yaml`
- [x] Rutas resueltas correctamente en `data/` y `outputs/`
- [x] El repo ya soporta overrides por entorno para cloud
- [x] Existe `Dockerfile` portable
- [x] Existe `render.yaml`
- [x] Existe salida reproducible de baseline consolidada por corrida
- [ ] Dataset base disponible en `data/raw` o refresh REST activo en el entorno objetivo
- [ ] Tests corren en el entorno objetivo
- [ ] Si se quiere paper mode, `runtime.mode` cambiado explicitamente a `paper`
- [ ] Si se quiere refresh automatico, `data.refresh_from_binance_rest=true`
- [ ] Si se quiere Render, worker aplicado y validado en Dashboard
