# Resultados de evaluación — `20260901T003338Z-baseline` (ablation: `baseline`)

## Global

- Intentos: 8
- Success rate: 12.5%
- Eficiencia media (calls / óptimo): 1.81×
- Latencia media: 31.7s

## Por dificultad

| Dificultad | n | Success rate | Eficiencia media |
|---|---:|---:|---:|
| easy | 1 | 100.0% | 3.00× |
| extreme | 3 | 0.0% | 0.42× |
| hard | 2 | 0.0% | 2.43× |
| medium | 2 | 0.0% | 2.69× |

## Por escenario

| Escenario | n | Success rate | Eficiencia media | Errores (por categoría) |
|---|---:|---:|---:|---|
| apartment-keys | 1 | 0.0% | 3.57× | sin_error=4, argumentos_invalidos=20, regla_del_mundo=1 |
| backtracking-vault | 1 | 0.0% | 0.06× | sin_error=1 |
| color-locks | 1 | 0.0% | 1.82× | sin_error=17, argumentos_invalidos=3 |
| extreme-archive | 1 | 0.0% | 0.25× | regla_del_mundo=1 |
| library-search | 1 | 0.0% | 2.86× | sin_error=9, argumentos_invalidos=3, regla_del_mundo=8 |
| office-sequence | 1 | 0.0% | 2.00× | sin_error=6, argumentos_invalidos=12, regla_del_mundo=8 |
| study-with-key | 1 | 100.0% | 3.00× | sin_error=6, argumentos_invalidos=3 |
| vault-combination | 1 | 0.0% | 0.95× | sin_error=13, argumentos_invalidos=2, regla_del_mundo=5 |

## Taxonomía de errores (global)

- sin_error: 56
- herramienta_inexistente: 0
- argumentos_invalidos: 43
- regla_del_mundo: 23
- bug_inesperado: 0
