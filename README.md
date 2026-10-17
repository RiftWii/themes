# RiftWii community themes

> **Draft.** This is a proposal for the RiftWii maintainers to discuss. It
> has not been published anywhere. See [Open questions](#open-questions).

A list of menu themes for [RiftWii](https://github.com/KakarottoCake/Riftwii),
made by its players. It is meant to live at
[github.com/RiftWii/themes](https://github.com/RiftWii/themes), and GitHub
Pages serves every theme as a zip under **https://riftwii.github.io/themes/**,
plus one `themes.json` there that lists them all
(https://riftwii.github.io/themes/themes.json). In future RiftWii could browse that
list and install a theme straight to the SD card. Until then, download a
zip, unpack it into `sd:/riftwii/themes/` and pick the theme under
Settings > **Theme**.

How to make a theme is in RiftWii's own
[docs/THEMES.md](https://github.com/KakarottoCake/Riftwii/blob/main/docs/THEMES.md)
and its theme kit (`themes/kit`). This repository only collects themes.

## Submit a theme

1. Read [CONTENT-RULES.md](CONTENT-RULES.md). In short: everything must be
   your own work, or work you may share; no Nintendo material at all; and
   the theme is licensed CC0, CC BY or CC BY-SA.
2. Fork this repository and add your theme as one folder,
   `themes/<YourTheme>/` (layout below).
3. Open a pull request. Fill in the description and tick every box.
4. The **validate** check runs. Fix anything it reports, and a maintainer
   reviews the theme. Once it is merged, **publish** adds it to the list
   within a few minutes.

To change a theme you submitted, open another pull request for the same
folder.

## A theme folder

```
themes/
  MyTheme/             the folder name: 1-32 letters, digits, _ or -
    theme.ini          required: name, author, colours, shape
    LICENSE            required: license, author and credits
    background.png     optional pictures, each exactly the size RiftWii needs
    tile.png
    tile_over.png
    music.ogg          optional menu music (Ogg Vorbis)
    click.wav          optional sound effects: hover, click,
                       home_open, home_close
```

The folder is copied as it is to `sd:/riftwii/themes/<folder>/`, so it
holds only files RiftWii uses:

- `theme.ini`, with `name` and `author` under `[theme]`;
- `LICENSE` (format in [CONTENT-RULES.md](CONTENT-RULES.md#the-license-file));
- any of the pictures listed in docs/THEMES.md, under the same name, at
  exactly the size listed there;
- `music.ogg`;
- `hover.wav`, `click.wav`, `home_open.wav`, `home_close.wav`.

There are no subfolders, hidden files, symlinks, previews or read-me
files: RiftWii would ignore them, and every extra byte is downloaded to a
Wii.

## What the check does

[validate.yml](.github/workflows/validate.yml) runs on every pull request.
It fails if:

- a box in the pull request description is not ticked;
- a file name is not one of those above, starts with a dot, or could climb
  out of the folder (`..`, `/`, `\`, `:`), or the entry is a symlink or a
  subfolder;
- a picture is not a valid PNG at exactly the size RiftWii needs;
- `theme.ini` has any line that RiftWii would skip, or no name or author;
- `music.ogg` or a sound is not in a format RiftWii plays, or is over a
  limit below;
- `LICENSE` does not name an allowed license or has no `Author:` line.

The picture list and the `theme.ini` parser are RiftWii's own. The check
builds a tiny program ([scripts/theme_check.cpp](scripts/theme_check.cpp))
against RiftWii's `src/art/theme.cpp`, so it accepts exactly what the Wii
accepts. When RiftWii adds a picture or a setting, the check knows at once.

It only warns, for a reviewer to look at, when a file's SHA-256 is in
[scripts/flagged-sha256.txt](scripts/flagged-sha256.txt), or when text in
`theme.ini`, `LICENSE`, PNG text or music tags mentions things like
"Nintendo" or "ripped from". No script can prove where a picture came from;
a person decides.

The scripts it runs come from the base branch, not from the pull request,
so a submission can't change the checks that judge it.

### Limits

| What | Limit | Why |
| --- | --- | --- |
| `theme.ini` | 64 KiB | RiftWii does not read a bigger one (`kMaxIni`) |
| Each PNG | 2 MiB, exact size | RiftWii skips bigger or wrong-sized pictures (`kMaxPng`) |
| `music.ogg` | 6 MiB, 6 minutes, Vorbis, 44.1/48 kHz | RiftWii skips music over 6 MiB. Six minutes is what 6 MiB holds at the quality docs/THEMES.md recommends, and a reviewer has to listen to all of it |
| Each sound WAV | 1 MiB, 5 s, 16-bit PCM | RiftWii's own limits for sound effects |
| Whole theme | 10 MiB | The largest music file plus about twice Bookshelf's pictures (2.2 MiB, the largest bundled theme). It keeps downloads on the Wii's Wi-Fi short and keeps about a hundred themes under GitHub Pages' 1 GB site limit |

## Publishing

[publish.yml](.github/workflows/publish.yml) runs on every push to `main`.
It checks every theme again, then builds the site:

- `themes/<folder>.zip`: the theme's files under `<folder>/`. The zips are
  deterministic (sorted entries, fixed dates and permissions), so a theme's
  SHA-256 only changes when the theme does.
- `previews/<folder>.png`: for now the theme's own `background.png`, if it
  has one. Rendering a real menu screenshot is a TODO. RiftWii's theme kit
  paints single pictures, not whole screens.
- `themes.json`, then deploys it to GitHub Pages:

```json
{
  "schema": 1,
  "commit": "<the commit it was built from>",
  "themes": [
    {
      "folder": "MyTheme",
      "name": "My Theme",
      "author": "RiftWii contributors",
      "license": "CC0-1.0",
      "size": 13673,
      "sha256": "…",
      "files": 5,
      "unpacked_size": 14029,
      "has_music": false,
      "zip": "https://riftwii.github.io/themes/themes/MyTheme.zip",
      "preview": "https://riftwii.github.io/themes/previews/MyTheme.png"
    }
  ]
}
```

The base URL in `themes.json` comes from [site-url.txt](site-url.txt), the
one place it is written down. Change that file if the site moves. The URLs
deliberately don't follow wherever Pages serves the repository, so a fork's
publish can't point the list somewhere else; publish.yml warns when the two
disagree.

## For a future in-app browser

This repository's checks make bad themes unlikely, but they are not a
security boundary for the Wii. RiftWii's AGENTS.md treats everything it
downloads as untrusted, and that holds here too. The index or a zip could
be swapped by anyone who gets write access to this repository or the
Pages site. So RiftWii itself must still:

- read `themes.json` with a size cap, and bound the number of entries and
  every string's length;
- compare the zip's size (`Content-Length`) with the index's `size`
  before downloading, and stop if it is larger;
- check the SHA-256 of the downloaded zip against the index before
  unpacking;
- while unpacking, bound the number of files and each file's unpacked
  size (the index's `files` and `unpacked_size` help), and refuse any name
  that is not a plain file name directly inside the theme's folder: no
  `..`, no `/` or `\` beyond the one folder, no absolute paths, the same
  rule as `theme_pack_name_ok()` for the update pack;
- unpack into a temporary folder and move it into place only when
  everything checked out.

No new certificate is needed. `riftwii.github.io` is covered by the
`*.github.io` certificate, which is served with a Let's Encrypt
certificate. On 2026-10-17 its chain was `*.github.io` ← YR1 ← ISRG
Root YR, cross-signed by **ISRG Root X1**, which RiftWii already trusts in
`wii/online/tlsroots.c` for release downloads. When Let's Encrypt stops
sending the cross-signed certificate, RiftWii would need to add ISRG Root
YR there.

## License

The scripts and workflows in this repository are GPL-3.0-or-later, like
RiftWii ([COPYING](COPYING)); each file says so in its SPDX header. Each
theme has its own license, given in its `LICENSE` file. The repository's
GPL does not apply to themes.

## Open questions

For the maintainers to decide before this goes public:

1. **RiftWii itself.** The checks build against `KakarottoCake/Riftwii`
   (`RIFTWII_REPO` in both workflows). If RiftWii moves into the RiftWii
   organization, change it there.
2. **Takedown contact and time.** CONTENT-RULES.md has
   `TODO-maintainer-contact` and `TODO-time` placeholders.
3. **Which RiftWii the checks follow.** `RIFTWII_REF` is `main`. A release
   tag would be steadier, but then a new picture or setting can't be used
   until the next release.
4. **Strict `theme.ini`.** The check fails on any line RiftWii would skip.
   That catches typos, but a theme written for a newer RiftWii (a new key)
   would fail against an older `RIFTWII_REF`.
5. **Theme kit templates.** Many themes will start from the kit's
   templates, which RiftWii's GPL code paints. Can a CC-licensed theme be
   built on them? A line in the kit's README saying the templates are CC0
   would settle it.
6. **Other licenses.** Is CC0 / CC BY / CC BY-SA the right set? Exceptions
   go in `scripts/approved-licenses.txt`.
7. **Size budget.** Is a 10 MiB theme limit right? If the list grows past
   Pages' 1 GB, the zips could move to GitHub Releases.
8. **AIFF sounds.** RiftWii plays AIFF and WAVE_FORMAT_EXTENSIBLE sounds,
   but the check (Python's `wave` module) reads only plain PCM WAV.
   Requiring plain WAV seemed simpler than a second parser.
9. **Previews.** Should the theme kit gain a mode that renders one menu
   screen, so publish can make real previews? Or should submitters add a
   screenshot?
10. **Folder names with spaces.** RiftWii allows them in theme folders;
   this repository doesn't, so URLs need no escaping.
