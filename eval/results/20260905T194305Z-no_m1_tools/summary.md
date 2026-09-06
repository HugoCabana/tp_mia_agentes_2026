# Resultados de evaluación — `20260905T194305Z-no_m1_tools` (ablation: `no_m1_tools`)

## Global

- Intentos: 24
- Success rate: 75.0%
- Eficiencia media (calls / óptimo): 2.24×
- Latencia media: 38.5s

## Por dificultad

| Dificultad | n | Success rate | Eficiencia media |
|---|---:|---:|---:|
| easy | 3 | 100.0% | 2.00× |
| extreme | 9 | 33.3% | 2.90× |
| hard | 6 | 100.0% | 2.08× |
| medium | 6 | 100.0% | 1.54× |

## Por escenario

| Escenario | n | Success rate | Eficiencia media | Errores (por categoría) |
|---|---:|---:|---:|---|
| apartment-keys | 3 | 100.0% | 1.62× | sin_error=33, regla_del_mundo=1 |
| backtracking-vault | 3 | 0.0% | 1.31× | sin_error=71 |
| color-locks | 3 | 100.0% | 1.45× | sin_error=48 |
| extreme-archive | 3 | 100.0% | 6.33× | sin_error=75, regla_del_mundo=1 |
| library-search | 3 | 100.0% | 2.57× | sin_error=54 |
| office-sequence | 3 | 100.0% | 1.59× | sin_error=60, regla_del_mundo=2 |
| study-with-key | 3 | 100.0% | 2.00× | sin_error=18 |
| vault-combination | 3 | 0.0% | 1.05× | sin_error=66 |

## Taxonomía de errores (global)

- sin_error: 425
- herramienta_inexistente: 0
- argumentos_invalidos: 0
- regla_del_mundo: 4
- bug_inesperado: 0
