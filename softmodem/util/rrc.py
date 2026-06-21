import math

def rrc(alpha: float, samples_per_symbol: int, span: int) -> list[float]:
    n = span * samples_per_symbol + 1
    result: list[float] = []
    
    for i in range(n):
        ti = (i - ((n - 1) // 2)) / samples_per_symbol
        
        if ti == 0:
            h = 1 - alpha + (4 * alpha / math.pi)
        
        elif abs(ti) == 1 / (4 * alpha):
            h = (alpha / math.sqrt(2)) * (
                (1 + 2 / math.pi) * math.sin(math.pi / (4 * alpha))
                + (1 - 2 / math.pi) * math.cos(math.pi / (4 * alpha))
            )
        
        else:
            numerator = (
                math.sin(math.pi * ti * (1 - alpha))
                + 4 * alpha * ti * math.cos(math.pi * ti * (1 + alpha))
            )
            denominator = math.pi * ti * (1 - (4 * alpha * ti) ** 2)
            h = numerator / denominator
        
        result.append(h)

    return result
