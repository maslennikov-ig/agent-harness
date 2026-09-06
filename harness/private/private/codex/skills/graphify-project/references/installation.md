# Graphify Installation Fallbacks

Read this only when `graphify` is unavailable or the current installation lacks a required parser.

Prefer `uv tool install graphifyy`, then `pipx install graphifyy`, then `pip install --user graphifyy`.

If the latest package fails while building a native `tree-sitter-*` dependency because the machine lacks `gcc`/`cc`, prefer a user-space compiler before requesting system packages:

```bash
npm install -g @ziglang/cli
ln -sf "$(npm prefix -g)/bin/zig" "$HOME/.local/bin/zig"
CC="$HOME/.local/bin/zig-cc-python" uv tool install --force --python 3.12 graphifyy
```

The `zig-cc-python` wrapper should call `zig cc` and filter only `-Wl,--exclude-libs,ALL`, which Zig's linker does not support. If a user-space compiler is unacceptable or unavailable, use the last known working version only as a fallback, for example `uv tool install --python 3.12 graphifyy==0.8.18`.

If a relevant repo contains `.sql` files and Graphify reports missing `tree_sitter_sql`, do not accept an incomplete database graph silently. When dependency installation is authorized, keep the same Graphify version and add its official SQL extra, for example `uv tool install --upgrade 'graphifyy[sql]==<current-version>'`, then rebuild and verify SQL nodes are present.
