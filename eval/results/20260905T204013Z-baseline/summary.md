# Resultados de evaluación — `20260905T204013Z-baseline` (ablation: `baseline`)

## Global

- Intentos: 8
- Success rate: 75.0%
- Eficiencia media (calls / óptimo): 2.25×
- Latencia media: 36.3s

## Por dificultad

| Dificultad | n | Success rate | Eficiencia media |
|---|---:|---:|---:|
| easy | 1 | 100.0% | 2.00× |
| extreme | 3 | 33.3% | 2.88× |
| hard | 2 | 100.0% | 2.09× |
| medium | 2 | 100.0% | 1.58× |

## Por escenario

| Escenario | n | Success rate | Eficiencia media | Errores (por categoría) |
|---|---:|---:|---:|---|
| apartment-keys | 1 | 100.0% | 1.43× | sin_error=10 |
| backtracking-vault | 1 | 0.0% | 1.33× | sin_error=24 |
| color-locks | 1 | 100.0% | 1.73× | sin_error=19 |
| extreme-archive | 1 | 100.0% | 6.25× | sin_error=25 |
| library-search | 1 | 100.0% | 2.57× | sin_error=18 |
| office-sequence | 1 | 100.0% | 1.62× | sin_error=20, regla_del_mundo=1 |
| study-with-key | 1 | 100.0% | 2.00× | sin_error=6 |
| vault-combination | 1 | 0.0% | 1.05× | sin_error=22 |

## Taxonomía de errores (global)

- sin_error: 144
- herramienta_inexistente: 0
- argumentos_invalidos: 0
- regla_del_mundo: 1
- bug_inesperado: 0
