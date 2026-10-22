# Content rules

Every theme in this repository is shared with everyone who uses RiftWii. So
everything in it must be yours to share. These rules say what that means.
The maintainers review every submission against them.

## 1. Only your own work, or work you may share

Every picture, sound, music file and font in a theme must be either:

- made by you, or
- someone else's work that you have permission to distribute under the
  theme's license. A Creative Commons license that allows this counts as
  permission (see rule 4).

"I found it online" is not permission. Neither is "it's only a small part".

## 2. No Nintendo material

A theme must not contain anything taken from Nintendo's software. This
includes:

- music or sounds ripped from the Wii Menu, a channel or a game;
- icons, pictures, textures or fonts extracted from them, or traced over
  them.

No contributor can give permission for Nintendo's work, so no license or
credit line makes it acceptable.

A look *inspired* by the Wii Menu is fine, if you draw it yourself from
scratch: rounded white tiles, a curved bottom bar or soft blue highlights
are ideas, not copies. RiftWii's own default look is already drawn that
way.

The same rule holds for screenshots in a pull request: show the theme
itself, with no Nintendo material, no game covers, box art or banners, and
no real game names beyond RiftWii's own words in its menu. Those pictures
and titles belong to the games' publishers. An empty SD card or one with
only homebrew shows a clean Home (the names view with empty places works
well). The site's preview is drawn for every theme, so no `preview.png`
goes in the folder.

## 3. Allowed licenses

The theme's `LICENSE` file names one of these licenses, which covers the
whole theme:

| License | SPDX id | In short |
| --- | --- | --- |
| [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | `CC0-1.0` | No rights reserved |
| [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `CC-BY-4.0` | Free to share and change, with credit |
| [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | `CC-BY-SA-4.0` | As CC BY, and changed versions keep the license |

Any other license needs the maintainers' approval before the theme can be
merged. Ask in the pull request. "NonCommercial" (NC) and "NoDerivatives"
(ND) licenses are not normally approved: people should be able to remix
themes.

## 4. Credit third-party parts

If part of your theme is someone else's CC-licensed work, the theme's
`LICENSE` lists it with:

- which file uses it;
- where it came from (a link);
- who made it;
- its license.

The work's license must allow what your theme's license allows. For
example, a CC BY-SA picture can't go into a CC0 theme.

## The LICENSE file

Every theme has a `LICENSE` file that starts with two lines the check
reads:

```
License: CC-BY-4.0
Author: Your Name

Third-party parts:
- music.ogg: "Song Title" by Someone, https://example.org/song, CC-BY-4.0
```

Write "Third-party parts: none" if everything is yours.

## Takedown

If a theme here uses your work without permission:

- open a [takedown request](.github/ISSUE_TEMPLATE/takedown.md) (a GitHub
  issue), or
- email **TODO-maintainer-contact** if you'd rather not write in public.

Say which theme and file, what the work is and how you are connected to
it.

The maintainers will remove the file, or the whole theme, within
**TODO-time** of a valid request, and add its SHA-256 to
`scripts/flagged-sha256.txt` so it isn't submitted again. Removal takes it
out of `themes.json` and the published zips at the next publish. Copies
already downloaded to someone's SD card, or kept in this repository's git
history, are outside what the maintainers can reach; they will say so in
their reply.

If a submitter disagrees, they can reply on the issue with their evidence
of permission. The maintainers decide, and the theme stays down meanwhile.
