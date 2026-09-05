# Resultados de evaluación — `20260901T004440Z-baseline` (ablation: `baseline`)

## Global

- Intentos: 8
- Success rate: 12.5%
- Eficiencia media (calls / óptimo): 1.43×
- Latencia media: 51.3s

## Por dificultad

| Dificultad | n | Success rate | Eficiencia media |
|---|---:|---:|---:|
| easy | 1 | 100.0% | 1.33× |
| extreme | 3 | 0.0% | 0.90× |
| hard | 2 | 0.0% | 1.81× |
| medium | 2 | 0.0% | 1.88× |

## Por escenario

| Escenario | n | Success rate | Eficiencia media | Errores (por categoría) |
|---|---:|---:|---:|---|
| apartment-keys | 1 | 0.0% | 2.86× | sin_error=15, regla_del_mundo=5 |
| backtracking-vault | 1 | 0.0% | 0.67× | sin_error=8, regla_del_mundo=4 |
| color-locks | 1 | 0.0% | 0.91× | sin_error=8, regla_del_mundo=2 |
| extreme-archive | 1 | 0.0% | 1.50× | sin_error=6 |
| library-search | 1 | 0.0% | 2.86× | sin_error=13, regla_del_mundo=7 |
| office-sequence | 1 | 0.0% | 0.77× | sin_error=6, regla_del_mundo=4 |
| study-with-key | 1 | 100.0% | 1.33× | sin_error=4 |
| vault-combination | 1 | 0.0% | 0.52× | sin_error=10, regla_del_mundo=1 |

## Taxonomía de errores (global)

- sin_error: 70
- herramienta_inexistente: 0
- argumentos_invalidos: 0
- regla_del_mundo: 23
- bug_inesperado: 0
