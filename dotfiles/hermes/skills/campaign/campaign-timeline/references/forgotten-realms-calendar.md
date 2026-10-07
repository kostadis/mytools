# Forgotten Realms Calendar (for date parsing/inference)

Source of truth for converting the campaign's `DD-MM-Month YYYY` date stamps and
for month-length arithmetic when inferring undated chapters.

## Date stamp format used in this campaign

`DD-MM-Tarsakh 1495`

- `DD` = day of month (01–30)
- `MM` = **MONTH** (middle field is the month, NOT the day)
- `Month YYYY` = month name + DR year

Example: `09-03-Tarsakh 1495` = "9th day of the month Tarsakh, year 1495 DR."
Do NOT read it as March 9th. The convention was confirmed by scanning all chapter
files before any dates were assigned.

## Month lengths

The Calendar of Harptos has 12 months, each exactly **30 days** (plus 5 festival
days that don't belong to any month, typically ignored for this campaign's
linear counting). So:

- `30-03` rolls over to `01-04`
- `29-03 + 5 days = 04-04`
- `30-12` is the last day of the year

Always assume 30-day months for accumulation unless the source states otherwise.

## The twelve months (in order)

| # | Name | Common note |
|---|------|-------------|
| 1 | Hammer | "Deepwinter" |
| 2 | Alturiak | "The Claws of Winter" |
| 3 | Ches | "The Claw of Sunsets" |
| 4 | Tarsakh | "The Claw of the Sunsets" end; spring |
| 5 | Mirtul | "The Melting" |
| 6 | Kythorn | "The Bloom" |
| 7 | Flamerule | "Summertide" |
| 8 | Eleasis | "Highsun" |
| 9 | Eleint | "The Fading" |
| 10 | Marpenoth | "Leafall" |
| 11 | Uktar | "The Rotting" |
| 12 | Nightal | "The Drawing Down" |

Note: in this campaign's data the year string is literally written `Tarsakh 1495`
as a fixed label — the actual Harptos year boundary (which would start at Hammer,
not Tarsakh) is NOT modeled. Treat the `MM` field as a 1-based month index into
the table above purely for display/parsing; do not remap to real Harptos epochs
unless the user explicitly asks.

## Festival days (usually ignored for linear counting)

Midwinter (between Hammer/Alturiak), Spring Equinox (Ches/Tarsakh), Summer
Solstice (Flamerule), Highharvestide (Eleint/Marpenoth), Feast of the Moon
(Uktar/Nightal). These are 1-day gaps outside the 30-day months; this campaign's
inference treats every month as a flat 30 days and does not insert them.
