
from manim import *
from math import *
config.frame_size = (3840, 2160)
config.frame_width = 14.22


from manim import *
from math import *

class GenScene(Scene):
    def construct(self):
        c = Circle(color=BLUE)
        c_original = Circle(color=PURPLE)
        self.play(Create(c_original))
        self.play(Transform(c_original, c))
        self.play(c_original.set_fill(GREEN))

    