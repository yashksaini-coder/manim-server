
from manim import *
from math import *
config.frame_size = (3840, 2160)
config.frame_width = 14.22


from manim import *
from math import *

class GenScene(Scene):
    def construct(self):
        c = Circle(color=BLUE, radius=0.5)
        self.play(Create(c))
        self.play(c.animate.shift(UP*2), rate_func=there_and_back, run_time=2)

    