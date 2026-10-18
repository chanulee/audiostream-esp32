# AS-007 rev A — kicad-happy audit (2026-10-18)

Tool: [aklofas/kicad-happy](https://github.com/aklofas/kicad-happy) @ 6a91aaa (2026-10-14), KiCad 10.0.6, ngspice.
Analyzer JSON: `work/kicad-happy-as007/` (not tracked). No hardware has been measured; everything below is design-file evidence.

**Verdict: Y.** I found no defect that would stop the board from powering up, enumerating over USB or playing audio.
The remaining risk is in things no file check can prove: the PJ-320D contact mapping (wrong twice before),
RF in the enclosure, and eFuse margin under Wi-Fi current peaks.

## Test results

| Check | Result |
|---|---|
| KiCad DRC (re-run) | 0 violations, 0 unconnected |
| KiCad ERC (re-run) | 0 |
| `pinout_check.py` | 142 / 142 |
| `audit_pcb.py` | readback OK, decoupling 19/19, library pads 54/54, top-pad vias 0, AUX order LINE_R·GND·GND·LINE_L, silk AS-007 rev A |
| Release Gerbers vs fresh export | identical on In1/In2/B.Cu, masks, paste, outline, silk; F.Cu differs by 1 redundant zone vertex |
| `analyze_schematic.py` | 4 error / 3 warning, all triaged below (0 real) |
| `analyze_pcb.py --full --proximity` | 7 error / 23 warning, all triaged (0 blocking) |
| `analyze_gerbers.py` | 0 findings |
| `cross_analysis.py` | 5 info |
| `analyze_emc.py` | 3 error / 12 warning, score 41.5/100 — heuristic, triaged below |
| SPICE (`simulate_subcircuits.py` + PCB parasitics) | 15 / 15 pass |
| `analyze_thermal.py` | skipped by tool (no MPN field) — hand calc: LDO ≈ 45 mW, no hotspot |
| Lifecycle audit | not run (no MPN field); `reports/jlc.json` stock ≥ 100 on 2026-10-15 |

## Datasheet checks done in this session

- **TPS259470A (U6), TI SLVSFC9C rev May 2026, Table 5-1:** pins 1 EN/UVLO, 2 OVLO, 3 AUXOFF, 4 FLT, 5 IN, 6 OUT, 7 DVDT, 8 GND, 9 ILM, 10 ITIMER match the netlist. FLT/AUXOFF open-drain NC and ITIMER open ("fastest response") are allowed. UVLO 1.20 V × 3.55 = 4.26 V, OVLO 1.20 V × 4.83 = 5.80 V, ILIM = 3334 / 5.1 k = 0.65 A (R_ILM range 549–6650 Ω).
- **PCM5102A (U2), TI SLAS859:** pin 1–20 assignment matches; LDOO 0.1 µF (Table 12), 470 Ω + 2.2 nF output filter (spec footnote 3); SCK = GND (internal PLL), FMT = GND (I2S).
- Other ICs (WROVER-E, TPS62162, TPS7A2033, USBLC6, CH340N, HRO TYPE-C-31-M-12) compared against the published pinouts. CH340N VCC = V3 = 3.3 V is the datasheet's 3.3 V configuration.

## False positives (reviewed, dismissed)

| Finding | Why it is not a problem |
|---|---|
| DS-001 / SS-001 no MPNs | Parts are fixed by LCSC numbers; the tool reads only an `MPN` field |
| VM-001 USB_DP/DM 5 V↔3.3 V | Tool inferred 5 V from USBLC6 VBUS pin; CH340N runs at 3.3 V |
| UC-003 CC1/CC2 missing 5.1 k | R1/R2 5.1 k to GND exist |
| PU-001 U3 PG pull-up | PG unused (NC) |
| RT-001 U6 FLT/ITIMER unrouted | L-shaped corner pads made of two overlapping pads of the same number |
| KO-001 U1/H1/J1 in keepout | Intended keep-outs (module, screw head, USB escape) |
| PM-002 J2/U1/J1 overhang | Intended (nozzle, antenna, shell) — handled by left/right rails |
| VP-001 vias in pads | Bottom test pads; no paste, no parts on bottom |
| TE-001 0 % test points | Tool does not recognize the 11 bottom pads |
| PS-002 / connectivity islands | Analyzer union-find; KiCad reports 0 unconnected |
| GP-001 OVLO plane gap, RP-001, CK-001, DP-003/004, SW-001 | DC/low-speed nets, 5 mm I2S over solid L2 GND, USB full-speed 12 Mbit/s, 3.3 mm skew is irrelevant at that rate |
| FD-001 no fiducials | JLC rails carry fiducials |

## Improvements, ranked

1. **(No copper change, before ordering)** Buy 2–3 loose PJ-320D (LCSC C431535) and a 3.5 mm TRS plug; meter Tip→A, Ring→D, Sleeve→B+C. This removes the one risk that was wrong in two earlier versions.
2. **(No copper change)** On the order, ask for left/right rails with mouse-bites, not V-cut. C15 (0603 MLCC) is 0.97 mm and D3 0.55 mm from the right edge; snapping a V-cut that close can crack MLCCs.
3. **(No copper change)** Add `MPN`/`Manufacturer` fields in `plan_pcb.py` so lifecycle, thermal and datasheet checks can run.
4. **(Copper → AS-008, only if bundled with another change)** The 4 USB_DM vias at 0.4 / 0.2 mm sit on JLC's multilayer "limitation" (standard minimum diameter 0.45 mm). Make them 0.45 / 0.2.
5. **(Copper, optional)** DNP 0402 pad from U6 ITIMER to GND. If Wi-Fi peaks trip the 0.56 A worst-case limit on the first board, fit 1–10 nF without a respin.
6. **Size:** at 76 % occupancy with the module, J1 and J2 setting the outline, no shrink is free. Dropping CH340N + USBLC6 (flash over the TX/RX pads, then OTA) is the only real saving, but it changes the bring-up path. Not recommended before the first board works.

## Still open from earlier reviews

D4 LED polarity is unconfirmed (only the LED is affected if it's wrong). C25 derating is above 5.67 V only. RF/coexistence and pop behaviour are unmeasured (REVIEW.md 6, 3).
