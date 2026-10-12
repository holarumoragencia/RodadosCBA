"""Colorimetría: adapta autos y mano a la luz cálida del galpón.

1. Neutraliza la dominante de color de cada foto (balance de blancos sobre los
   píxeles casi neutros: blancos, cromados, cubiertas).
2. Aplica la temperatura cálida del galpón.
3. Comprime las altas luces con una curva suave para que los blancos no
   "brillen" más que el entorno (el piso del galpón llega a ~76 % de luminancia).
4. Baja un poco la saturación de reflejos de cielo.

Uso: python3 grade.py  (desde la carpeta video/)
"""
import os
import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')
WARM = np.array([1.07, 1.0, 0.89])   # temperatura del galpón (parcial)
KNEE = 0.70                          # desde dónde se comprimen las altas luces
SHOULDER = 0.80                      # cuánto rango queda arriba de la rodilla


def tone(x):
    s = (1 - KNEE) * SHOULDER
    return np.where(x < KNEE, x, KNEE + s * (1 - np.exp(-(x - KNEE) / s)))


def grade(src, dst, neutralize=True, warm=WARM, desat=0.10):
    im = np.asarray(Image.open(src).convert('RGBA')).astype(np.float64) / 255
    rgb, a = im[..., :3], im[..., 3]
    if neutralize:
        mx, mn = rgb.max(-1), rgb.min(-1)
        lum = rgb @ [0.2126, 0.7152, 0.0722]
        m = (a > 0.8) & (mx - mn < 0.08) & (lum > 0.25) & (lum < 0.9)
        mean = rgb[m].mean(0)
        gains = np.clip(mean.mean() / mean, 0.85, 1.15)
        rgb = rgb * gains
    rgb = rgb * warm
    lum = (rgb @ [0.2126, 0.7152, 0.0722])[..., None]
    rgb = lum + (rgb - lum) * (1 - desat)
    rgb = tone(np.clip(rgb, 0, 1.2))
    out = np.dstack([np.clip(rgb, 0, 1), a])
    Image.fromarray((out * 255 + 0.5).astype(np.uint8), 'RGBA').save(dst)


if __name__ == '__main__':
    src_dir = os.path.join(ROOT, 'autos', 'finales')
    dst_dir = os.path.join(ROOT, 'autos', 'grade')
    os.makedirs(dst_dir, exist_ok=True)
    for f in sorted(os.listdir(src_dir)):
        grade(os.path.join(src_dir, f), os.path.join(dst_dir, f))
        print('auto', f)
    grade(os.path.join(ROOT, 'mano.png'), os.path.join(ROOT, 'mano-grade.png'),
          neutralize=False, warm=np.array([1.03, 1.0, 0.95]), desat=0.0)
    print('mano')
