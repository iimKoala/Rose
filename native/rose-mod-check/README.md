# rose-mod-check

LTK Manager's own mod check and repair as a separate program. Rose runs it on a mod as it is added (the Mod store too), so LTK Manager never has to open.

- Rules: [LeagueToolkit/ltk-manager](https://github.com/LeagueToolkit/ltk-manager), `crates/ltk-manager-problems`, tag `v1.33.0`, called the way LTK Manager's mod health check (`crates/ltk-manager-library/src/mods/health.rs`) and its archive repair (`crates/ltk-manager-library/src/mods/archive/repair.rs`) call them.
- The repair's edit is LTK Manager's `RepairEdit` (`crates/ltk-manager-library/src/mods/archive/repair/delta.rs`), included in `src/main.rs`, writing to a new file instead of over the mod.
- An archive the edit refuses (most often one that ships its WADs as loose files) is repaired the long way round, as LTK Manager's `repair_in_staging` does: unpacked into a folder in `%TEMP%`, fixed there, and packed whole into the new file.
- License: GPL-3.0-or-later, like the code it calls and includes (see `LICENSE`). Rose itself stays MIT: it only runs this program and reads what it prints.
- Name tables: LTK Manager's cache in `%LOCALAPPDATA%\LeagueToolkit\hashes`, opened read-only. Nothing is downloaded.
- `Cargo.lock` is LTK Manager's from v1.33.0, so every library is the version LTK Manager was built with.
- One flaw these rules name and never repair, a number stored wider than the game reads (`bin/property-type`, for example `StaticMaterialDef.type` as 32 bits where the game reads 8 since patch 16.18), is repaired by Rose itself when the number fits: `injection/tools/int_widths.py`, Rose's own code. The rules then check the repaired mod again and have the last word.

Build (from Rose's folder):

    cargo build --release --manifest-path native/rose-mod-check/Cargo.toml

then copy `native/rose-mod-check/target/release/rose-mod-check.exe` to `injection/tools/rose-mod-check.exe`.

The program is not kept in git. A build writes the paths of its sources into the program, and those start
with the builder's user folder; for a copy that is given to others, build with

    RUSTFLAGS="--remap-path-prefix=<your user folder>=C:\Users\builder"

It is shipped in `rose-tools.zip` (see `docs/install-from-github.md`), with this folder as its source.

Check:

    rose-mod-check "Talon Mahoraga.fantome" --league "C:/Riot Games/League of Legends"

prints `{"health": "healthy"|"repairable"|"unrepairable", "fixable": n, "counts": {...}, "rules": [...]}`.

Repair (a .fantome; the mod itself is never changed):

    rose-mod-check "Talon Mahoraga.fantome" --repair "repaired.fantome" --league "C:/Riot Games/League of Legends"

prints the repaired copy's verdict plus `"repaired": fixes applied` and `"output"` (null when nothing was applied and no file was written).

To move to a newer LTK Manager, change the three `tag = "v1.33.0"` in `Cargo.toml`, copy that release's `Cargo.lock`, and compare `RepairEdit` in its `delta.rs` with the copy in `src/main.rs`.
