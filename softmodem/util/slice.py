SQRT_2 = 2 ** 0.5

def slicer_qpsk(sample: complex) -> complex:
    return complex(
        -1 if sample.real < 0 else 1,
        -1 if sample.imag < 0 else 1
    ) / SQRT_2

def slicer_qpsk_v22bis(sample: complex) -> complex:
    points = [
        complex(SQRT_2 / 2, SQRT_2 / 6),
        complex(-SQRT_2 / 6, SQRT_2 / 2),
        complex(-SQRT_2 / 2, -SQRT_2 / 6),
        complex(SQRT_2 / 6, -SQRT_2 / 2)
    ]

    return min(points, key=lambda z: abs(sample - z))

def single_axis_slicer(
    value: float,
    min: float,
    max: float,
    steps: int
) -> float:
    if value < min:
        return min
    
    elif value > max:
        return max
    
    else:
        amplitude = max - min
        progress = (value - min) / amplitude
        step = progress * (steps - 1)
        quantized = round(step)
        final = quantized * amplitude / (steps - 1) + min

        return final

def slicer_qam16(sample: complex) -> complex:
    return complex(
        single_axis_slicer(sample.real, -SQRT_2 / 2, SQRT_2 / 2, 4),
        single_axis_slicer(sample.imag, -SQRT_2 / 2, SQRT_2 / 2, 4)
    )
