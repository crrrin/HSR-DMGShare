import unittest
try:
    import cv2
    import numpy as np
    from faction import classify_marker
except ImportError:
    cv2=None

@unittest.skipIf(cv2 is None,'OpenCV not installed')
class FactionTests(unittest.TestCase):
    def test_colours_and_ambiguity(self):
        for colour,want in [((255,220,40),'ally'),((40,60,255),'enemy'),((50,50,50),'unknown')]:
            crop=np.zeros((20,20,3),np.uint8)
            cv2.circle(crop,(10,10),3,colour,-1)
            self.assertEqual(classify_marker(crop)[0],want)
