
from manim import *
from math import *
config.frame_size = (3840, 2160)
config.frame_width = 14.22


from manim import *
from math import *

class GenScene(Scene):
    def construct(self):
        sphere = Sphere(color=BLUE, resolution=50)
        self.play(Create(sphere))
        self.play(Rotate(sphere, angle=2 * PI))
        self.play(FadeOut(sphere))

    