# FAS PDF ප්‍රතිඵල CSV බවට පරිවර්තනය කිරීම

`docs/L2S2-Results-Ac.-2023-2024.pdf` හි scan පිටු 16ම පරීක්ෂා කළා. අවසාන Wide CSV එකේ **මුද්‍රිත student rows 265ම**, **unique index අංක 265ක්** සහ **subject module columns 11ක්** තිබෙනවා. Long CSV එකේ **grade records 1,588ක්** තිබෙනවා. PDF එක සහ student data මේ පරිවර්තනයේදී Google වෙත යැව්වේ නැහැ.

| PDF පිටු | Exam section | Student rows | Grade cells |
| --- | --- | ---: | ---: |
| 1–4 | Regular · Combination I | 59 | 531 |
| 5–11 | Regular · Combination III | 123 | 861 |
| 12–16 | Repeat examination | 83 | 196 |
| **එකතුව** | | **265** | **1,588** |

Repeat examination rows 83 අතර Repeat ලෙස වර්ග කළ records 76ක් සහ Medical records 7ක් තිබෙනවා. Medical records 5ක මුද්‍රිත index එකේ `R/M` හෝ `RR/M` වැනි suffix එකක් තිබෙනවා. Wide සහ Long CSV දෙකේම `Index` එකේ මුද්‍රිත අංකය සහ suffix එකත්, `Base_Index` එකේ අකුරු රහිත මූලික අංකයත් තියෙනවා. `Attempt` එකේ R ගණන අනුව attempt එක ලියනවා.

CSV තුනේම `Academic_Year`, `Level` සහ `Semester` තියෙනවා. මේ PDF එකේ අගයන් `2023/2024`, `Level 2`, `Semester II`. Default filenames `AY-2023-2024_Level-2_Semester-II_` වලින් පටන් ගන්නවා. එකම PDF නමෙන් ඊළඟ academic year එක export කළත් එයට වෙනම filename ලැබෙනවා.

## මුල් flow එකේ දත්ත හැලුණු තැන්

1. **PDF සහ OCR.** මේ PDF එකේ text layer එකක් වෙනුවට scan images තිබෙනවා. කලින් Tesseract මුළු පිටුව text පෙළක් බවට හැරවූ විට තිබූ table සීමා සහ හිස් cells ඒ text එකෙන් නැති වුණා. සමහර index numbers සහ grades වෙන වෙනම lines වලට ගියා.
2. **Text parser.** කලින් offline parser එක පිටු තුනක් එකට කියවා හමුවූ පළමු course header එකෙන් grades අනුපිළිවෙළට පැවරුවා. Combination එකක් වෙනස් වුණොත් වැරදි header එක යෙදෙන්න පුළුවන්. Token එකක් හඳුනාගත නොහැකි වුණොත් ඊළඟ grade එක කලින් module එකට යා හැකියි. හඳුනාගත් grade එකක් නැති Regular rows ද ඉවත් වුණා.
3. **Gemini සහ merge.** JSON schema එක මඟින් fields සහ types පරීක්ෂා වුණා. JSON එකේ මුල් පිටුවේ සෑම index එකක්ම තිබේද කියා කලින් බැලුවේ නැහැ. අවසානයේ clean index සහ attempt මත records ඉවත් කිරීමෙන් වෙනම මුද්‍රිත row එකක් අහිමි වෙන්නත් පුළුවන්.
4. **CSV.** CSV writer එකට ලැබුණේ parser එකෙන් ඉතිරි වූ records. කලින් offline run එකෙන් Wide rows 13ක් සහ Long grade rows 11ක් පමණක් ලියවුණා. CSV ලියවීම සාර්ථක වීමෙන් PDF extraction එක සම්පූර්ණ බව තහවුරු වුණේ නැහැ.

## දැන් code එක වැඩ කරන අනුපිළිවෙළ

1. [PDFScrapper](api/models/pdf_scrapper.py) පිටුවකට text layer එකක් තිබේ නම් layout සහිතව කියවනවා. මේ PDF එකේ පිටු 16ම 300 DPI වලින් එක බැගින් render වුණා.
2. [Table OCR](api/models/table_ocr.py) scan එකේ සුළු ඇලය සකස් කරලා horizontal සහ vertical rules හඳුනාගන්නවා. Header, serial, index සහ grades මුද්‍රිත cell එකෙන් කියවනවා. Grade එකක් මඟහැරුණත් පිටුපස grade එක වෙනත් subject column එකකට යන්නේ නැහැ.
3. [Result parser](api/models/ai_connector.py) grid එකෙන් ලැබුණු සෑම row එකක්ම source order එකෙන් තබනවා. පිටු අතර serial අනුපිළිවෙළත් OCR කියවීම් අතර වෙනස්කම්ත් page report එක හරහා පෙන්වනවා.
4. [OCR review](api/models/ocr_review.py) PDF එකේ SHA‑256 hash එක සහ පිටුවෙන් පිටුව row counts සසඳලා, PDF එකෙන් නැවත කියවා තහවුරු කළ values අදාළ cells වලට දානවා. මේ PDF එකට review entries 20ක් භාවිත කළා. ඒවායින් grade cells 15ක් සහ serial අංකයක් නිවැරදි කළ අතර, තවත් grades 4ක් තිබූ අගය සමඟ ගැළපුණා.
5. [CSV exporter](api/models/file_export.py) UTF‑8 BOM සහිත CSV තුනම ලියනවා. Wide CSV එකේ ලියාපදිංචි නොවූ modules සහ PDF එකේ dash cells හිස්ව තියෙනවා. Long CSV එකට grade තියෙන cells පමණක් ඇතුළත් වෙනවා. එක් එක් CSV එක සම්පූර්ණයෙන් ලියා අවසන් වූ පසු output path එකට atomic replace එකකින් දානවා.

## Gemini API පරීක්ෂාව

`.env` හි තිබෙන key එක සහ `gemini-3.5-flash-lite` model එක භාවිත කළා. පළමු SDK generation probe එකට HTTP 504 ලැබුණා. පසුව REST model lookup එක සහ generic JSON schema එකක් සහිත synthetic generation request එක HTTP 200 දුන්නා. Response JSON එකේ බලාපොරොත්තු වූ labels දෙකම ලැබුණා. App එකේ schema validation, සහ local OCR හඳුනාගත් index එකක් අඩු Gemini response එකක් ප්‍රතික්ෂේප කිරීම, mocked SDK test එකකින් පරීක්ෂා කළා. සැබෑ PDF එකේ results Gemini හරහා verify කළේ නැහැ. [Google Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)

Grid එක නොහඳුනාගත් text pages සඳහා configured Gemini model එක එක් පිටුවකට වෙන වෙනම උත්සාහ කරනවා. එය fail වුණොත්, හෝ local parser එක හඳුනාගත් index එකක් response එකෙන් හැලුණොත්, app එක offline fallback තෝරනවා සහ ඒ පිටුවට warning එකක් සටහන් කරනවා. Local-only run එකකට `--offline` භාවිත කරන්න.

## අවසාන export පරීක්ෂාව

- 16 පිටුවල table row counts 16, 21, 18, 4, 15, 22, 22, 22, 22, 17, 3, 15, 22, 22, 21, 3 ලෙස කියවා CSV rows සමඟ ගැළපුවා.
- Index values 265ම cell crops වලින් වෙනම single-line OCR pass එකකින් නැවත කියවූ විට එකඟ වුණා. Grade areas OCR output සමඟ glyph shapes පදනම් කරගත් වෙනම පරීක්ෂාවකින් සසඳා, වෙනස්කම් PDF crops වලින් බැලුවා.
- Reviewed CLI run එකේ page warnings හෝ `UNREAD` cells තිබුණේ නැහැ. Wide grade cells 1,588ම Long rows සමඟ record, module සහ grade මට්ටමින් ගැළපුණා. Wide CSV එකේ subject cells 1,327ක් හිස්ව තිබෙනවා. Modules CSV එකේ catalog entries 27ක් තිබෙනවා.
- FastAPI app එකට sample PDF එක සහ review JSON එක upload කළ විට HTTP 200 සහ student rows 265ක් ලැබුණා. API download තුනේම bytes CLI ගොනු සමඟ ගැළපුණා. Regression tests හතරම සාර්ථක වුණා.
- මේ පරීක්ෂාවලින් row coverage සහ output consistency තහවුරු වෙනවා. සෑම grade එකක්ම මිනිසෙකු විසින් වෙන වෙනම කියවා සහතික කර නැහැ. වෙනත් scan එකකට review අවශ්‍ය වන cells වෙනස් විය හැකියි.

## ගොනු සහ නැවත ධාවනය

- [Wide CSV](exports/AY-2023-2024_Level-2_Semester-II_L2S2-Results-Ac.-2023-2024_results_wide.csv)
- [Long CSV](exports/AY-2023-2024_Level-2_Semester-II_L2S2-Results-Ac.-2023-2024_results_long.csv)
- [Modules CSV](exports/AY-2023-2024_Level-2_Semester-II_L2S2-Results-Ac.-2023-2024_modules.csv)
- [PDF එකට අදාළ OCR review JSON](docs/L2S2-Results-Ac.-2023-2024-review.json)

```bash
uv run python main.py process docs/L2S2-Results-Ac.-2023-2024.pdf --offline
```

මේ PDF එකේ නමින් `docs/` තුළ තිබෙන review JSON එක PDF fingerprint එක ගැළපෙන විට ස්වයංක්‍රීයව යෙදෙනවා. වෙනත් review file එකක් තෝරන්න CLI එකේ `--review` භාවිත කරන්න. API එකේ `POST /api/v1/extract-results` වෙත `file`, `offline=true` සහ අවශ්‍ය නම් review JSON එක `review` ලෙස multipart form එකෙන් දෙන්න. Response එකේ CSV filenames, එක් එක් පිටුවේ rows ගණන සහ warnings තිබෙනවා. එක් එක් CSV එක `GET /api/v1/download/{filename}` හරහා ගන්න පුළුවන්.
