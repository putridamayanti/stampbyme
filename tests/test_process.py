import numpy as np
import pytest

from conftest import blank, filled_rect, ring
from stampbyme.detect import detect_objects
from stampbyme.process import remove_background, render_stamp, upscale_factor

WHITE = np.array([255, 255, 255], np.float32)
SIZE = 256


def pixel(rgb, paper=WHITE):
    return remove_background(np.array([[rgb]], np.uint8), paper)[0, 0]


def alpha_bbox(image):
    """Box around the half-opaque edge (ignores faint resampling tails)."""
    a = np.array(image)[..., 3]
    ys, xs = np.nonzero(a >= 128)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


class TestRemoveBackground:
    def test_white_becomes_transparent(self):
        assert pixel((255, 255, 255))[3] == 0

    def test_black_stays_opaque_black(self):
        assert tuple(pixel((0, 0, 0))) == (0, 0, 0, 255)

    def test_grey_becomes_semi_transparent_black(self):
        r, g, b, a = pixel((128, 128, 128))
        assert (r, g, b) == (0, 0, 0)
        assert 110 < a < 130

    def test_near_white_noise_is_removed(self):
        assert pixel((250, 251, 249))[3] == 0

    def test_cream_paper_becomes_transparent(self):
        cream = np.array([246, 238, 220], np.float32)
        assert pixel((246, 238, 220), cream)[3] == 0
        assert pixel((0, 0, 0), cream)[3] == 255

    def test_colour_is_unmixed_from_paper(self):
        # 50% red over white is (255, 128, 128); the ink should come back as red.
        r, g, b, a = pixel((255, 128, 128))
        assert r == 255 and g < 5 and b < 5
        assert 110 < a < 130

    def test_compositing_back_on_paper_reproduces_input(self):
        rng = np.random.default_rng(0)
        rgb = rng.integers(0, 256, (32, 32, 3), dtype=np.uint8)
        rgba = remove_background(rgb, WHITE, noise_floor=0).astype(np.float32)
        a = rgba[..., 3:] / 255
        recomposed = rgba[..., :3] * a + 255 * (1 - a)
        assert np.abs(recomposed - rgb).max() <= 2


def single_object(sheet):
    result = detect_objects(sheet)
    assert len(result.objects) == 1
    return result.paper, result.objects[0]


class TestRenderStamp:
    def test_output_is_square_rgba_of_requested_size(self):
        sheet = blank()
        filled_rect(sheet, 100, 100, 300, 120)
        paper, obj = single_object(sheet)
        stamp = render_stamp(sheet, paper, obj, size=SIZE)
        assert stamp.mode == "RGBA" and stamp.size == (SIZE, SIZE)

    @pytest.mark.parametrize("rect", [(100, 100, 300, 120), (500, 50, 80, 400), (40, 40, 200, 200)])
    def test_object_is_centred(self, rect):
        sheet = blank()
        filled_rect(sheet, *rect)
        paper, obj = single_object(sheet)
        x0, y0, x1, y1 = alpha_bbox(render_stamp(sheet, paper, obj, size=SIZE, padding=10))
        assert abs((x0 + x1) / 2 - SIZE / 2) <= 1
        assert abs((y0 + y1) / 2 - SIZE / 2) <= 1

    def test_aspect_ratio_preserved(self):
        sheet = blank()
        filled_rect(sheet, 100, 100, 400, 100)
        paper, obj = single_object(sheet)
        x0, y0, x1, y1 = alpha_bbox(render_stamp(sheet, paper, obj, size=SIZE, padding=0))
        assert (x1 - x0) / (y1 - y0) == pytest.approx(4, rel=0.03)

    @pytest.mark.parametrize("padding", [0, 20, 100])
    def test_padding_sets_margin(self, padding):
        sheet = blank()
        filled_rect(sheet, 300, 300, 200, 100)
        paper, obj = single_object(sheet)
        x0, _, x1, _ = alpha_bbox(render_stamp(sheet, paper, obj, size=SIZE, padding=padding))
        expected = SIZE * 200 / (200 + 2 * padding)
        assert abs((x1 - x0) - expected) <= 2

    def test_small_object_is_upscaled_to_fill_canvas(self):
        sheet = blank()
        filled_rect(sheet, 100, 100, 40, 40)
        paper, obj = single_object(sheet)
        stamp = render_stamp(sheet, paper, obj, size=SIZE, padding=0)
        x0, y0, x1, y1 = alpha_bbox(stamp)
        assert x1 - x0 >= SIZE - 2 and y1 - y0 >= SIZE - 2
        assert upscale_factor(obj, SIZE, 0) == pytest.approx(SIZE / 40)

    def test_large_object_is_downscaled(self):
        sheet = blank(2000, 1200)
        filled_rect(sheet, 100, 100, 1600, 800)
        paper, obj = single_object(sheet)
        x0, _, x1, _ = alpha_bbox(render_stamp(sheet, paper, obj, size=SIZE, padding=0))
        assert x1 - x0 <= SIZE

    def test_background_is_transparent_and_ink_opaque(self):
        sheet = blank()
        ring(sheet, 400, 400, 150, thickness=20)
        paper, obj = single_object(sheet)
        a = np.array(render_stamp(sheet, paper, obj, size=SIZE, padding=10))[..., 3]
        assert a[0, 0] == 0 and a[-1, -1] == 0
        assert a[SIZE // 2, SIZE // 2] == 0  # hole in the ring
        assert (a == 255).sum() > 0.05 * SIZE * SIZE

    def test_neighbour_inside_bbox_is_not_copied(self):
        sheet = blank()
        filled_rect(sheet, 100, 100, 40, 400)
        filled_rect(sheet, 100, 460, 400, 40)
        filled_rect(sheet, 300, 200, 100, 100)
        result = detect_objects(sheet)
        l_shape = max(result.objects, key=lambda o: o.area)
        stamp = np.array(render_stamp(sheet, result.paper, l_shape, size=400, padding=0))
        # Sheet (300..400, 200..300) maps to stamp (200..300, 100..200) at scale 1.
        assert stamp[100:200, 200:300, 3].max() == 0
        assert stamp[:, :40, 3].min() == 255  # the L's vertical bar is there

    def test_object_touching_sheet_edge(self):
        sheet = blank(600, 400)
        filled_rect(sheet, 0, 0, 120, 80)
        paper, obj = single_object(sheet)
        stamp = render_stamp(sheet, paper, obj, size=SIZE, padding=30)
        x0, y0, x1, y1 = alpha_bbox(stamp)
        assert abs((x0 + x1) / 2 - SIZE / 2) <= 1
        assert abs((y0 + y1) / 2 - SIZE / 2) <= 1

    def test_ink_colour_is_preserved(self):
        sheet = blank()
        filled_rect(sheet, 100, 100, 200, 200)
        paper, obj = single_object(sheet)
        rgba = np.array(render_stamp(sheet, paper, obj, size=SIZE))
        opaque = rgba[rgba[..., 3] == 255]
        assert opaque[:, :3].max() == 0


class TestInkOpacity:
    def test_ink_opacity_stretches_alpha(self):
        dark_grey = (40, 40, 40)  # ~84% opaque over white
        assert pixel(dark_grey)[3] < 230
        out = remove_background(np.array([[dark_grey]], np.uint8), WHITE, ink_opacity=0.84)[0, 0]
        assert out[3] == 255

    def test_dark_grey_ink_sheet_gives_solid_stamps(self):
        sheet = blank(paper=(246, 238, 220))
        filled_rect(sheet, 100, 100, 200, 200, color=(25, 25, 30))
        result = detect_objects(sheet)
        assert 0.85 < result.ink_opacity < 0.95
        a = np.array(render_stamp(sheet, result.paper, result.objects[0], size=SIZE,
                                  ink_opacity=result.ink_opacity))[..., 3]
        assert a[SIZE // 2, SIZE // 2] == 255

    def test_grey_shading_stays_lighter_than_ink(self):
        sheet = blank()
        filled_rect(sheet, 100, 100, 200, 200, color=(30, 30, 30))
        filled_rect(sheet, 150, 150, 100, 100, color=(140, 140, 140))  # shading inside
        result = detect_objects(sheet)
        a = np.array(render_stamp(sheet, result.paper, result.objects[0], size=SIZE, padding=0,
                                  ink_opacity=result.ink_opacity))[..., 3]
        assert a[10, 10] == 255
        assert 100 < a[SIZE // 2, SIZE // 2] < 160

    def test_pure_black_sheet_is_unchanged(self, grid):
        sheet, _ = grid
        assert detect_objects(sheet).ink_opacity == 1.0

    def test_light_grey_sheet_is_not_forced_solid(self):
        sheet = blank()
        filled_rect(sheet, 100, 100, 200, 200, color=(200, 200, 200))  # ~22% opaque
        assert detect_objects(sheet).ink_opacity == 0.5
