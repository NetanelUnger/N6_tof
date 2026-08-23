# מערכת לימוד אבן–נייר–מספריים מחיישן ToF על STM32N6

מסמך זה מתאר את השרשרת המלאה, מהמרחקים שה־VL53L9CX מודד ועד מודל integer
שמיועד ל־Neural‑ART NPU של STM32N6. המערכת בנויה כתהליך לימודי: כל שלב הוא
סקריפט Python נפרד, לכל שלב יש BAT שמסביר מראש מה הוא עושה, וכל תוצר משמעותי
מקבל metadata, hash ומצב שמאפשר להמשיך אחרי עצירה.

## התמונה הגדולה

```text
VL53L9CX (54x42 מרחקים במ"מ)
        |
        v
FW transform task --> DATASET STREAM ON --> USB CDC / CN8
        |                    N6DF v2 + CRC32 + frame_id + NPU scores
        v
Python capture --> uint16 NPZ + 16-bit depth PNG + RGB preview + JSONL
        |
        v
validate --> preprocess 64x50x1 uint8 --> split by capture burst
        |
        v
small Keras CNN --> full-integer TFLite --> STEdgeAI Neural-ART compiler
        |                                      |
        |                                      +--> network C/headers
        |                                      +--> raw weight blob
        v
PC reference/HIL <---- exact scores ---- signed FW embeds weights, copies to SRAM6
```

יש ארבע מחלקות ולא שלוש: `none`, `rock`, `paper`, `scissors`. `none` חיונית.
בלעדיה המודל מוכרח לבחור אחת משלוש המחוות גם כשהיד איננה, כשהתמונה פגומה או
כשהעצם כלל לא דומה למחווה מוכרת.

## למה לא לשמור BMP

BMP איננו קלט "קל יותר" ל־STM32Cube.AI או ל־STEdgeAI. יוצר המודל איננו לומד
מתיקיית BMP באופן ישיר; קוד האימון טוען מערכי מספרים, מבצע preprocessing ומזין
TensorFlow. בפועל יש כאן שלושה צרכים שונים:

1. מקור מדעי מדויק: `NPZ` מכיל מערך `uint16` של 54×42 ערכי מילימטר. זה מקור
   האמת הנוח והמהיר ביותר ל־Python.
2. פורמט פתוח לצפייה/ייבוא: `*.depth.png` הוא PNG grayscale של 16 bit. הוא
   lossless, קטן מ־BMP ושומר כל ערך מילימטר. `65535` מסמן pixel לא תקין.
3. תצוגה לאדם: `*.preview.png` הוא RGB מוגדל וצבוע. הוא נוח לבדיקת תמונות אבל
   אסור לאמן ממנו, מפני שהצבע וה־8 bit איבדו מידע.

כל sample נשמר בשני פורמטים מדויקים, NPZ ו־16-bit PNG, ונרשם ב־`metadata.jsonl`
עם frame ID, CRC, טווח, session, burst ו־SHA‑256. אם כתיבה הופסקה באמצע,
הרשומה אינה מתווספת עד שכל קבצי ה־sample נכתבו.

## שינויי ה־Firmware

נוספה פקודת CLI חדשה:

```text
DATASET STREAM ON
DATASET STREAM OFF
DATASET STREAM STATUS
```

לתצוגת inference חיה קיימים שני מסלולים נפרדים:

```text
MAP ON
MAP ON SCREEN
MAP ON DISPLAY
```

`MAP ON` מציג ב־CDC, מתחת למפת ה־ANSI, שורת `NPU RESULT` עם אחת מארבע
התוצאות `NOTHING`, `ROCK`, `PAPER`, `SCISSORS`, אחוז confidence, מספר ה־frame
וזמן inference. שורה נוספת מציגה את ארבעת ציוני ה־`int8` לפי סדר המחלקות.
`MAP ON SCREEN` ו־`MAP ON DISPLAY` הן פקודות זהות: הן מציגות את מפת העומק
במרכז ה־GC9A01 ואת סיכום המחלקה בטקסט קבוע מתחתיה. פקודות ה־`OFF` המקבילות
מנקות גם את המפה וגם את הטקסט.

ה־processing task מבצע inference ואז מצלם `RPS_AI_Status_t` פעם אחת בלבד.
אותו snapshot, כולל אותו frame ID, נמסר גם ל־CDC וגם ל־display task. לכן
תוצאה שמצוירת אינה יכולה להשתייך בטעות לפריים סמוך. `status` ו־`tof status`
מדווחים גם את frame ה־ToF האחרון שצויר ואת frame תוצאת ה־NPU שצוירה, וכך אפשר
לבצע HIL למסך בלי להסתמך על צפייה פיזית בפאנל.

`DATASET STREAM ON` מכבה אוטומטית את מפת ה־ANSI של `MAP ON`, אבל איננו עוצר
את החיישן ואיננו תלוי במסך SPI. task העיבוד ממיר כל pixel של מערך ה־float
הטרנספורמי ל־`uint16` מילימטר, מסמן invalid כ־`0xFFFF`, מכין record בתוך אחד
משני buffers סטטיים של CDC ושולח ללא allocation וללא המתנה ל־USB הפיזי. אם
שני buffers תפוסים, הפריים נספר כ־dropped וה־ToF ממשיך—זרם האימון לעולם אינו
אמור לעצור את acquisition task.

### N6DF v2

כל המספרים little-endian. גודל header הוא 64 bytes ואחריו 4536 bytes של
`54 * 42 * uint16`.

| Offset | Field | משמעות |
|---:|---|---|
| 0 | `N6DF` | magic לסנכרון מחדש גם אם טקסט CLI נמצא בזרם |
| 4 | version/header size | `2` ו־`64` |
| 8 | frame ID | המספר שהגיע ממנגנון ה־processing של החיישן |
| 12 | timestamp ms | `HAL_GetTick()` בזמן processing |
| 16 | width/height | `54`, `42` |
| 20 | format/flags | format 1 = `uint16 mm`; bit 0 = עומק לא מסונן |
| 24 | payload size | 4536 bytes |
| 28 | valid count | מספר pixels שאינם invalid |
| 32 | min/max | טווח valid שנמדד בפריים |
| 36 | invalid/filter | sentinel ו־filter תצוגה אינפורמטיבי |
| 40 | payload CRC32 | CRC‑32/IEEE של המרחקים |
| 44 | NPU frame ID | ה־frame המדויק שעבורו הסתיימה inference |
| 48 | four `int8` scores | לפי הסדר `none, rock, paper, scissors` |
| 52 | class/valid | class ID ו־1 רק אם תוצאת ה־NPU שייכת ל־frame הנוכחי |
| 54 | confidence | הסתברות quantized ביחידות permille |
| 56 | NPU run count | מונה inference מונוטוני שמוכיח שה־NPU ממשיך לעבוד |
| 60 | header CRC32 | CRC‑32/IEEE של bytes 0..59 |

Python מחפש magic, בודק sanity, ממתין לאורך המלא ובודק את שני ה־CRC. במקרה של
byte חסר או טקסט בין records הוא מתקדם byte אחד ומסתנכרן מחדש. HIL דורש גם
ש־frame ID יתקדם; CRC תקין לבדו לא מגלה FW שמשדר שוב ושוב record ישן.
ה־decoder עדיין קורא N6DF v1 כדי שלא לשבור captures וכלי בדיקה ישנים, אך רק
v2 מסוגל להוכיח inference ב־Neural‑ART עבור אותו frame.

ניתוק CN8, כניסה ל־firmware update או reset מכבים את הזרם. גם סגירת handle של
ה־COM במחשב מורידה DTR ומכבה מייד את `MAP` ואת `DATASET STREAM`, בעוד רכישת
ה־ToF ממשיכה ברקע. כך גם קריסה של Python אינה משאירה producer בינארי שממלא
את תור ה־CDC; הפעלה הבאה יכולה לפתוח את אותו COM ולהמשיך. הפקודה `MAP ON`
מכבה את הזרם הבינארי גם היא כדי שלא לערבב binary ו־ANSI.

## מבנה התיקייה

```text
training/
  config/                  חוזי מחלקות, preprocessing, training וכלים
  scripts/                 קובץ Python אחד לכל שלב + ספריות משותפות
  data/raw/                sessions מקוריים; לעולם אינם נדרסים
  data/prepared/           train/validation/test אחרי preprocessing
  models/                  checkpoint, Keras, TFLite וחוזה tensors
  generated/               פלט STEdgeAI ו־firmware integration staging
  reports/                 דוחות JSON/CSV ו־HIL
  state/                   manifests שמאפשרים resume/idempotence
  00_SETUP.bat ...         כניסה מודרכת לכל שלב
  BUILD_MODEL_FOR_N6.bat   orchestrator משלבים 03–08
  99_STATUS_RESUME.bat     תמונת מצב read-only
  RESET_TRAINING_DATA.bat  איפוס מוגן של data ותוצרי הלמידה
```

התיקיות הגדולות/מקומיות מוחרגות מ־Git, אבל קובצי `.gitkeep`, הקוד וה־config
נשמרים. אין מחיקה אוטומטית של raw data, model או checkpoint. כשרוצים להתחיל
ניסוי נקי מריצים `RESET_TRAINING_DATA.bat` ומקלידים `DELETE`. הוא מוחק רק את
`data/raw`, `data/prepared`, `models`, `generated`, `reports`, `state` ואת
`st_ai_output`. הוא משאיר את כלי העבודה ואת המודל האחרון שכבר נמצא
ב־`AppliNonSecure/AI`, כדי שה־FW יישאר buildable ויוכל לצלם dataset חדש; שלב
08 יחליף את המודל הזה בהמשך. נכתב גם `reset_log.json` עם פירוט האיפוס.

## עבודה לפי שלבים

### 00 — סביבת Python

מריצים `00_SETUP.bat`. הקובץ דורש CPython 3.11, יוצר `.venv` מקומי ומתקין
גרסאות pinned של NumPy, Pillow, pyserial, TensorFlow וכלי דוחות. Python 3.11
נבחר בכוונה: חבילות ML ו־Windows wheels נוטות להיות זמינות ויציבות יותר מאשר
בגרסת Python חדשה מאוד.

השלב גם מחפש `stedgeai.exe`, אך אינו נכשל אם הוא עדיין אינו מותקן—הוא דרוש רק
בשלב 07. אפשר להציג מצב בכל רגע עם `99_STATUS_RESUME.bat`.

### 01 — צילום מודרך

לפני הצילום טוענים ל־SRAM את ה־FW החדש באמצעות `10_LOAD_RAM.bat`, או מתקינים
אותו באופן persistent רק בבדיקת release באמצעות `11_FLASH_RELEASE.bat`.

לאחר מכן מריצים `01_CAPTURE.bat`:

- התוכנה מאתרת בדיוק device אחד עם VID `0483`, PID `5740`. אפשר להעביר
  `--port COM12` כשמחוברים כמה devices.
- היא שולחת `MAP OFF`, לאחר מכן `DATASET STREAM ON`, ומציגה זו לצד זו את מפת
  העומק הגולמית ואת `MODEL INPUT` המדויק שהלמידה וה־NPU יקבלו. אם האצבעות אינן
  ברורות בחלון הימני — לא מצלמים את ה־burst.
- `R`, `P`, `S`, `N` בוחרים label.
- רווח מתחיל burst רציף; מזיזים את היד ימינה/שמאלה, למעלה/למטה, מסובבים מעט
  ומשנים מרחק. לאחר הלחיצה יש countdown של 1.5 שניות שבו מחזיקים את המחווה
  יציבה; רק אחריו מתחילה שמירה. כך פריים של מעבר בין תנוחות אינו מקבל label
  שגוי. רווח נוסף מסיים את ה־burst.
- ה־BAT שואל בתחילתו כמה samples לשמור בכל מחלקה. ברירת המחדל היא 96.
  כל sample שומר גם `model_inputs/*.model.png`, ולכן אפשר לבדוק בדיעבד בדיוק
  מה הוזן למודל ולא רק preview צבעוני של החיישן.
- פריימים נשמרים בקצב 3Hz כברירת מחדל. פריימים כמעט זהים מדולגים כדי לא למלא
  את הדאטה במאות העתקים של אותה תנוחה.
- כל לחיצה חדשה על רווח יוצרת `burst_id`. ברירת המחדל דורשת לפחות 8 bursts
  נפרדים לכל מחלקה (12 תמונות ב־burst כאשר היעד 96), ועדיף לפזר אותם על לפחות
  שני sessions. בין bursts משנים מרחק, מיקום וזווית ולא את משמעות ה־label.
  עבור `none` מצלמים סצנה בלי מחוות RPS — לא מאות פריימים זהים של רקע אחד.
- אם frame ID אינו מתקדם או לא הגיע record תקין במשך 2 שניות, ההקלטה נעצרת
  אוטומטית ומוצגת שגיאה. המסך אינו משמש כ־oracle.
- לכל session נכתב `capture.log` לצד `session.json`. הוא כולל פקודות stream,
  CRC/framing resync, timeouts, frame sequence, תחילת/סיום bursts וסיכום סגירה.
  במקרה תקלה שולחים את הקובץ הזה יחד עם `session.json`.
- סגירת החלון שולחת `DATASET STREAM OFF`; אם התהליך נהרג לפני שהספיק, הורדת
  DTR בצד מערכת ההפעלה מבצעת את אותה עצירה ב־FW.

ברירת המחדל היא 96 samples למחלקה. זה מספר פתיחה, לא ערובה לאיכות. 384
פריימים מאדם אחד ברצף אחד הם פחות טובים מ־384 פריימים שחולקו בין כמה אנשים,
מרחקים, bursts ו־sessions.

Resume: החלון לעולם אינו מוחק session. אפשר להריץ:

```bat
01_CAPTURE.bat --session 20260822_153000
```

הספירות נטענות מ־`metadata.jsonl` והצילום ממשיך. session חדש הוא ברירת המחדל
והוא מומלץ כשרוצים להגדיל diversity.

### 02 — יבוא PNG קיים

זהו שלב אופציונלי. מבנה מומלץ:

```text
D:\old_depth\rock\*.png
D:\old_depth\paper\*.png
D:\old_depth\scissors\*.png
D:\old_depth\none\*.png
```

`02_IMPORT_PNG.bat D:\old_depth` מזהה label מהתיקייה. SHA‑256 של קובץ המקור
מונע יבוא כפול בהרצה חוזרת. 16-bit grayscale מתקבל כמרחק מדויק. RGB נדחה.
8-bit מתקבל רק עם `--allow-8bit`, מומר בקירוב לפי near/far ומסומן
`approximate_from_uint8` כדי שלא נתבלבל בעת ניתוח איכות.

### 03 — ולידציה

`03_VALIDATE.bat` אינו משנה raw data. הוא בודק:

- שכל רשומה מפנה ל־NPZ ו־PNG קיימים;
- shape של 42×54 ו־dtype `uint16`;
- SHA‑256 מחדש מול metadata;
- invalid ratio, class/session balance;
- exact duplicates ומינימום samples מומלץ.

שגיאת integrity עוצרת. חוסר איזון או מעט samples הם warning: אפשר להחליט
לצלם עוד ואז להריץ שוב. הדוח נמצא ב־`reports/dataset_validation.json`.

### 04 — preprocessing ופיצול

`04_PREPARE.bat` מיישם חוזה יחיד שמאוחר יותר חייב להיות משוכפל bit-for-bit
ב־FW:

1. invalid וכל מה שמחוץ ל־100..1200mm הופכים לרקע 0;
2. ספי עומק נבדקים בהדרגה מ־percentile 1 ועד 100;
3. בכל סף נמצאים רכיבי 8-neighbor מחוברים. רעש קטן מ־12 pixels נדחה, ונבחר
   הרכיב התקין הקרוב ביותר לפני שמרחיבים את החיפוש לרקע הרחוק;
4. נשמרת רק רצועת עומק של 220mm סביב הרכיב הנבחר ומתבצע crop עם margin של 2;
5. ערכי הרכיב מנורמלים ביחס ל־percentile 10 *של אותו רכיב*: טווח תבליט של
   260mm ממופה ל־32..255, והרקע נשאר 0. לכן אותה יד ב־300mm וב־600mm נראית
   כמעט זהה למודל, במקום שהמרחק האבסולוטי ישלוט בהחלטה;
6. ה־crop מוגדל ב־nearest-neighbor, שומר יחס ממדים, ממורכז ב־64×50 ומתקבל
   `uint8` NHWC `[N,50,64,1]`.

Nearest-neighbor נבחר מפני שקל לממש אותו באופן זהה ב־C והוא אינו ממציא מרחק
ביניים. percentile/crop דורשים ב־FW histogram קטן ו־bounding box, ועדיין אינם
דורשים floating point או allocator. הקונפיגורציה נמצאת ב־`config/preprocessing.json`;
שינוי בה משנה hash ומכריח הכנה ואימון מחדש.

הפיצול איננו random לפי frame. כל `burst_id` נשאר כולו ב־train, validation או
test. אחרת frame 100 יכול להיות ב־train ו־frame 101 הכמעט זהה ב־test, ולקבל
accuracy מרשים אך שקרי. exact duplicates נשמרים פעם אחת בלבד. מבין החלוקות
החוקיות נבחרת החלוקה הקרובה ביותר ל־70/15/15 לפי מספר samples בכל מחלקה—not
לפי מספר bursts בלבד. שער נוסף דורש לפחות 10 samples מכל מחלקה בכל split
ולפחות 50% מדוגמאות המחלקה ב־train; burst זעיר של תמונה אחת אינו יכול להפוך
ל־validation שקרי.

### 05 — אימון

`05_TRAIN.bat` בונה `spatial_cnn_v3_compact`: ארבע שכבות Conv2D ושלוש MaxPool. במקום
`GlobalAveragePooling`, שאיבד את מיקום האצבעות ועודד את המודל לספור בעיקר את
שטח הכתם, נעשה `Flatten` ולאחריו Dense קטן. כך נשמר המבנה המרחבי של אגרוף,
כף יד ושתי אצבעות. רק נתוני train עוברים augmentation דטרמיניסטי: הזזה של עד
4 pixels, mirror אופקי ושינוי עוצמה קטן. validation ו־test נשארים מדידות אמת
בלתי משונות. הרשת עדיין פשוטה בכוונה:

- מעט parameters וזיכרון;
- ops סטנדרטיים שקל יותר לכמת ולמפות ל־NPU;
- אין post-processing מורכב;
- אפשר לאמן מהר גם על CPU.

גרסת `compact` משתמשת ב־24 channels בשכבת convolution האחרונה וב־Dense של
32 יחידות. היא שומרת את מפת המיקום אך מגבילה את blob המשקולות ל־64KiB, כדי
להשאיר ל־VL53L9 את ה־heap הנדרש. שלב 08 בודק את התקציב ומפסיק מוקדם עם
הסבר אם STEdgeAI מפיק מודל גדול מדי.

בהפעלה אינטראקטיבית `05_TRAIN.bat` מציג תפריט לפני האימון:

- `AUTO / RESUME` — ברירת המחדל המומלצת. אם המודל הסופי עדיין מתאים ל־hash של
  הנתונים וההגדרות הוא ממוחזר; אם קיים checkpoint תואם ממשיכים ממנו; ואם
  הקלט השתנה מתחילים אוטומטית מ־epoch 1.
- `FRESH TRAINING FROM EPOCH 1` — מפעיל `--force`, מתעלם מהמודל ומה־checkpoint
  הקודמים ומאתחל משקולות חדשות. האפשרות אינה מוחקת דבר מתוך `data/raw` או
  `data/prepared`.
- `SHOW PIPELINE STATUS` — מציג את מצב השלבים וחוזר לתפריט בלי לשנות קבצים.

לצורך automation אפשר עדיין לעקוף את התפריט בעזרת arguments, למשל
`05_TRAIN.bat --force`. `BUILD_MODEL_FOR_N6.bat` מפעיל את סקריפט Python ישירות
ולכן נשאר resumable ולא נתקע על תפריט אינטראקטיבי.

קובצי state נכתבים באמצעות החלפה אטומית באותה תיקייה. ב־Windows נעשה retry
קצר גם כאשר Dropbox או antivirus מחזיקים לרגע את קובץ היעד; נעילה זמנית כזו
אינה אמורה עוד להפסיק אימון בסוף epoch.

אחרי כל epoch נשמר checkpoint ומספר epoch יחד עם hash של data/config. אם
המחשב נכבה, אותה הרצה ממשיכה. אם dataset או config השתנו, checkpoint ישן אינו
נטען בטעות. Early stopping מחזיר את המשקולות הטובות לפי validation accuracy,
ולבסוף מבוצעת הערכה על test שלא שימש לבחירת weights.

אם מספר הדוגמאות אינו מאוזן—למשל 300 דוגמאות `none` שכבר צולמו מול יעד חדש
של 100 לכל מחווה—כל הדוגמאות נשמרות, אך האימון מחשב `class_weight` הפוך
לשכיחות. כך המחלקה הגדולה אינה שולטת ב־loss רק מפני שיש לה יותר קבצים.
גם early stopping משתמש ב־`val_balanced_accuracy`: לכל מחלקה משקל כולל זהה
ב־validation. דוח ה־test כולל overall accuracy, accuracy לכל מחלקה ו־macro
accuracy. בפרופיל `learning` הנוכחי השער הוא 50% macro כדי לאפשר את המשך
שרשרת הלימוד; לפני release אמיתי יש להחזיר לפחות 80% כדי שמחווה חלשה לא
תוסתר על ידי `none`.

### 06 — Quantization

ה־NPU אינו מקבל קובץ Keras float כמו שהוא. `06_QUANTIZE.bat` משתמש ב־TFLite
converter וב־representative dataset אמיתי כדי לקבוע scale ו־zero-point לכל
tensor. הוא דורש conversion מלא ל־integer: input `uint8`, output `int8`; אם op
נשאר float, השלב נכשל.

לאחר מכן כל test set רץ שוב דרך TFLite Interpreter. בודקים את ירידת הדיוק ולא
רק שהקובץ נוצר. `models/model_contract.json` מקפיא:

- SHA‑256 וגודל המודל;
- input/output shape ו־dtype;
- quantization scale/zero point;
- סדר המחלקות;
- preprocessing.

זהו ה־ABI בין Python, הקוד המיוצר על ידי ST וה־FW.

שני quality gates מוגדרים ב־`config/training.json`: ברירת המחדל דורשת לפחות
80% accuracy של מודל ה־float על test, ואינה מתירה ל־quantization להוריד יותר
מ־5 נקודות אחוז. הכשל שומר את הדוחות לצורך למידה, אבל עוצר את ה־orchestrator
לפני יצירת גרסת NPU חלשה.

### 07 — STEdgeAI / Neural‑ART

מתקינים את כלי ST המתאים ומגדירים לדוגמה:

```bat
set STEDGEAI_PATH=C:\path\to\stedgeai.exe
07_GENERATE_N6.bat
```

ב־Windows הסקריפט מזהה אוטומטית גם את מבנה ההתקנה הרגיל
`C:\ST\STEdgeAI\<version>\Utilities\windows\stedgeai.exe`. המשתנה
`STEDGEAI_PATH` נדרש רק להתקנה במיקום אחר או לבחירה מפורשת של גרסה.

הסקריפט מריץ עקרונית:

```text
stedgeai generate -m rps_int8.tflite --target stm32n6 --st-neural-art \
  -n rps_tof -o generated/st_ai_output
```

סוגי ה־I/O נלקחים מה־TFLite הכמותי עצמו; אין להעביר כאן
`--input-data-type uint8`, משום שב־STEdgeAI 4.0 הדגל מיועד להמרת טיפוס ועלול
להידחות עבור מודל שקלטו כבר `uint8`. שלב 06 מקפיא ומאמת את הטיפוסים בחוזה.

הוא דורש `<network>.c/.h`, `stai_<network>.c/.h` ולפחות
`<network>_atonbuf.*.raw`, ומוודא שהקוד מכיל LL_ATON/Neural‑ART. קובצי
`ecblobs` נאספים אם הקומפיילר יצר אותם, אך אינם חובה כאשר ה־Epoch Controller
לא בשימוש. כך כשל התקנה
או mapping ל־M55 אינו מסומן כהצלחת NPU.

מקורות רשמיים שימושיים:

- [ST deployment guide for STM32N6](https://github.com/STMicroelectronics/stm32ai-modelzoo-services/blob/main/image_classification/docs/README_DEPLOYMENT_STM32N6.md)
- [STEdgeAI command-line interface](https://stm32ai-cs.st.com/assets/embedded-docs/command_line_interface.html)
- [Neural-ART getting started](https://stm32ai-cs.st.com/assets/embedded-docs/stneuralart_getting_started.html)

## 08 — שילוב NPU ו־atomic A/B deployment

כאן יש הבדל חשוב בין "בנינו מודל" לבין "התקנו מודל על הלוח".

פלט Neural‑ART הרגיל מפוצל:

```text
Non-Secure application image: network code + descriptors
separate raw blob(s):          constants/weights at memory-pool addresses
```

במודל הנוכחי blob המשקולות הוא 49,809 bytes. במקום להוסיף partition ופורמט
`.n6fw` חדשים, `08_INTEGRATE_MODEL.bat` ממיר אותו למערך `const uint8_t` בתוך
ה־Non‑Secure image החתום. בזמן `RPS_AI_Init()` ה־FW מעתיק את המערך ל־SRAM6
בכתובת `0x24350000`. שלב 08 מעדכן גם את הכתובות וגם את תכונת ה־DMA
ל־`cacheable=0`; השארת מאפיין ה־xSPI המקורי גורמת ל־BUSIF fault בהרצת ה־NPU.

```text
external Flash Slot A/B
  one signed Non-Secure image
    application + STAI/LL_ATON + generated network + exact const weights
                              |
                              +-- boot memcpy --> NPU SRAM6 @ 0x24350000
```

לכן `.n6fw` v1 הקיים כבר מספיק: hash/signature, inactive slot, trial ו־rollback
חלים על קוד הרשת ועל המשקולות יחד. אי אפשר לקבל קוד חדש עם weights ישנים.

ה־generated activations של המודל הנוכחי נמצאים ב־SRAM5 ב־`0x242E0000`.
ה־FW שומר את החלק העליון של SRAM3 (`0x24244000..0x2426FFFF`) ל־CDC ול־scratch
של preprocessing, כדי להשאיר לפחות 360KiB heap ל־VL53L9. שלב 08 מסרב לשלב
מודל עתידי שבחר SRAM3, ומסרב ל־weight blob גדול מ־SRAM6; אין overlap שקט.

שלב 08 גם מתקין snapshot תואם של headers, sources וספריית runtime מתוך אותה
גרסת STEdgeAI שיצרה את הרשת. הוא אינו מבצע fallback ל־M55.

### 08B — bootstrap חד־פעמי של Secure

הפעלת שעוני NPU/CACHEAXI, פתיחת SRAM3–6 והעברת NPU interrupts ל־Non‑Secure
שייכות ל־TrustZone Secure. `.n6fw` מעדכן בכוונה רק את האפליקציה, ולכן מריצים
פעם אחת לכל לוח את `08B_BOOTSTRAP_NPU_SWD.bat`. הוא בונה וחותם הכול, ואז—רק
אחרי הקלדת `BOOTCHAIN`—צורב דרך SWD רק FSBL + Secure. שני app slots ו־A/B
metadata נשמרים. `--build-only` בודק את כל התוצרים בלי לשנות חומרה.

## HIL

`09_HIL.bat` קורא ברירת מחדל של 100 frames אמיתיים ובודק:

- לפני טעינת TensorFlow או איסוף frames הוא שולח `RPS ON` ו־`RPS STATUS`.
  image ישן, פקודה חסרה או `ready=0` נעצרים מיד עם הסבר ולא אחרי 100 frames;
- שני CRC לכל frame;
- frame IDs מתקדמים ללא חזרה/קפיצה בלתי סבירה;
- timeout אם התהליך נתקע;
- קצב observed ומספר payload CRC ייחודיים;
- אם TFLite קיים: prediction live על המחשב עם אותו preprocessing.
- לפחות 80% מה־frames מכילים תוצאת NPU של אותו frame;
- מונה ה־NPU עולה בכל תוצאה ואינו נתקע;
- לפחות 95% התאמה בין class של TFLite ושל Neural‑ART;
- הפרש מרבי שמוגדר ב־`config/training.json`. בפרופיל הלימודי הוא 16 יחידות
  raw `int8`, כלומר 0.0625 לפי output scale של 1/256.

ה־preflight והתוצאה נשמרים גם ב־`reports/hil_validation.log`; הדוח המובנה
נשמר ב־`reports/hil_validation.json`. הודעות INFO של TensorFlow מוסתרות כדי
שהפלט ב־BAT יציג את מצב הלוח וה־NPU בלבד.

זה בודק את החיישן, processing task, framing, CDC וה־decoder בלי להסתמך על מסך
SPI. ההשוואה היא על אותו frame ID ועל raw output quantized, לא רק על label
סופי; לכן counter ישן או תוצאה ממוחזרת אינם יכולים לעבור את השער.

פערים ב־frame IDs מדווחים כ־CDC backpressure ואינם מוסתרים. הם אינם כשל לבדם:
ברירת המחדל שומרת 3 samples/sec ולכן ה־gate דורש לפחות 3 records תקינים לשנייה,
אפס שגיאות CRC, IDs שאינם חוזרים ולפחות 80% payloads שונים. כך sensor של 10Hz
יכול לדלג על frames ב־transport ועדיין לספק קצב צילום תקין ומדיד.

## שני מסלולי FW

`10_LOAD_RAM.bat` הוא מסלול הפיתוח המהיר: incremental build ל־Secure
ול־Non‑Secure (target שלא השתנה הוא no-op) וטעינת שניהם דרך SWD ל־SRAM. כך גם
SAU/RISAF ו־bootstrap ה־NPU נבדקים בלי Flash. אין חתימה, write ל־Flash או שינוי
version; reset מוחק את ההרצה.

`11_FLASH_RELEASE.bat` הוא מסלול בדיקת מערכת סופית: version נוכחי + 1, build
incremental, חתימת Non‑Secure, `.n6fw`, שליחת XMODEM דרך CN8, reset ואימות
אחרי חלון trial. המשקולות כבר בתוך אותו image. הוא דורש 08B שהושלם ו־HIL
שעבר עבור fingerprint זהה, ומבקש להקליד `FLASH` לפני השינוי. `--package-only`
בונה וחותם בלי לשנות את הלוח ובלי להשאיר version חדש ב־header.

## Resume וכללי אמינות

- Raw samples הם append-only.
- כל stage שומר `state/<stage>.json` עם input fingerprint ותוצרים.
- Prepare/train/quantize/generate משתמשים ב־hash; תוצר תואם ממוחזר.
- checkpoint נטען רק כשה־config/data hash זהה.
- rerun של import מדלג על source SHA שכבר קיים.
- שינוי config גורר rebuild מהשלב הרלוונטי, לא שימוש שקט במודל ישן.
- `99_STATUS_RESUME.bat` הוא read-only ומציג counts, stages ומודלים.
- `BUILD_MODEL_FOR_N6.bat` מריץ 03–08 ועוצר רק על prerequisite או quality gate
  אמיתי; 08 משלים את יחידת ה־A/B האטומית.

## סדר עבודה מומלץ ראשון

1. `00_SETUP.bat`.
2. `10_LOAD_RAM.bat` כדי להריץ FW עם `DATASET STREAM` בלי flash.
3. לפחות 2 sessions של `01_CAPTURE.bat`, ובסך הכול 8 bursts לכל מחלקה.
4. `03_VALIDATE.bat`; לצלם עוד אם class/session diversity חלשים.
5. `BUILD_MODEL_FOR_N6.bat`.
6. `10_LOAD_RAM.bat` שוב כדי להריץ את המודל המשולב ב־SRAM.
7. `09_HIL.bat` ולהמשיך רק אם PC ו־NPU עברו את השער.
8. `08B_BOOTSTRAP_NPU_SWD.bat` פעם אחת ללוח; להחזיר BOOT0/BOOT1 ל־1-2.
9. רק בסוף, `11_FLASH_RELEASE.bat` לגרסת flash שעולה אחרי RESET.
