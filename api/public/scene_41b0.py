
from manim import *
from math import *
config.frame_size = (3840, 2160)
config.frame_width = 14.22

from manim import *

class SquareToCircle(Scene):
    def construct(self):
        # Create a square
        square = Square(side_length=2, color=BLUE)

        # Create a circle
        circle = Circle(radius=1, color=RED)

        # Add the square to the scene
        self.add(square)

        # Animate the square transforming into the circle
        self.play(Transform(square, circle), run_time=2)

        # Wait for 1 second before closing the scene
        self.wait(1)
    