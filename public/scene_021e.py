
from manim import *
from math import *
config.frame_size = (3840, 2160)
config.frame_width = 14.22

from manim import *
from math import *

class GenScene(Scene):
    def construct(self):
        cube = Cube()
        self.play(Create(cube))
        self.play(Rotate(cube, PI/2))
        self.play(Rotate(cube, PI/2, axis=UP))
        self.play(Rotate(cube, PI/2, axis=RIGHT))

    