
from manim import *
from math import *
config.frame_size = (3840, 2160)
config.frame_width = 14.22

from manim import *
from math import *

class GenScene(Scene):
    def construct(self):
        t = Triangle(color=RED)
        c = Circle(color=BLUE)
        self.play(Create(t))
        self.play(Transform(t, c))
        self.play(Uncreate(c))
    