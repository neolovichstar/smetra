import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"


def hex_rgb(token):
    value = token.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) == 8:
        value = value[:6]
    if len(value) != 6:
        return None
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def is_chromatic_dark_blue(rgb):
    r, g, b = rgb
    maximum, minimum = max(rgb), min(rgb)
    delta = maximum - minimum
    if maximum == 0 or delta < 10 or sum(rgb) / 3 < 12:
        return False
    if maximum == r:
        hue = 60 * (((g - b) / delta) % 6)
    elif maximum == g:
        hue = 60 * ((b - r) / delta + 2)
    else:
        hue = 60 * ((r - g) / delta + 4)
    if hue < 0:
        hue += 360
    return 190 <= hue <= 260 and delta / maximum >= 0.18


def contrast_ratio(foreground, background):
    def luminance(rgb):
        channels = []
        for component in rgb:
            channel = component / 255
            channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    first, second = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (first + 0.05) / (second + 0.05)


class UIDesignSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.style = (WEB / "style.css").read_text(encoding="utf-8-sig")
        cls.black = (WEB / "black.css").read_text(encoding="utf-8")
        cls.cabinet = (WEB / "cabinet.css").read_text(encoding="utf-8")
        cls.landing_html = (WEB / "index.html").read_text(encoding="utf-8")
        cls.landing_js = (WEB / "landing.js").read_text(encoding="utf-8")
        cls.motion_test = (ROOT / "tests" / "browser_landing_motion.cjs").read_text(encoding="utf-8")
        cls.prompt = (ROOT / "docs" / "UI_DESIGN_CRITIC_PROMPT.md").read_text(encoding="utf-8")

    def test_product_styles_do_not_reintroduce_chromatic_dark_blue(self):
        for name, source in (("style.css", self.style), ("black.css", self.black), ("cabinet.css", self.cabinet)):
            matches = []
            for token in re.findall(r"#[0-9a-fA-F]{3,8}\b", source):
                rgb = hex_rgb(token)
                if rgb and is_chromatic_dark_blue(rgb):
                    matches.append(token.lower())
            self.assertFalse(matches, f"{name} contains dark-blue color tokens: {sorted(set(matches))}")

    def test_primary_accent_is_shared_and_not_decorative_blue(self):
        self.assertIn("--accent:#efb56b", self.black)
        self.assertIn("--cabinet-accent:var(--accent)", self.cabinet)
        self.assertIn("background:var(--accent)", self.black)
        self.assertIn("box-shadow:none", self.black[self.black.find(".btn.primary{"):self.black.find(".btn.primary{") + 180])

    def test_primary_accent_meets_normal_text_contrast_on_landing_surface(self):
        accent = hex_rgb("#efb56b")
        surface = hex_rgb("#090909")
        self.assertGreaterEqual(contrast_ratio(accent, surface), 4.5)

    def test_decorative_orbits_and_glows_are_removed_from_landing_markup(self):
        self.assertNotRegex(self.landing_html, r'class="[^"]*motion-(?:orbit|glow|sweep|spark)')
        self.assertNotRegex(self.black, r"motion-(?:orbit|glow|sweep|spark|scan)|proposal-sheen|cta-light-sweep|quiet-float|hero-atmosphere|hero-rule-arrive")

    def test_pointer_parallax_changes_actual_artwork_transform(self):
        self.assertIn("transform:translate3d(var(--scene-x,0px),var(--scene-y,0px),0)", self.black)
        self.assertIn("setProperty('--scene-x'", self.landing_js)
        self.assertIn("setProperty('--scene-y'", self.landing_js)
        self.assertIn("visibly transform the hero artwork", self.motion_test)

    def test_keyboard_focus_and_reduced_motion_are_preserved(self):
        self.assertIn(":focus-visible{outline:2px solid var(--accent)", self.style)
        self.assertIn("button:focus-visible,a:focus-visible{outline:2px solid var(--accent)", self.black)
        self.assertIn("@media(prefers-reduced-motion:reduce)", self.black)
        self.assertIn("Reduced-motion preference disables title entrance animation", self.motion_test)

    def test_workspace_microcopy_is_not_set_below_ten_pixels(self):
        self.assertNotRegex(self.cabinet, r"font-size:9px")

    def test_release_gate_prompt_requires_verified_ten_out_of_ten(self):
        self.assertIn("10/10 по каждой области", self.prompt)
        self.assertIn("NOT READY", self.prompt)
        self.assertIn("NOT VERIFIED", self.prompt)


if __name__ == "__main__":
    unittest.main()
