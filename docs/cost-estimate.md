# Cost estimate

The method, not a bill. No prices are stored here; put current rates from the
Microsoft pricing pages into the inputs.

## What drives the cost

Two things: the capacity that hosts the model, and the licences of the people
who view it. On Fabric F SKUs below F64 (and on Premium Per User), every
viewer needs a Pro or PPU licence; from F64 up, viewers with a free licence can
consume content shared to them. That threshold usually decides the SKU more
than the model does.

## Inputs

| Item | Symbol | Source |
|---|---|---|
| Viewers (cost center owners, controllers, finance) | `V` | HR or the security grants |
| Authors (build reports on the model) | `A` | Usually small |
| F SKU monthly rate, reserved | `R_F` | Pricing page, by SKU and region |
| F64 monthly rate, reserved | `R_F64` | Pricing page |
| Pro licence per user per month | `L_pro` | Pricing page |
| Model memory needed | from `semlayer.model_size` and a refresh in tst | The SKU's per-model memory limit must hold the model plus a refresh copy |

## Formula

```
below F64:  capacity R_F   + (V + A) x L_pro
F64:        capacity R_F64 +       A x L_pro
break-even: V x L_pro = R_F64 - R_F
```

So F64 pays for itself once `V > (R_F64 - R_F) / L_pro`. With a few dozen
finance viewers, a small F SKU plus Pro licences is usually cheaper; with a
few hundred, F64 is.

## Model size input

`python -m semlayer.model_size --data data` at full generator scale estimates
29.9M bytes for the imported columns (the formula is in the module; it ignores
run-length encoding, so it ranks columns rather than predicting the size the
service reports). Import refresh needs room for a second copy of the
partitions being refreshed. Measure the real size in tst after a refresh
before choosing the SKU.

## Cost controls in the design

- GL imported at summary grain: 3.19x fewer rows than line grain.
- Incremental refresh: each night reloads 3 months, not 3 years.
- One shared model instead of one per report: one copy of the data in memory.
