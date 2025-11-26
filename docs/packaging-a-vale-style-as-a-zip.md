# Packaging a Vale style as a ZIP (with Tengo scripts & vocabulary)

This guide describes shipping a Vale v3 style as a single distributable ZIP
that includes:

- one or more styles (YAML rules);
- Tengo scripts for custom rules and/or fix-suggestion actions;
- vocabulary lists (accept/reject) and optional Hunspell dictionaries.

It also covers referencing the package via `Packages` + `vale sync`.

______________________________________________________________________

## 1) Repository layout (before zipping)

Style repositories typically follow this structure:

```text
.
├─ .vale.ini                  # “complete package” config (points at styles/)
└─ styles/
   ├─ MyStyle/                # style rules (YAML)
   │  ├─ 00-Intro.yml
   │  └─ MyRule.yml
   └─ config/                 # shared resources for all styles
      ├─ scripts/             # Tengo for `extends: script` rules
      │  └─ MyScript.tengo
      ├─ actions/             # Tengo for suggestion/fixer actions
      │  └─ CamelToSnake.tengo
      ├─ vocabularies/        # per-vocabulary name directories
      │  └─ myvocab/
      │     ├─ accept.txt
      │     └─ reject.txt
      └─ dictionaries/        # optional Hunspell .dic/.aff
         ├─ en_GB.dic
         └─ en_GB.aff
```

**Why these paths?** Vale resolves non-style resources under `styles/config/*`:

- **`config/scripts/`** is the search root for `script:` in `extends: script`
  rules.
- **`config/actions/`** is the search root for Tengo scripts used by
  `action: { name: suggest }` fixers.
- **`config/vocabularies/<name>/accept.txt|reject.txt`** ships organisation
  vocab.
- **`config/dictionaries/`** ships Hunspell files for spelling rules (optional).

______________________________________________________________________

## 2) Minimal rule wiring

### (a) A Tengo-backed rule

```yaml
# styles/MyStyle/MyRule.yml
extends: script
message: 'Custom structural check fired.'
level: warning
scope: raw            # or 'sentence', etc., as needed
script: MyScript.tengo  # resolved from styles/config/scripts/
```

Place `MyScript.tengo` in `styles/config/scripts/`.

### (b) A rule with a Tengo suggestion action (fixer)

This pattern applies when the rule itself is regex-driven but dynamic
suggestions are required:

```yaml
# styles/MyStyle/CamelToSnake.yml
extends: existence
message: "'%s' should be snake_case."
nonword: true
level: error
tokens:
  - '[A-Z]\w+[A-Z]\w+'

action:
  name: suggest
  params:
    - CamelToSnake.tengo   # resolved from styles/config/actions/
```

Place `CamelToSnake.tengo` in `styles/config/actions/`.

> Tip: keep actions small and pure; return a single best suggestion or a short
> list.

______________________________________________________________________

## 3) Vocabulary files (accept/reject)

Ship a vocabulary named `myvocab`:

```text
styles/config/vocabularies/myvocab/accept.txt
styles/config/vocabularies/myvocab/reject.txt
```

- **`accept.txt`**: words/terms to *allow* (prevent false positives).
- **`reject.txt`**: words/terms to *discourage* (raise alerts if seen).

Lines are one token per line; keep them canonical (e.g., “microservice”,
“WebSocket”), and prefer the singular base form unless inflected variants are
required.

To use this vocab in the package’s own config (see §4), set `Vocab = myvocab`.
Consumers can keep that or override with their own.

______________________________________________________________________

## 4) The package’s `.vale.ini`

Include a minimal config at the root of the ZIP that points at `styles/` and
records any bundled vocabulary. Leave `BasedOnStyles` sections to the consumer
so they can decide which files opt into the package:

```ini
# .vale.ini (inside the ZIP)
StylesPath = styles
Vocab = myvocab
```

This makes the ZIP a **complete package**: when a consumer syncs it, Vale knows
where to load everything.

______________________________________________________________________

## 5) Build the ZIP

From the repo root:

```bash
zip -r MyStyle-1.2.3.zip .vale.ini styles/
```

Attach `MyStyle-1.2.3.zip` to a GitHub Release (or host it anywhere with a
stable URL).

If a `stilyagi.toml` manifest exists at the repository root, include it in the
archive, so consumers can pick up install defaults without extra flags:

```bash
zip -r MyStyle-1.2.3.zip .vale.ini styles/ stilyagi.toml
```

Version ZIPs (e.g., SemVer) so consumers can pin or upgrade deterministically.

______________________________________________________________________

## 6) How consumers install and use it

In the **consuming** repository:

### .vale.ini

```ini
# Consumer project
StylesPath = .github/styles

# Point to the release asset; multiple packages allowed (order = precedence)
Packages = https://github.com/example/vale-style/releases/download/v1.2.3/MyStyle-1.2.3.zip

# Optionally extend/override the package defaults:
[*.{md,adoc,txt}]
BasedOnStyles = Vale, MyStyle
Vocab = myvocab
```

Then:

```bash
vale sync   # downloads/merges the package into StylesPath
vale .      # lint the repo
```

Notes:

- If multiple packages are listed, later entries take precedence when files
  collide.
- Consumers can override any packaged file by adding replacements under their
  local `StylesPath`.

______________________________________________________________________

## 7) Sanity checks

After `vale sync`, confirm the resources are visible:

- Packaged rules appear under the configured style name (`MyStyle`).
- A rule that references `MyScript.tengo` triggers as expected on sample text.
- A token in `reject.txt` raises an alert; a token in `accept.txt` is ignored
  by the packaged spelling/term rules.

A quick project-local smoke test:

```bash
printf 'THISNeedsFixing\n' | vale --ext=.txt -
```

The `CamelToSnake.yml` message and a suggested fix should be emitted.

______________________________________________________________________

## 8) Private distribution & alternatives (optional)

- **Vendoring via Git**: instead of `Packages`, consumers can vendor the repo
  (or a release) into their tree (e.g., as a submodule) and set `StylesPath`
  accordingly. This avoids external fetches but shifts updates to Git ops.
- **Multiple styles per ZIP**: several style folders can reside under
  `styles/` and reference them all from `.vale.ini`.

______________________________________________________________________

## 9) Release checklist

- [ ] All rule YAML under `styles/MyStyle/…`
- [ ] All `extends: script` Tengo in `styles/config/scripts/`
- [ ] All suggestion/fixer Tengo in `styles/config/actions/`
- [ ] Vocab in `styles/config/vocabularies/<name>/(accept|reject).txt`
- [ ] Optional Hunspell in `styles/config/dictionaries/`
- [ ] Root `.vale.ini` points `StylesPath = styles` and enables the packaged
      style/vocab
- [ ] Versioned ZIP built from `.vale.ini` + `styles/`
- [ ] Release asset URL stable and documented for consumers

Ship it; consumers `vale sync` it; everyone gets the same rules, scripts, and
vocabulary, versioned and reproducible.
