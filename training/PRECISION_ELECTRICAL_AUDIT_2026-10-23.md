# Precision electrical source audit - 2026-10-23

Recovery commit: `871ee61`. Baseline: `evidence/tonight-20261023/final-fresh`. Source inspection is independent of inference. This document does not feed any reference answer into recognition.

## All 14 native false pairs

| Source | Pair | Independent reference | Source diagnosis |
|---|---|---|---|
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | R34.1 -- U2.3 | GND / VBUS | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | R34.1 -- U2.6 | GND / V33IO | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | R34.1 -- U2.9 | GND / VBUS | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | U2.17 -- U2.3 | GND / VBUS | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | U2.17 -- U2.6 | GND / V33IO | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | U2.17 -- U2.9 | GND / VBUS | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | U2.2 -- U2.3 | GND / VBUS | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | U2.2 -- U2.6 | GND / V33IO | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | U2.2 -- U2.9 | GND / VBUS | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | U2.3 -- U2.6 | VBUS / V33IO | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-3b2a49a524e2d50dcf26](../evidence/precision-20261023/native-3b2a49a524e2d50dcf26.png) | U2.6 -- U2.9 | V33IO / VBUS | GND incorrectly propagated across decoupling capacitors C1/C2/C30. Pin 3 and 9 are VBUS; pin 6 is V33IO. Pins 2/17 and R34.1 are genuine GND. No unsupported split committed. |
| [native-a39a7a1fc84f921b27fd](../evidence/precision-20261023/native-a39a7a1fc84f921b27fd.png) | R1.1 -- R1.4 | LORA_RST / NONEXISTENT PHYSICAL PIN OR COMPONENT | R1 is an explicit two-terminal 10K resistor. Pin 4 belongs to neither terminal. Quarantine the incompatible observation; retain original evidence and valid pins 1/2. |
| [native-37735b083f0b9f56549f](../evidence/precision-20261023/native-37735b083f0b9f56549f.png) | P0.00 -- P0.31 | NONEXISTENT PHYSICAL PIN OR COMPONENT / NONEXISTENT PHYSICAL PIN OR COMPONENT | P0.00/XL1 and P0.31/AIN7 are U1 GPIO function names, not physical connector references. The boundary candidate was rejected after another design regressed; accepted parser unchanged. |
| [native-c4d7791b4ebdf13c3944](../evidence/precision-20261023/native-c4d7791b4ebdf13c3944.png) | U504.4 -- U504.9 | NONEXISTENT PHYSICAL PIN OR COMPONENT / NONEXISTENT PHYSICAL PIN OR COMPONENT | The source is U6 (ATECC608A-MAHDA), not U504. Pins 4/9 are visibly connected with a dot; the error is component identity from fused internal text. Do not cut this junction. |

The baseline U2.3--U2.9 pair is electrically correct (both VBUS) despite its wrong GND name. A guessed ground split could destroy that correct pair. Raw traced roots are unresolved on these terminals and cannot certify a safe repair. No global junction or rail-splitting threshold was changed.

## All 18 clear-sample errors

These are 11 missing physical-anchor observations and 7 incorrect assignments, not 18 missing pins. Human inspection can read the printed labels; current automatic evidence is insufficient for a general safe repair. These findings are retained as explicit limitations, with no reference-specific substitutions.

| Sample / pin | Before | Expected | Source evidence and remaining cause |
|---|---|---|---|
| [S1.U64.4](../evidence/precision-20261023/source-audit/S1-U64.png) | WZPLJ6 | DD6 | Literal DD6 and pin 4 are visible; wrong strip OCR merged the pin/name text. |
| [S1.U64.13](../evidence/precision-20261023/source-audit/S1-U64.png) | missing | CC7 | CC7 and pin 13 visible; physical terminal was not recovered. |
| [S3.U6.14](../evidence/precision-20261023/source-audit/S3-U6.png) | KAAI | AAA1 | AAA1 and pin 14 visible on a bus entry; wrong strip OCR. |
| [S3.U6.11](../evidence/precision-20261023/source-audit/S3-U6.png) | missing | AAA4 | AAA4 and pin 11 visible; missing terminal at the rightmost bus entry. |
| [S3.U8.14](../evidence/precision-20261023/source-audit/S3-U8.png) | AAA6 | AAA9 | AAA9 and pin 14 visible; neighboring AAA6 was associated instead. |
| [S3.U8.11](../evidence/precision-20261023/source-audit/S3-U8.png) | missing | AAA12 | AAA12 and pin 11 visible; missing terminal beside crossing bus strokes. |
| [S3.U27.17](../evidence/precision-20261023/source-audit/S3-U27.png) | missing | AR12 | AR12 and pin 17 visible; label and number fused into one text region. |
| [S3.U27.7](../evidence/precision-20261023/source-audit/S3-U27.png) | RG9 | AR3 | AR3 and pin 7 visible on left; distant right-side RG9 assigned instead. |
| [S3.U28.19](../evidence/precision-20261023/source-audit/S3-U28.png) | missing | AR10 | AR10 and pin 19 visible; fused label/number not separated. |
| [S4.U31.27](../evidence/precision-20261023/source-audit/S4-U31.png) | missing | ADDA11 | ADDA11 and pin 27 visible; crowded vertical pin-label strip. |
| [S4.U33.14](../evidence/precision-20261023/source-audit/S4-U33.png) | missing | ADDA9 | ADDA9 and pin 14 visible; missing strip observation at top edge. |
| [S4.U34.9](../evidence/precision-20261023/source-audit/S4-U34.png) | missing | ADDA7 | ADDA7 and pin 9 visible; missing strip observation at top edge. |
| [S5.U36.21](../evidence/precision-20261023/source-audit/S5-U36.png) | missing | INDA14 | INDA14 and pin 21 visible; missing left terminal observation. |
| [S5.U36.2](../evidence/precision-20261023/source-audit/S5-U36.png) | N00549 | INDA12 | INDA12 and pin 2 visible; anchor exists but external label was not associated. |
| [S5.U49.2](../evidence/precision-20261023/source-audit/S5-U49.png) | ~TT2 | INDA8 | INDA8 and pin 2 visible; OCR label corrupted into ~TT2. |
| [S5.U49.9](../evidence/precision-20261023/source-audit/S5-U49.png) | N00619 | INBU8 | INBU8 and pin 9 visible; anchor exists, local trace unresolved and net anonymous. |
| [S5.U37.9](../evidence/precision-20261023/source-audit/S5-U37.png) | missing | INBU4 | INBU4 and pin 9 visible; missing right terminal observation. |
| [S5.U50.9](../evidence/precision-20261023/source-audit/S5-U50.png) | missing | INBU0 | INBU0 and pin 9 visible; missing right terminal observation. |

## Eleven XML blocks: all 37 component records

Every blocked graph has zero observed physical pins for at least one component. Independent parse/readback shows no missing or extra observed assignments. The serializer preserves explicit unassigned pins; it cannot invent a faculty node for a component with no physical IDs. No exporter defect was found.

Unprinted terminal numbers are a real source-information limit. Visible symbols and wires with absent recognized anchors are recognition defects, not ambiguous electrical geometry. Incorrect references from prose or fused glyphs require component review.

| Case | Zero-pin components | Source assessment |
|---|---|---|
| S3 | [R1](../evidence/precision-20261023/source-audit/xml-S3-R1-0.png), [R6](../evidence/precision-20261023/source-audit/xml-S3-R6-0.png) | R1 is an OCR alias of printed R11; R6 is a visible resistor with unprinted physical numbers. |
| S4 | [R11](../evidence/precision-20261023/source-audit/xml-S4-R11-0.png), [R13](../evidence/precision-20261023/source-audit/xml-S4-R13-0.png), [R20](../evidence/precision-20261023/source-audit/xml-S4-R20-0.png) | All three resistor bodies/conductors visible; physical numbers unprinted. Missing observations. |
| S5 | [R12](../evidence/precision-20261023/source-audit/xml-S5-R12-0.png), [R19](../evidence/precision-20261023/source-audit/xml-S5-R19-0.png) | Both resistor bodies visible; physical numbers unprinted. Missing observations. |
| S4-scan300 | [R1](../evidence/precision-20261023/source-audit/xml-S4-scan300-R1-0.png), [R11](../evidence/precision-20261023/source-audit/xml-S4-scan300-R11-0.png), [R14](../evidence/precision-20261023/source-audit/xml-S4-scan300-R14-0.png), [R15](../evidence/precision-20261023/source-audit/xml-S4-scan300-R15-0.png) | R1 aliases printed R13; R11/R14/R15 visible with degraded ink. Physical numbers unprinted. |
| S4-scan200 | [R11](../evidence/precision-20261023/source-audit/xml-S4-scan200-R11-0.png) | R11 source is blurred but visible; physical numbers unprinted. |
| native-3b2a49a524e2d50dcf26 | [C36](../evidence/precision-20261023/source-audit/xml-native-3b2a49a524e2d50dcf26-C36-0.png), [R24](../evidence/precision-20261023/source-audit/xml-native-3b2a49a524e2d50dcf26-R24-0.png), [R32](../evidence/precision-20261023/source-audit/xml-native-3b2a49a524e2d50dcf26-R32-0.png), [R40](../evidence/precision-20261023/source-audit/xml-native-3b2a49a524e2d50dcf26-R40-0.png) | All four bodies visible. R32 explicitly prints 1/2. C36/R24/R40 omit numbering. C36 value is also misassociated as 100K instead of 10uF. |
| native-c4d88e79bc63688e0e7c | [R11](../evidence/precision-20261023/source-audit/xml-native-c4d88e79bc63688e0e7c-R11-0.png), [R15](../evidence/precision-20261023/source-audit/xml-native-c4d88e79bc63688e0e7c-R15-0.png), [R2](../evidence/precision-20261023/source-audit/xml-native-c4d88e79bc63688e0e7c-R2-0.png), [U4](../evidence/precision-20261023/source-audit/xml-native-c4d88e79bc63688e0e7c-U4-0.png), [U58](../evidence/precision-20261023/source-audit/xml-native-c4d88e79bc63688e0e7c-U58-0.png) | R11/R15/R2 visible without pin numbers. U4 text comes from a prose note, not its body. U58 is USB text misread as a component. |
| native-e9b7597c67252bf7707d | [R1](../evidence/precision-20261023/source-audit/xml-native-e9b7597c67252bf7707d-R1-0.png), [R2](../evidence/precision-20261023/source-audit/xml-native-e9b7597c67252bf7707d-R2-0.png), [R8](../evidence/precision-20261023/source-audit/xml-native-e9b7597c67252bf7707d-R8-0.png), [R9](../evidence/precision-20261023/source-audit/xml-native-e9b7597c67252bf7707d-R9-0.png) | Four resistor symbols visible; pin numbering unprinted. Missing observations. |
| native-901de51001a98cc2361a | [R3](../evidence/precision-20261023/source-audit/xml-native-901de51001a98cc2361a-R3-0.png) | R3 body and wires visible, numbering unprinted. |
| native-c6bcc506a3200b19e089 | [R1](../evidence/precision-20261023/source-audit/xml-native-c6bcc506a3200b19e089-R1-0.png), [R2](../evidence/precision-20261023/source-audit/xml-native-c6bcc506a3200b19e089-R2-0.png), [R4](../evidence/precision-20261023/source-audit/xml-native-c6bcc506a3200b19e089-R4-0.png), [R5](../evidence/precision-20261023/source-audit/xml-native-c6bcc506a3200b19e089-R5-0.png), [R7](../evidence/precision-20261023/source-audit/xml-native-c6bcc506a3200b19e089-R7-0.png), [R8](../evidence/precision-20261023/source-audit/xml-native-c6bcc506a3200b19e089-R8-0.png) | Six resistor bodies visible without numbers. References also appear in a component list; duplicate text anchors need disambiguation. |
| native-c4d7791b4ebdf13c3944 | [R5](../evidence/precision-20261023/source-audit/xml-native-c4d7791b4ebdf13c3944-R5-0.png), [R6](../evidence/precision-20261023/source-audit/xml-native-c4d7791b4ebdf13c3944-R6-0.png), [R8](../evidence/precision-20261023/source-audit/xml-native-c4d7791b4ebdf13c3944-R8-0.png), [R9](../evidence/precision-20261023/source-audit/xml-native-c4d7791b4ebdf13c3944-R9-0.png), [U4](../evidence/precision-20261023/source-audit/xml-native-c4d7791b4ebdf13c3944-U4-0.png) | Four resistor bodies visible without numbers. U4 body has explicitly printed 1..5 and clear wires; missing terminal extraction. |

No connections were added for these blockers. Manually transcribe visible physical IDs or explicitly choose the library numbering convention, then use the saved review and independent XML graph check. The native CM4 U4 overview is [here](../evidence/precision-20261023/source-audit/cm4-U4-wide.png).

Machine-readable observations and inverse-mapped crop bounds: [audit.json](../evidence/precision-20261023/source-audit/audit.json). Reproduce with `backend/.venv/Scripts/python.exe tools/eval/precision_audit.py --phase evidence/tonight-20261023/final-fresh --out evidence/precision-20261023/source-audit`.

## Changed observations outside partial ground truth - rejected candidate only

The rejected candidate fresh S3 output had three fewer assigned connector observations. Independent source inspection confirms all three former IDs were wrong; the replacements below are human readings only and were not injected into recognition.

| Removed observation | Literal source | Evidence |
|---|---|---|
| P1.6 | P1-B5, beside BMAG | [source crop](../evidence/precision-20261023/source-audit/S3-removed-P1-6.png) |
| P2.2 | P2-B22, beside GRFDM11 | [source crop](../evidence/precision-20261023/source-audit/S3-removed-P2-2.png) |
| P2.B3 | P2-B30, beside GRFDM3 | [source crop](../evidence/precision-20261023/source-audit/S3-removed-P2-B3.png) |

The rejected connector boundary abstained on fused OCR words; this change is not present in the accepted application. These three changes are outside the 245 annotated clear assignments and are reported separately from that score. Full fresh graph differences are retained in `accepted-fresh/precision-changes.json`.

## Rejected connector experiment - restored accepted parser

The complete-boundary parser candidate is NOT shipped. Although it removed the nRF false pair and the three incorrect S3 readings above, fresh evaluation on native-c4d88e79bc63688e0e7c introduced a new nonexistent component P3 and invalid pin P3.2. Rejecting a fused token allowed the regex to backtrack from reference P32 to P3. This violates the no-new-errors gate. The candidate was stopped and digital_vision.py restored byte-for-byte to the accepted parser. Its experimental test is archived in backend/.state, outside the test suite. No second parser experiment was attempted.

Consequently the nRF P0.00--P0.31 pair remains an automatic error, and the three S3 removals above are experimental findings only. The accepted application change is the corroborated two-terminal passive guard. Candidate evidence is in evidence/precision-20261023/connector-candidate-rejected.json. The S1 completed worker and candidate GPU results are retained for audit but are not represented as fresh acceptance of the restored parser.

## Final accepted status

Application commit b0d6c9b accepts only the corroborated passive guard. Native false pairs: 14 to 13; all 103 valid pins, all 9 correct pairs, and all previously correct source labels retained. Clear assignments remain 227/245. All 18 corpus graph exports were checked through both native CAD readbacks (2,206 assignments each). The accepted cohort combines 16 unchanged cached graphs with two current fresh target workers; candidate fresh results are not relabeled as current acceptance.
