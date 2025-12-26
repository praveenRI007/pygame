import random

class Perlin2D:
    def __init__(self, seed=None):
        self.seed = seed if seed is not None else random.randrange(0, 2**31)
        rnd = random.Random(self.seed)
        self.perm = list(range(256))
        rnd.shuffle(self.perm)
        self.perm *= 2

    @staticmethod
    def fade(t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    @staticmethod
    def lerp(a, b, t):
        return a + t * (b - a)

    @staticmethod
    def grad(h, x, y):
        h &= 7
        if h == 0: return x + y
        if h == 1: return -x + y
        if h == 2: return x - y
        if h == 3: return -x - y
        if h == 4: return x
        if h == 5: return -x
        if h == 6: return y
        return -y

    def noise(self, x, y):
        xi = int(x) & 255
        yi = int(y) & 255
        xf = x - int(x)
        yf = y - int(y)
        u = self.fade(xf)
        v = self.fade(yf)
        aa = self.perm[self.perm[xi] + yi]
        ab = self.perm[self.perm[xi] + yi + 1]
        ba = self.perm[self.perm[xi + 1] + yi]
        bb = self.perm[self.perm[xi + 1] + yi + 1]
        x1 = self.lerp(self.grad(aa, xf, yf), self.grad(ba, xf - 1, yf), u)
        x2 = self.lerp(self.grad(ab, xf, yf - 1), self.grad(bb, xf - 1, yf - 1), u)
        return self.lerp(x1, x2, v)

    def fractal(self, x, y, octaves=5, lac=2.0, gain=0.5):
        total = 0
        amp = 1
        freq = 1
        max_amp = 0
        for _ in range(octaves):
            total += self.noise(x * freq, y * freq) * amp
            max_amp += amp
            amp *= gain
            freq *= lac
        return total / max_amp
