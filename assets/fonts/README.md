# UI font

Drop one open-licensed font file (`.ttf` or `.otf`) in this folder. The UI uses the first one it
finds (alphabetical), and falls back to pygame's built-in font when the folder is empty.

Only fonts under an open licence that allows redistribution (SIL Open Font License,
Apache 2.0, ...) may be added. Keep the licence text next to the font file
(for example `OFL.txt`). Prefer a clean sans-serif with tabular (equal width) digits and full
Swedish glyphs (å ä ö), because the countdown is read from a distance.
