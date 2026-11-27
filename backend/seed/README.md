# Seed data

`block123.json` holds the fictional demo blocks. **Everyone in it is made up.**
Edit it freely, then press **Reset** on the control panel (or run `python -m seed.seed`) to reload.

## Block fields

| Field | Meaning |
| --- | --- |
| `floors`, `units_per_floor` | Size of the block. Units are labelled `#FF-UU`, e.g. `#09-12` |
| `stairwells` | Which unit numbers each stairwell serves |
| `vacant` | Units with nobody living there (the fake report targets `#14-03`) |

## Resident fields

| Field | Meaning |
| --- | --- |
| `id` | Short id used in URLs, e.g. `/phone/aziz` |
| `language` | `en`, `zh`, `ms`, `ta`, `hokkien` |
| `has_smartphone` | Seniors without one get calls / neighbour visits instead |
| `is_essential_worker`, `essential_role` | For the family-cover loop |
| `dependent_unit` | The family member a neighbour checks on, so the worker can go to duty |
| `silence_opt_in` | Opted in to Silence Alert daily check-ins |
| `vulnerable` | Needs in a crisis. **Moves into an encrypted Sealed Profile in Week 3** |

## Helper fields

| Field | Meaning |
| --- | --- |
| `skills` | `cpr`, `first_aid` |
| `home_hours` | When they're usually home, e.g. `"18:00-08:00"` (can wrap past midnight) |
| `sgsecure_responder` | Already registered with SGSecure |

## The demo cast (Block 123)

- **Mdm Tan, #09-12**: lives alone, oxygen machine, Hokkien. The story of the pitch.
- **Mr Rajan, #13-07**: wheelchair user. The one "not reached" in the handover brief.
- **Aziz, #07-10**: CPR-trained, SGSecure responder. Mdm Tan's helper.
- **Priya, #06-03**: nurse; her father **Mr Krishnan** lives at **#11-04** (family cover).
- **Daniel, #03-05**: utility engineer (essential worker).
- **Mr Lim, #05-08**: opted in to Silence Alert.
- **#14-03 is vacant**, so the fake report can be caught.
- **The night gap:** Ryan (#12-09) is the only first-aider on floors 10–14 and he's away 23:00–08:00.
