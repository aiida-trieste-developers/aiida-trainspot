# Landing-page animation

`docs/source/_svg/active_learning.html` is generated, not hand-written. It holds two inline SVGs:
a two-column layout for normal screens and a portrait rebuild for phones.

| script                        | output                 | viewBox                                                     |
| ----------------------------- | ---------------------- | ----------------------------------------------------------- |
| `gen_active_learning_main.py` | `/tmp/v2col_full.txt`  | 745 x 720, used on the page                                 |
| `gen_active_learning_tall.py` | `/tmp/mobile_full.txt` | 400 x 640, used below 700 px                                |
| `gen_active_learning_wide.py` | `/tmp/v12_full.txt`    | 1646 x 585, a single-row variant, not currently on the page |

To regenerate, run the scripts and wrap the two fragments in the `.al-anim` / `.al-wide` / `.al-tall`
divs that `active_learning.html` already uses.

## Checking the result

`check_overlaps.py` reads a generated SVG and reports anything that shares both space and time with
something else. It exists because eyeballing the animation repeatedly missed real defects.

```bash
python docs/tools/check_overlaps.py /tmp/v2col_full.txt 745 720
```

It works out, for every group, where it actually sits (a static position, or the start and end of its
motion path), how big it really is (from its own shapes and text), and when it is on screen (from its
opacity keyframes, as separate bursts rather than one merged span). It follows `animateTransform` to
where a group ends up, treats the stage discs as obstacles, and knows paint order: something drawn
earlier passes behind, which is harmless for a decorative spark but not for a set carrying its own
count, since that just becomes unreadable.

## Styling

Colours come from CSS custom properties on `.al-anim` in `docs/source/_static/aiida-custom.css`,
which is also where the two-column/portrait swap lives. `docs/source/_static/al-anim.js` pauses
whichever layout is hidden, and both of them for readers who ask for reduced motion.
