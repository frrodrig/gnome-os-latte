# Latte ALSA UCM profile

This profile is copied from `xiaomi-latte-dev/docs` `fix_file/audio/` at
commit `c0c672d128e4e0dac497b4af7b40fea64df6ec19`. Its kernel-tree history
attributes the original UCM rewrite and Linux Latte 7.2 adaptation to
[@Qs315490](https://github.com/Qs315490), including commits
`b2516c69d3df3739190b83eff57dec007fe08798` and
`29be1c193aeb211263d869b35cc96e03835f40c5`.

The user relayed on 2026-11-24 that the author confirmed the MIT license
continues to apply to this current profile. The upstream `docs` repository
does not itself include a license file or SPDX declaration for these files;
this notice records the confirmation relayed by the user. The accompanying
`LICENSE-MIT` preserves the license terms and attribution.

The board profile relies on the Latte kernel's RT5659/TFA9890 controls and
its `Left`/`Right` amplifier prefixes. The hardware author reports having
validated the routes, but this repository's build does not verify the audio
card or sound output on a physical tablet.
