"""Colour evidence only; circle/star/diamond shape is deliberately not required."""
import cv2
import numpy as np

def classify_marker(crop, min_pixels=5, ratio=2.0):
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    h,s,v=cv2.split(hsv)
    # Restrict colour counting to the central part of the marker crop.
    height, width = h.shape
    yy, xx = np.ogrid[:height, :width]
    cx, cy = (width - 1) / 2, (height - 1) / 2
    rx, ry = max(1, width * .35), max(1, height * .35)

    core = ((xx - cx) / rx)**2 + ((yy - cy) / ry)**2 <= 1
    bright = (s >= 100) & (v >= 120) & core
    blue=int(np.count_nonzero(bright&(h>=80)&(h<=115)))
    red=int(np.count_nonzero(bright&((h<=12)|(h>=170))))
    side='unknown'
    if blue>=min_pixels and blue>=ratio*max(1,red):side='ally'
    elif red>=min_pixels and red>=ratio*max(1,blue):side='enemy'
    return side,{'blue_pixels':blue,'red_pixels':red}
