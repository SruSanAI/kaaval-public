# Contributing to Kaaval

Thanks for helping. Bug reports, ideas and pull requests are all welcome.

## Before you start

- **Questions and ideas:** [Discussions](https://github.com/SruSanAI/kaaval-public/discussions).
- **Bugs:** open an [issue](https://github.com/SruSanAI/kaaval-public/issues/new/choose) using the bug template.
- **Security problems:** never in public. See [SECURITY.md](SECURITY.md).
- **Bigger changes:** open an issue first, so we agree on the approach before you spend time on it.

## Set up

```bash
git clone https://github.com/SruSanAI/kaaval-public && cd kaaval-public
pip install volare flask && volare enable --pdk sky130 c6d73a35f524070e85faff4a6a9eef49553ebc2b   # and ngspice (tested with ngspice-47)
KAAVAL_PORT=5110 python -m app.server   # http://127.0.0.1:5110
for t in tests/test_*.py; do python "$t" || break; done
```

## Before you open a pull request

- `for t in tests/test_*.py; do python "$t" || break; done` passes.
- For a bug fix, the new test fails without the fix and passes with it.
- Docs and `CHANGELOG.md` (under *Unreleased*) are updated for anything a user would notice.

## Pull requests

One topic per PR, with what changed and why. CI must be green.

Kaaval is not open source (see [LICENSE](LICENSE)); please open an issue before any pull request. By contributing you assign your contribution to the copyright holder and agree to its use under the project's licence, and to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
