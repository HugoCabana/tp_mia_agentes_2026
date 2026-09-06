# Resultados de evaluación — `20260905T202845Z-tight_max_iterations` (ablation: `tight_max_iterations`)

## Global

- Intentos: 24
- Success rate: 16.7%
- Eficiencia media (calls / óptimo): 1.72×
- Latencia media: 22.7s

## Por dificultad

| Dificultad | n | Success rate | Eficiencia media |
|---|---:|---:|---:|
| easy | 3 | 100.0% | 2.00× |
| extreme | 9 | 0.0% | 2.23× |
| hard | 6 | 16.7% | 1.43× |
| medium | 6 | 0.0% | 1.10× |

## Por escenario

| Escenario | n | Success rate | Eficiencia media | Errores (por categoría) |
|---|---:|---:|---:|---|
| apartment-keys | 3 | 0.0% | 1.19× | sin_error=25 |
| backtracking-vault | 3 | 0.0% | 0.56× | sin_error=30 |
| color-locks | 3 | 0.0% | 1.00× | sin_error=33 |
| extreme-archive | 3 | 0.0% | 5.67× | sin_error=66, regla_del_mundo=2 |
| library-search | 3 | 33.3% | 2.19× | sin_error=46 |
| office-sequence | 3 | 0.0% | 0.67× | sin_error=26 |
| study-with-key | 3 | 100.0% | 2.00× | sin_error=18 |
| vault-combination | 3 | 0.0% | 0.48× | sin_error=30 |

## Taxonomía de errores (global)

- sin_error: 274
- herramienta_inexistente: 0
- argumentos_invalidos: 0
- regla_del_mundo: 2
- bug_inesperado: 0
