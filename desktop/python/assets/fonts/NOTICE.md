# ThinMulmaru (얇은물마루)

- Author: BinRecycle; based on Mulmaru by Mushsooni.
- Upstream: https://github.com/BinRecycle/ThinMulmaru
- License: SIL Open Font License 1.1; see LICENSE.txt (bundled with the font).
- Supplied webfont: https://cdn.jsdelivr.net/gh/Project-Noonnu/2607161321@thinmulmaru/thinmulmaru/ThinMulmaru.woff2

ThinMulmaru.ttf is the same font extracted from the supplied WOFF2 container,
with its names, outlines and license metadata retained. Only the container changed.
It was generated once using fontTools.ttLib.TTFont: set flavor=None, then save as TTF.
fontTools is not needed at runtime or for packaging the checked-in TTF.
The app registers the bundled font in-process and does not install a system font.

# Mulmaru (물마루)

- Author: Mushsooni.
- Upstream: https://github.com/mushsooni/mulmaru
- Supplied webfont: https://cdn.jsdelivr.net/gh/projectnoonnu/2601-4@1.1/Mulmaru.woff2
- License: SIL Open Font License 1.1; see Mulmaru-LICENSE.txt.

Mulmaru.ttf is extracted from the supplied WOFF2 using fontTools, with names,
outlines and license metadata retained. Its native weight is 500.
The app uses this face for emphasized bold text alongside regular ThinMulmaru,
without synthetic emboldening or installing either font system-wide.
