def detector(level, raw, parameters):
    alpha = float(parameters.get("alpha", 0.7))
    if alpha > 1 or alpha < 0 :
        raise ValueError("alpha must be between 0 and 1")
    threshold = float(parameters["threshold"])
    
    raw.reverse()
    raw = [float(element) for element in raw]
    ema = raw[0]
    for value in raw[1:]:
        ema = alpha * value + (1-alpha) * ema
    result = 1 if ema < threshold else 0
    return result, ema
