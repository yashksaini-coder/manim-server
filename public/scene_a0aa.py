
from manim import *
from math import *
config.frame_size = (3840, 2160)
config.frame_width = 14.22

from manim import *
from math import *

class GenScene(Scene):
    def construct(self):
        cube = Cube(color=BLUE, fill_opacity=0.5)
        cube_side_length = 4
        volume_text = Text(f"Volume = {cube_side_length}^3", font_size=24)
        self.play(Create(cube))
        self.play(Write(volume_text))
        self.wait(2)
        self.play(Unwrite(volume_text))
        self.play(FadeOut(cube))
    