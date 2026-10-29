"""Colorimetría + estelas de luz para el video "auto en consignación".

Por cada cuadro del video fuente (work/src/NNNN.png):
1. Grade: levanta exposición, curva de contraste fílmica, vibrance y split-toning
   (sombras frías / altas luces cálidas) para que se vea más vivo.
2. Máscara del auto (píxeles azules rellenados fila por fila) para que las estelas
   pasen por detrás del auto y no por encima.
3. Estelas de las luces de la calle: zoom-blur radial de las altas luces desde el
   punto de fuga, teñidas cálidas.
4. Estelas de velocidad sintéticas, de un solo color (blanco cálido) y muy
   desenfocadas, que salen del punto de fuga y aceleran hacia los bordes, más un
   zoom-blur del fondo hacia los bordes para dar sensación de velocidad.
5. Bloom + destello anamórfico en los faros.

Uso: python3 fx.py [cuadro]   (sin argumento procesa todos → work/bg/NNNN.jpg)
"""
import os
import sys
from multiprocessing import Pool

import cv2
import numpy as np

DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(DIR, 'work', 'src')
DST = os.path.join(DIR, 'work', 'bg')
FPS = 24
W, H = 1080, 1920
VP = (540.0, 590.0)          # punto de fuga de la calle
BLACK_FROM = 1330            # desde acá el fuente ya es negro (zona de textos)

STREAK = np.array([215, 235, 255], np.float32) / 255   # blanco cálido (BGR)


def grade(img):
    x = img.astype(np.float32) / 255
    x = x * 1.6 + 0.01                                   # exposición
    x = x / (1 + 0.55 * x)                                 # hombro suave para altas luces
    x = np.clip(x, 0, 1)
    # Curva S (contraste)
    x = x + 0.9 * (x - x * x) * (2 * x - 1)
    x = np.clip(x, 0, 1)
    lum = x @ np.array([0.0722, 0.7152, 0.2126], np.float32)    # BGR
    lum3 = lum[..., None]
    # Vibrance: más saturación a lo que está poco saturado
    sat = x.max(-1, keepdims=True) - x.min(-1, keepdims=True)
    amt = 1.75 - 0.6 * np.clip(sat * 2, 0, 1)
    x = lum3 + (x - lum3) * amt
    # Split toning: sombras teal, altas luces ámbar
    sh = np.clip(1 - lum3 * 2.2, 0, 1)
    hi = np.clip((lum3 - 0.45) * 1.8, 0, 1)
    x = x + sh * np.array([0.035, 0.018, -0.02], np.float32) + hi * np.array([-0.06, 0.01, 0.06], np.float32)
    return np.clip(x, 0, 1)


def car_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    blue = ((hsv[..., 0] > 92) & (hsv[..., 0] < 128) & (hsv[..., 1] > 90) & (hsv[..., 2] > 45)).astype(np.uint8)
    blue[:, :60] = 0
    blue[:, -60:] = 0
    blue = cv2.morphologyEx(blue, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = np.zeros_like(blue)
    rows = np.where(blue.sum(1) > 25)[0]
    for y in rows:
        xs = np.where(blue[y])[0]
        if xs[-1] - xs[0] > 80:
            m[y, xs[0]:xs[-1] + 1] = 1
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    if rows.size:   # el techo/parabrisas oscuro: cerrar hasta arriba del todo lo azul
        top = rows.min()
        m[max(top - 10, 0):top] = m[top]
    m = cv2.dilate(m, np.ones((25, 25), np.uint8))
    return cv2.GaussianBlur(m.astype(np.float32), (0, 0), 10)


def zoom_blur(layer, steps=28, amount=0.38):
    acc = np.zeros_like(layer)
    for i in range(steps):
        s = 1 + amount * i / (steps - 1)
        M = np.float32([[s, 0, VP[0] * (1 - s) / 2], [0, s, VP[1] * (1 - s) / 2]])
        acc += cv2.warpAffine(layer, M, (layer.shape[1], layer.shape[0]), flags=cv2.INTER_LINEAR) * (1 - i / steps)
    return acc / steps * 2.2


def speed_blur(img, steps=16, amount=0.10):
    """Zoom-blur normalizado de todo el cuadro (para mezclar hacia los bordes)."""
    acc = np.zeros_like(img)
    for i in range(steps):
        s = 1 + amount * i / (steps - 1)
        M = np.float32([[s, 0, VP[0] / 2 * (1 - s)], [0, s, VP[1] / 2 * (1 - s)]])
        acc += cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return acc / steps


def streak_layer(t):
    """Estelas de velocidad a media resolución, deterministas por tiempo."""
    h, w = H // 2, W // 2
    core = np.zeros((h, w), np.float32)
    vp = (VP[0] / 2, VP[1] / 2)
    rng = np.random.default_rng(7)
    for k in range(28):
        side = 1 if k % 2 else -1
        ang = np.deg2rad(rng.uniform(-36, 26))            # + = hacia abajo
        period = rng.uniform(0.6, 1.1)
        phase = rng.uniform(0, period)
        bright = rng.uniform(0.45, 1.0)
        u = ((t + phase) % period) / period              # 0→1 recorrido
        r0 = 80 * np.exp(3.2 * u)                         # acelera en perspectiva
        r1 = r0 * (2.3 + 1.6 * u)
        if r0 > 700:
            continue
        d = np.array([np.cos(ang) * side, np.sin(ang)])
        p0 = (vp[0] + d[0] * r0, vp[1] + d[1] * r0)
        p1 = (vp[0] + d[0] * r1, vp[1] + d[1] * r1)
        thick = max(2, int(2 + r0 / 30))
        fade = min(1, u * 5) * (1 - u ** 2) * bright
        cv2.line(core, (int(p0[0] * 16), int(p0[1] * 16)), (int(p1[0] * 16), int(p1[1] * 16)),
                 float(fade), thick, cv2.LINE_AA, shift=4)
    soft = cv2.GaussianBlur(core, (0, 0), 7) * 0.9 + cv2.GaussianBlur(core, (0, 0), 22) * 1.6
    return cv2.resize(soft, (W, H), interpolation=cv2.INTER_LINEAR)[..., None] * STREAK


def process(i):
    src = cv2.imread(os.path.join(SRC, f'{i:04d}.png'))
    t = (i - 1) / FPS
    x = grade(src)
    car = car_mask(src)[..., None]
    behind = 1 - car
    yy = np.arange(H, dtype=np.float32)[:, None, None]
    vfade = np.clip((BLACK_FROM - 60 - yy) / 260, 0, 1) * np.clip((yy - 150) / 120, 0, 1)

    # 0) Zoom-blur del fondo, creciente hacia los bordes y detrás del auto
    yy2, xx2 = np.mgrid[0:H, 0:W].astype(np.float32)
    dist = np.hypot(xx2 - VP[0], yy2 - VP[1])
    wblur = (np.clip((dist - 180) / 520, 0, 1) ** 1.3)[..., None] * behind * 0.85
    half = cv2.resize(x, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    x = x * (1 - wblur) + cv2.resize(speed_blur(half), (W, H)) * wblur

    lum = x @ np.array([0.0722, 0.7152, 0.2126], np.float32)
    # 1) Estelas de luces de la calle
    hl = np.clip((lum - 0.62) / 0.3, 0, 1)[..., None] * x * behind
    small = cv2.resize(hl, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    streak = cv2.resize(zoom_blur(small), (W, H))
    streak *= np.array([0.92, 0.98, 1.05], np.float32)   # blanco cálido
    # 2) Estelas de velocidad
    speed = streak_layer(t) * behind * 0.75
    # 3) Bloom de faros + destello anamórfico
    head = np.clip((lum - 0.8) / 0.2, 0, 1)[..., None] * car * x
    hs = cv2.resize(head, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    bloom = cv2.resize(cv2.GaussianBlur(hs, (0, 0), 6), (W, H)) * np.array([1.2, 1.05, 0.95], np.float32) * 1.4
    flare = cv2.resize(cv2.blur(hs, (151, 1)), (W, H)) * np.array([0.9, 0.95, 1.0], np.float32) * 2.0
    flare *= 0.75 + 0.25 * np.sin(t * 2.4)

    add = (streak * 1.4 + speed) * vfade + bloom + flare
    out = 1 - (1 - x) * (1 - np.clip(add, 0, 1))         # screen
    out[BLACK_FROM + 40:] *= 0                             # zona de textos limpia
    cv2.imwrite(os.path.join(DST, f'{i:04d}.jpg'), np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8),
                [cv2.IMWRITE_JPEG_QUALITY, 95])
    return i


if __name__ == '__main__':
    os.makedirs(DST, exist_ok=True)
    n = len(os.listdir(SRC))
    todo = [int(a) for a in sys.argv[1:]] or list(range(1, n + 1))
    with Pool(4) as p:
        for i in p.imap_unordered(process, todo):
            if i % 24 == 0:
                print('cuadro', i, '/', n)
