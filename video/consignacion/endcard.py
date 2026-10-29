"""Genera las capas del motion del logo para el cierre (endcard/).

A partir del alfa del logo calcula un relieve (bisel) con luz desde arriba a la izquierda:
- cromo.png / cromo-brillo.png: logo oscuro con borde metálico, para la fase sobre negro.
- relieve-luz.png / relieve-sombra.png: luces y sombras para el logo "tallado" tono sobre
  tono en el fondo naranja (como el cierre de la referencia).

Uso: python3 endcard.py
"""
import os

import cv2
import numpy as np

DIR = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(DIR, '..', '..', 'assets', 'brand', 'logo-rodados-mono-blanco.png')
OUT = os.path.join(DIR, 'endcard')
PAD = 60
SCALE = 1.25


def save(name, rgb, a):
    rgb = np.broadcast_to(rgb, a.shape + (3,))
    rgba = np.dstack([np.clip(rgb, 0, 255), np.clip(a * 255, 0, 255)]).astype(np.uint8)
    cv2.imwrite(os.path.join(OUT, name), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))


im = cv2.imread(LOGO, cv2.IMREAD_UNCHANGED)
a = im[..., 3].astype(np.float32) / 255
a = cv2.resize(a, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
a = np.pad(a, PAD)

h = cv2.GaussianBlur(a, (0, 0), 3.2)
gx = cv2.Sobel(h, cv2.CV_32F, 1, 0, ksize=3)
gy = cv2.Sobel(h, cv2.CV_32F, 0, 1, ksize=3)
L = np.array([-0.62, -0.78])                         # luz desde arriba-izquierda
shade = (gx * L[0] + gy * L[1]) * 2.4                # + borde iluminado, - borde en sombra
edge = np.clip(np.hypot(gx, gy) * 2.2, 0, 1)
inside = np.clip(cv2.GaussianBlur(a, (0, 0), 1.0) * 1.4, 0, 1)

os.makedirs(OUT, exist_ok=True)
one = np.ones_like(a)[..., None]

# Fase oscura: cara casi negra + borde metálico
lit = np.clip(shade, 0, 1)
dark = np.clip(-shade, 0, 1)
metal = 16 + 35 * edge + 210 * lit ** 1.4
save('cromo.png', one * metal[..., None], inside)
spec = 40 + 230 * np.clip(edge * 1.6 + lit * 1.5, 0, 1)
save('cromo-brillo.png', one * spec[..., None], inside * np.clip(edge * 1.5 + lit, 0, 1))

# Fase naranja: relieve tono sobre tono
save('relieve-luz.png', one * np.array([255, 236, 214]), np.clip(lit * 1.1, 0, 0.85) * inside)
drop = cv2.GaussianBlur(np.roll(np.roll(a, 14, 0), 9, 1), (0, 0), 10) * (1 - inside)
sh = np.clip(dark * 1.0, 0, 0.75) * inside + drop * 0.55
save('relieve-sombra.png', one * np.array([92, 34, 0]), sh)
save('relieve-brillo.png', one * np.array([255, 245, 232]), np.clip(lit * 1.6 + edge * 0.6, 0, 1) * inside)
print('listo', a.shape[::-1])
