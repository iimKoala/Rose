//! rose-mod-check: LTK Manager's own mod check and repair, run without LTK Manager.
//!
//! The rules are LTK Manager's (crates/ltk-manager-problems, tag v1.33.0,
//! https://github.com/LeagueToolkit/ltk-manager), called the way its mod health
//! check calls them (crates/ltk-manager-library/src/mods/health.rs) and the way
//! its repair calls them (crates/ltk-manager-library/src/mods/archive/repair.rs,
//! repair_in_archive, and repair_in_staging for an archive the edit refuses).
//! Rose runs this as a separate program and reads the JSON it prints.
//!
//! Check:  rose-mod-check <mod.fantome|.zip|.modpkg> [--league <League of Legends folder>]
//! Repair: rose-mod-check <mod.fantome> --repair <output.fantome> [--league <folder>]
//!
//! Prints one JSON verdict on stdout with the fields of LTK Manager's
//! ModHealthVerdict: health, fixable, counts, rules. A repair adds "repaired"
//! (fixes applied) and "output" (the repaired copy, or null when nothing was
//! applied and no file was written); its verdict is the repaired copy's. The
//! mod itself is never changed. Exit code 0: done; 1: the mod could not be read
//! or repaired ({"error": ...}); 2: wrong command line.

use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::sync::Arc;

use camino::Utf8Path;
use ltk_fantome::{ArchiveDelta, FantomeHashtable, FantomeReader, apply_delta, is_layer_name, wad_entry_name};
use ltk_hashtable::Category;
use ltk_manager_assets::hashtables::WadPathResolver;
use ltk_manager_assets::mod_archive::open_fantome;
use ltk_manager_base::budget::Budget;
use ltk_manager_base::config::Config;
use ltk_manager_problems::{
    self as problems, Counts, FileChange, FileOutcome, FixReport, GameContent, HeldWrites, InstalledContent, KeptTable,
    ProjectFiles, Run,
};
use ltk_mod_project::fantome::{FantomeFormat, FantomeImporter};
use ltk_mod_project::{ModProject, ModProjectLayer, ProjectImporter, ProjectPacker};
use ltk_wad::{PathResolver, WadHash, chunk_hash_of};
use serde_json::{Value, json};

/// Repairs in a row while fixes are still offered: one pass can leave a fix for
/// the next (a rule skips a file an earlier rule of the same pass rewrote)
const REPAIR_PASSES: usize = 3;

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    let mut archive: Option<PathBuf> = None;
    let mut league: Option<PathBuf> = None;
    let mut output: Option<PathBuf> = None;
    while let Some(arg) = args.next() {
        if arg == "--league" {
            league = args.next().map(PathBuf::from);
        } else if arg == "--repair" {
            output = args.next().map(PathBuf::from);
            if output.is_none() {
                return usage();
            }
        } else if archive.is_none() {
            archive = Some(PathBuf::from(arg));
        } else {
            return usage();
        }
    }
    let Some(archive) = archive else {
        return usage();
    };

    let mut config = Config::default();
    config.league_path = league;
    // None without a League install: a rule that needs the game then says so instead of guessing
    let game = InstalledContent::resolve(&config).map(|content| Arc::new(content) as Arc<dyn GameContent>);
    // LTK Manager's shared hashtable cache (%LOCALAPPDATA%\LeagueToolkit\hashes), opened read-only
    let resolver = WadPathResolver::discover();

    let result = match &output {
        None => check(&archive, &config, &resolver, &game).map(|run| verdict(&run)),
        Some(output) => repaired(&archive, output, &config, &resolver, &game),
    };
    match result {
        Ok(answer) => {
            println!("{answer}");
            ExitCode::SUCCESS
        }
        Err(error) => {
            println!("{}", json!({ "error": error }));
            ExitCode::from(1)
        }
    }
}

fn usage() -> ExitCode {
    eprintln!("usage: rose-mod-check <mod.fantome|.zip|.modpkg> [--repair <output.fantome>] [--league <League of Legends folder>]");
    ExitCode::from(2)
}

/// One pass of every rule, as LTK Manager's mod health check runs it
fn check(archive: &Path, config: &Config, resolver: &WadPathResolver, game: &Option<Arc<dyn GameContent>>) -> Result<Run, String> {
    let is_modpkg = archive.extension().is_some_and(|ext| ext.eq_ignore_ascii_case("modpkg"));
    let files = if is_modpkg {
        ProjectFiles::in_modpkg(archive, config, Budget::repair(), game.clone())
    } else {
        ProjectFiles::in_archive(archive, config, Budget::repair(), resolver, game.clone())
    };
    files.map(|files| files.without_game_copies().checked()).map_err(|error| error.to_string())
}

/// Worded as LTK Manager's ModHealthVerdict::from_run and rule_briefs word it
fn verdict(run: &Run) -> Value {
    let counts = Counts::over(run.live_problems());
    let fixable = run.live_problems().filter(|problem| problem.fix.is_some()).count();
    let wrong = counts.fatals + counts.errors + counts.warnings;
    let health = if wrong == 0 {
        "healthy"
    } else if fixable > 0 {
        "repairable"
    } else {
        "unrepairable"
    };
    let mut rules = Vec::new();
    for rule in &run.rules {
        let found: Vec<_> = run.live_problems().filter(|problem| problem.rule == rule.id).collect();
        // The ladder runs worst-first, so the worst finding is the least
        if let Some(worst) = found.iter().map(|problem| problem.severity).min() {
            rules.push(json!({
                "rule": rule.id.to_string(),
                "title": &rule.title,
                "description": &rule.description,
                "severity": worst,
                "count": found.len(),
                "fixable": found.iter().filter(|problem| problem.fix.is_some()).count(),
            }));
        }
    }
    json!({ "health": health, "fixable": fixable, "counts": counts, "rules": rules })
}

/// Repair `archive` into `output` and answer with the repaired copy's verdict.
///
/// LTK Manager's repair_in_archive, with the edit written to a new file instead
/// of over the archive. Only a .fantome (a .zip is one) is repaired here.
fn repaired(
    archive: &Path,
    output: &Path,
    config: &Config,
    resolver: &WadPathResolver,
    game: &Option<Arc<dyn GameContent>>,
) -> Result<Value, String> {
    if archive.extension().is_some_and(|ext| ext.eq_ignore_ascii_case("modpkg")) {
        return Err("a .modpkg is not repaired by rose-mod-check".to_string());
    }
    let output_utf8 = Utf8Path::from_path(output).ok_or("the output path is not UTF-8")?;
    let mut source = archive.to_path_buf();
    let mut applied = 0u32;
    for _ in 0..REPAIR_PASSES {
        let project = ProjectFiles::in_archive(&source, config, Budget::repair(), resolver, game.clone())
            .map_err(|error| error.to_string())?;
        let run = project.checked();
        let wanted = run.live_fixable();
        if wanted.is_empty() {
            break;
        }
        let declared = open_fantome(&source)
            .map_err(|error| error.to_string())?
            .read_hashtables()
            .map_err(|error| error.to_string())?;
        let exclusions: &dyn PathResolver = resolver;
        let (report, held) = problems::apply_held(project, declared, &run, &wanted, config, Some(exclusions), game.clone())
            .map_err(|error| error.to_string())?;
        if report.applied == 0 {
            break;
        }
        let source_utf8 = Utf8Path::from_path(&source).ok_or("the mod path is not UTF-8")?;
        let edited = held_delta(&held, source_utf8, &report)
            .and_then(|delta| apply_delta(source_utf8, output_utf8, &delta, None).map_err(|error| error.to_string()));
        let fixed = match edited {
            Ok(_) => report.applied,
            // The edit refuses an archive it cannot rebase, most often one that ships its WADs as loose
            // files. LTK Manager then goes the long way round (repair_in_staging), and so does this.
            Err(refusal) => repaired_in_staging(&source, output_utf8, config, resolver, game)
                .map_err(|error| format!("Failed to edit {source_utf8} ({refusal}) and to repack it: {error}"))?,
        };
        if fixed == 0 {
            break;
        }
        applied += fixed;
        source = output.to_path_buf();
    }
    let run = check(&source, config, resolver, game)?;
    let mut answer = verdict(&run);
    answer["repaired"] = json!(applied);
    answer["output"] = if applied > 0 { json!(output.to_string_lossy()) } else { Value::Null };
    Ok(answer)
}

/// Repair `archive` the long way round: unpack it as a project, fix it there, and pack it whole into
/// `output`. Returns the fixes applied; with 0 nothing is written.
///
/// LTK Manager's repair_in_staging and repack (v1.33.0, GPL-3.0-or-later:
/// crates/ltk-manager-library/src/mods/archive/repair.rs), packing into a new file instead of over the archive.
fn repaired_in_staging(
    archive: &Path,
    output: &Utf8Path,
    config: &Config,
    resolver: &WadPathResolver,
    game: &Option<Arc<dyn GameContent>>,
) -> Result<u32, String> {
    let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |since| since.as_nanos());
    // shortcut: a run that is killed leaves this folder in %TEMP%; give it a cleanup if that ever shows
    let staging = std::env::temp_dir().join(format!("rose-mod-check-{}-{stamp}", std::process::id()));
    std::fs::create_dir_all(&staging).map_err(|error| format!("Could not create {}: {error}", staging.display()))?;
    let outcome = fixed_in(&staging, archive, output, config, resolver, game);
    let _ = std::fs::remove_dir_all(&staging);
    outcome
}

/// The work of [`repaired_in_staging`], inside its staging directory.
fn fixed_in(
    staging: &Path,
    archive: &Path,
    output: &Utf8Path,
    config: &Config,
    resolver: &WadPathResolver,
    game: &Option<Arc<dyn GameContent>>,
) -> Result<u32, String> {
    let staging_utf8 = Utf8Path::from_path(staging).ok_or("the staging path is not UTF-8")?;
    let exclusions: &dyn PathResolver = resolver;
    let packed = std::fs::File::open(archive).map_err(|error| format!("Could not read {}: {error}", archive.display()))?;
    ProjectImporter::new(staging_utf8.to_path_buf())
        .import(FantomeImporter::new(packed).with_path_resolver(exclusions))
        .map_err(|error| format!("Failed to unpack the archive: {error}"))?;
    let run = problems::analyze_within(staging, config, Budget::repair(), game.clone()).map_err(|error| error.to_string())?;
    let wanted = run.live_fixable();
    if wanted.is_empty() {
        return Ok(0);
    }
    let report = problems::apply(staging, &run, &wanted, config, Some(exclusions), game.clone()).map_err(|error| error.to_string())?;
    if report.applied == 0 {
        return Ok(0);
    }
    let project = ModProject::load(staging_utf8).map_err(|error| error.to_string())?;
    let writer = std::io::BufWriter::new(std::fs::File::create(output).map_err(|error| format!("Could not write {output}: {error}"))?);
    ProjectPacker::new(project, staging_utf8.to_path_buf())
        .pack(FantomeFormat::new(writer))
        .map_err(|error| format!("Failed to pack the repaired mod: {error}"))?;
    Ok(report.applied)
}

// The repair's edit, from LTK Manager v1.33.0 (GPL-3.0-or-later):
// crates/ltk-manager-library/src/mods/archive/repair/delta.rs (RepairEdit::held, assemble,
// DeltaTarget, declare_held_table, free_archive_table_path), with its errors as text.

/// The suffix that makes a layer directory one of the mod's WADs.
const WAD_DIR_SUFFIX: &str = ".wad.client";
/// Where an unpack writes the archive's `RAW/` entries, under the base layer.
const RAW_DIR: &str = "raw";
/// Where an archive keeps the hashtable files its metadata declares.
const ARCHIVE_HASHES_DIR: &str = "META/hashes";
/// The entry that holds an archive's metadata.
const ARCHIVE_INFO: &str = "META/info.json";

/// What `report` applied out of `held`, a run that wrote nothing to disk (RepairEdit::held).
fn held_delta(held: &HeldWrites, archive: &Utf8Path, report: &FixReport) -> Result<ArchiveDelta<'static>, String> {
    let mut delta = assemble(report, |file| {
        held.bytes(&file.layer, &file.path)
            .map(<[u8]>::to_vec)
            .ok_or_else(|| format!("The run holds no bytes for {}/{}", file.layer, file.path))
    })?;
    if let Some(table) = held.table() {
        declare_held_table(&mut delta, table, archive)?;
    }
    Ok(delta)
}

/// The delta for `report`, with `bytes_of` supplying each written file's bytes.
fn assemble(report: &FixReport, bytes_of: impl Fn(&FileOutcome) -> Result<Vec<u8>, String>) -> Result<ArchiveDelta<'static>, String> {
    let mut delta = ArchiveDelta::new();
    for file in &report.files {
        // A file a rule read but did not change was never written. Its bytes
        // are the archive's, and re-encoding them would change the mod.
        if file.change == FileChange::Unchanged {
            continue;
        }
        let target = DeltaTarget::of(&file.layer, &file.path)
            .ok_or_else(|| format!("A Fantome archive has no place for {}/{}", file.layer, file.path))?;
        match file.change {
            FileChange::Removed => match target {
                DeltaTarget::Chunk { wad, hash } => delta.remove_chunk(&file.layer, &wad, hash),
                DeltaTarget::Entry { path } => delta.remove_entry(&path),
            },
            FileChange::Unchanged => continue,
            FileChange::Written => {
                let bytes = bytes_of(file)?;
                match target {
                    DeltaTarget::Chunk { wad, hash } => delta.chunk(&file.layer, &wad, hash, bytes),
                    DeltaTarget::Entry { path } => delta.entry(&path, bytes),
                }
            }
        };
    }
    Ok(delta)
}

/// What one repaired file of a project addresses in the archive it came from.
#[derive(Debug, Clone, PartialEq, Eq)]
enum DeltaTarget {
    /// A chunk of a packed WAD in the file's layer, keyed by its path hash.
    Chunk { wad: String, hash: WadHash },
    /// A whole archive entry, by its entry name.
    Entry { path: String },
}

impl DeltaTarget {
    /// What the repaired `path` of `layer` addresses; `None` for a layer name no WAD directory can hold.
    fn of(layer: &str, path: &str) -> Option<Self> {
        if !is_layer_name(layer) {
            return None;
        }
        Some(match path.split_once('/') {
            Some((dir, rest)) if dir.to_ascii_lowercase().ends_with(WAD_DIR_SUFFIX) => Self::Chunk {
                wad: dir.to_owned(),
                hash: chunk_hash_of(Utf8Path::new(rest)),
            },
            Some((RAW_DIR, rest)) if layer == ModProjectLayer::BASE_NAME => Self::Entry {
                path: format!("RAW/{rest}"),
            },
            _ => Self::Entry {
                path: wad_entry_name(layer, path),
            },
        })
    }
}

/// Declare the name table a repair kept in the archive's metadata.
fn declare_held_table(delta: &mut ArchiveDelta<'static>, table: &KeptTable, archive: &Utf8Path) -> Result<(), String> {
    let mut info = std::fs::File::open(archive)
        .map_err(|error| format!("Could not read {archive}: {error}"))
        .and_then(|file| {
            FantomeReader::new(file)
                .and_then(|mut reader| reader.read_info())
                .map_err(|error| format!("Could not read {archive}'s metadata: {error}"))
        })?;
    let path = match &table.into {
        Some(entry) => entry.path().to_string(),
        None => free_archive_table_path(&info.hashtables),
    };
    delta.entry(&path, table.bytes.clone());
    if !info.hashtables.iter().any(|held| held.path.eq_ignore_ascii_case(&path)) {
        let (algorithm, width) = &table.shape;
        info.hashtables.push(FantomeHashtable {
            path,
            category: Category::Game,
            algorithm: algorithm.clone(),
            bits: width.bits(),
        });
        let written = serde_json::to_vec_pretty(&info).map_err(|error| format!("Could not write {archive}'s metadata: {error}"))?;
        delta.entry(ARCHIVE_INFO, written);
    }
    Ok(())
}

fn free_archive_table_path(manifests: &[FantomeHashtable]) -> String {
    let taken: Vec<String> = manifests.iter().map(|manifest| manifest.path.to_ascii_lowercase()).collect();
    std::iter::once(format!("{ARCHIVE_HASHES_DIR}/game.hashes.txt"))
        .chain((1..).map(|attempt| format!("{ARCHIVE_HASHES_DIR}/game.repaired{attempt}.hashes.txt")))
        .find(|candidate| !taken.contains(&candidate.to_ascii_lowercase()))
        .expect("the candidate sequence is unbounded")
}
