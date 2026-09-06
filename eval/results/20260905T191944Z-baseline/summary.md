# Resultados de evaluación — `20260905T191944Z-baseline` (ablation: `baseline`)

## Global

- Intentos: 24
- Success rate: 58.3%
- Eficiencia media (calls / óptimo): 3.46×
- Latencia media: 26.4s

## Por dificultad

| Dificultad | n | Success rate | Eficiencia media |
|---|---:|---:|---:|
| easy | 3 | 100.0% | 2.00× |
| extreme | 9 | 11.1% | 11.25× |
| hard | 6 | 66.7% | 2.05× |
| medium | 6 | 100.0% | 1.47× |

## Por escenario

| Escenario | n | Success rate | Eficiencia media | Errores (por categoría) |
|---|---:|---:|---:|---|
| apartment-keys | 3 | 100.0% | 1.48× | sin_error=31 |
| backtracking-vault | 3 | 0.0% | n/d | — |
| color-locks | 3 | 100.0% | 1.45× | sin_error=48 |
| extreme-archive | 3 | 33.3% | 11.25× | sin_error=135 |
| library-search | 3 | 100.0% | 2.57× | sin_error=54 |
| office-sequence | 3 | 33.3% | 1.27× | sin_error=32, regla_del_mundo=1 |
| study-with-key | 3 | 100.0% | 2.00× | sin_error=18 |
| vault-combination | 3 | 0.0% | n/d | — |

## Taxonomía de errores (global)

- sin_error: 318
- herramienta_inexistente: 0
- argumentos_invalidos: 0
- regla_del_mundo: 1
- bug_inesperado: 0
