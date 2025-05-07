
from manim import *
from math import *
config.frame_size = (3840, 2160)
config.frame_width = 14.22

from manim import *
from math import *

class GenScene(Scene):
    def construct(self):
        s = Square(color=BLUE)
        c = Circle(color=BLUE)
        self.play(Create(s))
        self.play(Transform(s, c))

    