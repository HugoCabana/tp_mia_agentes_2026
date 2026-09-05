# Resultados de evaluación — `20260905T200830Z-low_history_budget` (ablation: `low_history_budget`)

## Global

- Intentos: 24
- Success rate: 37.5%
- Eficiencia media (calls / óptimo): 3.41×
- Latencia media: 47.9s

## Por dificultad

| Dificultad | n | Success rate | Eficiencia media |
|---|---:|---:|---:|
| easy | 3 | 100.0% | 3.56× |
| extreme | 9 | 11.1% | 4.06× |
| hard | 6 | 50.0% | 2.88× |
| medium | 6 | 33.3% | 2.87× |

## Por escenario

| Escenario | n | Success rate | Eficiencia media | Errores (por categoría) |
|---|---:|---:|---:|---|
| apartment-keys | 3 | 66.7% | 2.81× | sin_error=57, regla_del_mundo=2 |
| backtracking-vault | 3 | 0.0% | 1.33× | sin_error=71, regla_del_mundo=1 |
| color-locks | 3 | 0.0% | 2.94× | sin_error=94, regla_del_mundo=3 |
| extreme-archive | 3 | 33.3% | 9.75× | sin_error=115, regla_del_mundo=2 |
| library-search | 3 | 100.0% | 4.10× | sin_error=86 |
| office-sequence | 3 | 0.0% | 1.67× | sin_error=65 |
| study-with-key | 3 | 100.0% | 3.56× | sin_error=31, regla_del_mundo=1 |
| vault-combination | 3 | 0.0% | 1.10× | sin_error=69 |

## Taxonomía de errores (global)

- sin_error: 588
- herramienta_inexistente: 0
- argumentos_invalidos: 0
- regla_del_mundo: 9
- bug_inesperado: 0
