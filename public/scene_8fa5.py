
from manim import *
from math import *
config.frame_size = (3840, 2160)
config.frame_width = 14.22


from manim import *
from math import *

class GenScene(Scene):
    def construct(self):
        axes = ThreeDAxes()
        sphere = Surface(
            lambda u, v: np.array([np.cos(u) * np.cos(v), np.cos(u) * np.sin(v), np.sin(u)]),
            u_min=-PI/2,
            u_max=PI/2,
            v_min=0,
            v_max=TAU,
            resolution=20,
        )
        self.play(Create(axes), Create(sphere))
        self.set_camera_orientation(phi=75 * DEGREES, theta=30 * DEGREES)
        self.begin_ambient_camera_rotation(rate=0.05)

    