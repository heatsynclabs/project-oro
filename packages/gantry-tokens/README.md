# gantry-tokens

## What it is

The GANTRY design system as CSS custom properties, and a checker that keeps the
colours legible.

The token layer is one file, `tokens.css`, with no build step and no token
compiler, because the consumers are Astro, Vue, React 19, and Rails ERB, and
only plain CSS reaches all four. Link it and the properties are there.
`docs/plan/architecture.md` section 5 is the reasoning.

Two files here are generated, and this used to say nothing was.
`brand/hsl-lockup.svg` and `brand/hsl-lockup-dark.svg` are built by
`brand/build-the-lockup.py` from the two SVGs the members portal carries inline
in its masthead, because the hosted sign in screens take a file and cannot
inline anything, and a second copy of a logo is two logos that drift. Two files
rather than one because the label policy has a light slot and a dark one, and
the ink differs: `--bone` in each theme. `tests/run.sh` runs that script with
`--check`, so a masthead somebody edits without rebuilding fails rather than
shipping two marks.

Three things it defines:

- **Themes.** `:root[data-theme="dark"]` and `:root[data-theme="light"]`, set on
  the root element.
- **Grounds.** `page`, `raised`, `plate`, and `hazard`, set with `data-ground`
  on any element. A ground is the surface a block sits on. It remaps the
  semantic colours for that element and everything inside it, so a hazard band
  inside a paper page still resolves legible text without anybody picking
  colours by hand. The word is in `docs/glossary.md`.
- **Everything that is not colour.** Type scale, spacing, shadows, z index, the
  44 pixel tap floor, and the safe area insets.

```html
<body data-ground="page">
  <section data-ground="hazard">
    <p>This paints amber and takes the dark inks, with no class on it.</p>
  </section>
</body>
```

### What this copy changes, and why

It came from the `hsl-forge` brand skill package. Two defects were measured
before it landed here and both are fixed in this copy and nowhere upstream yet.

**The status inks now live in the grounds.** `--ink-ok`, `--ink-warn`,
`--ink-err`, `--ink-info`, `--ink-faint`, and `--ink-ghost` used to be declared
only in the theme blocks, so a grounded element kept its page theme values.
`--ink-warn` on a hazard ground was `#f2ab1e` on `#f2ab1e`, a contrast ratio of
1.00, which is invisible. Each ground now carries the family. The `page` and
`raised` grounds map it from `--theme-ink-*` in the theme blocks, since those
two surfaces do flip with the theme. The `plate` and `hazard` grounds hold
literals, because a plate stays dark and a hazard band stays amber whatever the
theme says.

**A ground paints itself.** `[data-ground]` used to remap variables and set no
`background-color` and no `color`, so a bare grounded element rendered in page
colours and read as though the mechanism were broken. It now paints. Where the
remap is wanted without the fill, `data-ground-paint="none"` turns the painting
off and leaves the tokens remapped.

Two smaller changes came out of measuring. The v1.1 aliases `--ink-black` and
`--ink-soft` were repointed at `--g-ink` and `--g-ink-2`, so they follow the
ground like everything else; at the root they resolve to exactly what they did
before. And `--ink` follows `--g-ink` for the same reason.

### What it leaves behind

The upstream file also ships `@font-face` blocks and a set of `.g-*` primitives:
`.g-card`, `.g-btn`, `.g-grid`, the caution tape ribbon, the grain overlay, the
focus ring, and the iOS zoom guard. None of that is here.

The primitives are `gantry-css`, which is a later step in
`docs/plan/order-of-operations.md` and is not built. The `@font-face` blocks
point at `fonts/*.woff2` files this package does not carry, and a stylesheet
that references assets which are not there is worse than one that does not try.
The `--font-*` properties still name the families, each with a real fallback
stack, so text renders correctly on a machine that has none of them installed.

## How to run it

There is nothing to start. Link the file:

```html
<link rel="stylesheet" href="tokens.css">
```

To see what a token resolves to on every theme and ground, and what that
measures against the surface behind it:

```sh
python3 packages/gantry-tokens/validator/check_contrast.py --list
```

## How to test it

```sh
packages/gantry-tokens/tests/run.sh
```

That runs the validator's own suite and then the validator itself over
`tokens.css`. CI runs the same script.

The validator walks the theme by ground cross product. For every ink token on
every ground it resolves the `var()` chain, composites any `rgba` over the
resolved ground, computes the WCAG 2.1 relative luminance contrast ratio, and
reports every pair under 4.5:1. That is 112 pairs today. The themes and the
grounds are read out of the token file rather than written into the checker, so
a fifth ground comes under the check the moment somebody declares one.

So does a new ink. Three name prefixes are read as a promise that the token is
something a person will set `color` to, and any token carrying one is measured:

| Prefix | What it covers |
|---|---|
| `--ink` | The status inks, and the v1.1 aliases that kept the name |
| `--g-ink` | The ground text family, which `--color-text-primary`, `--color-text-secondary` and `--color-text-tertiary` alias, and which `[data-ground]` paints as `color` |
| `--g-on-` | The accent used as text on the ground. Upstream sets `color: var(--g-on-accent)` on `.g-eyebrow`, which sits on the ground rather than on an accent coloured surface, so that is what it is measured against |

Neither of the two defects shows up in a contrast ratio, so measuring cannot
hold either one fixed. `validator/test_grounds.py` does that instead, and by
parsing rather than by searching the file for a string: it reads the ink
declarations of each ground block and the `background-color` and `color` of the
`[data-ground]` rule out of the parsed stylesheet. One test comments that rule
out and asserts the suite goes red, so a rule disabled during debugging and not
restored fails the same way a deleted one does.

It refuses to run on a file with no grounds or no inks, rather than passing
having looked at nothing. Point it at the v1.1 tokens in `heatsynclabs/new-hsl`
and it says so instead of going green.

`validator/known-failures.txt` carries the pairs that are below the minimum and
accepted for now, one line each, with the ratio measured and the reason. A pair
below the minimum that is not in that file fails the build. So does a pair in
that file which has started passing, and so does one whose ratio has moved,
because an exemption nobody has to revisit is how a list like this becomes a
place things go to be forgotten. Sixteen pairs are listed today and the file
says why for each. Four of them are `--g-ink-3`, the tertiary ground ink, and
those four are a real defect held open rather than an exemption on principle:
clearing them means changing a brand colour value, which is not a change this
package makes on its own. Until it is made, `--color-text-tertiary` should not
carry anything a person has to read.

`validator/fixtures/unfixed-grounds.css` is the upstream theme and ground blocks
before the fix, kept byte for byte. One test measures it and asserts the checker
reports `--ink-warn` on hazard. A checker that has only ever run green proves
nothing, and the phase 1 exit criterion is not that it passes, it is that it
passes and would have caught that pair.

## What it depends on

Nothing, at runtime. It is one CSS file.

The validator needs python3 and the standard library. There is no third party
package to install, which is why there is no ADR behind it: a volunteer fixing
the theme at 2am should not have to make a package manager work first.

Provenance and licence are in `ATTRIBUTIONS.md` and repeated in the header of
`tokens.css`. The short version: the v2.0 layer is internal HeatSync Labs work
from the `hsl-forge` brand skill package, it descends from the v1.1 tokens in
`heatsynclabs/new-hsl`, neither carries a licence file, and none is claimed
here.
