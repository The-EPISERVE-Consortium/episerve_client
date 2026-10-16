"""Client version constant.

The committed value is a placeholder used by source checkouts. The release
workflow overwrites this file before building the binaries, so a released
``episerve`` binary reports its git tag (e.g. ``0.1.0``). See
``.github/workflows/build-binary.yml``.
"""

__version__ = "0.0.0.dev0"
