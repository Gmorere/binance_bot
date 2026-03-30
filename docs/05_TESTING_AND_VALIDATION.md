# 05 — Testing and Validation

## Objetivo
Evitar refactors “bonitos” que rompan parciales, fees, PnL o trazabilidad.

## Estado auditado
- El repo no traía tests automáticos al inicio de esta auditoría.
- La prioridad mínima es cubrir simulación, métricas y smoke path del runner.

## Cobertura mínima requerida

### 1. Unit tests
- cálculo de fees,
- cálculo de pnl neto,
- parcial TP1 + cierre TP2,
- stop loss con gap adverso,
- prioridad conservadora del stop en vela ambigua,
- métricas agregadas básicas.

### 2. Integration / smoke tests
- runner sin señales,
- runner con dataframe válido y salida estable.

### 3. Regression tests
- comparar métricas clave antes/después de un refactor,
- verificar que el número de trades no cambie sin explicación,
- verificar que PnL y drawdown no salten arbitrariamente.

## Casos borde obligatorios
- dataframe vacío,
- columnas faltantes,
- NaNs en indicadores,
- capital inicial cero,
- señal inválida,
- fees nulos,
- fees extremos,
- vela con toque ambiguo entre stop y target.

## Comando de validación actual
```bash
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Criterios de aceptación de cambios
Un cambio pasa solo si:
- corre con la `.venv`,
- mantiene coherencia de PnL,
- no rompe tests existentes,
- actualiza documentación si cambia comportamiento,
- explica cualquier delta de métricas.
