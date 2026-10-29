# Changelog

All notable changes to Kaaval. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-11-04

First public release, for the Meta Global AI Developer Hackathon.

### Added
- Text-only xschem and SPICE netlister; nothing in a reviewed repository is executed.
- Power-up from 0 V, second-state, loop-stability and saturation-margin checks at 5 corners x 3 temperatures x 3 supplies (ngspice + open sky130).
- Chip-context sequence check: rail order and gap, ramp speed, late enables and resets, the Tiny Tapeout pad path; failures name the gap where they start.
- Muse Spark planner (Meta Model API): block functions, pin roles with evidence, JSON test plans validated by the engine.
- Review page: findings on the schematic, sequence matrix, power-up waveforms, Bode plots.

[Unreleased]: https://github.com/SruSanAI/kaaval-public/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/SruSanAI/kaaval-public/releases/tag/v0.1.0
