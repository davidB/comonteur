# Troubleshooting a project that looks broken after reopening

Symptoms here showed up fine before, in an earlier session — the fix is almost never new
code, it's finding what stopped resolving.

## Glyphs render as rectangles ("tofu")

Not a Blender GPU glitch — a font failed to load. Check the Info Editor / startup log for:

```
Could not find '<file>' in '<dir>'
```

That message means the font was never linked from `lib/design.blend` in the first place —
it was loaded as a bare external path (`bpy.data.fonts.load("assets/fonts/...")`), which
only resolves against whatever the process's working directory happened to be at load
time. `cmt.library.link()` resolves against the project root instead (finds `.comonteur/`
walking up from the current `.blend`), so it doesn't have this failure mode — see `api.md`'s
`cmt.library` section for the link-from-`lib/design.blend` pattern, and convert an old shot
to it if you find one still calling `bpy.data.fonts.load()` directly.

Fix for an already-broken `.blend`: **File > External Data > Find Missing Files**, point it
at `assets/fonts/` (or wherever the `.ttf`/`.otf` files live), and Blender relinks the VFonts
by filename. Per Text object, you can also force a reload from the Font properties panel's
font dropdown.

## "Asset Library 'Online Essentials'" errors in the log

```
Asset Library 'Online Essentials': Couldn't read V1 listing from ...
Could not read asset listing 'Online Essentials', see Info Editor for details
```

This is Blender's own bundled remote asset library (materials/HDRIs browser), backed by a
cache under the user's home directory — nothing to do with a comonteur project. Don't chase
it when debugging project data; it's cosmetic to this tool.
