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
        |             N6DF v3: raw depth + exact NPU tensor + scores + CRCs
        v
Python capture --> NPZ עם raw uint16 + tensor מדויק מהבקר + previews + JSONL
        |
        v
validate --> bit-exact MCU/Python check --> split device tensor by capture burst
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

המסמך הזה מתמקד במסלול הלמידה ובחיבור שלו ל־Firmware. לתיאור מפורט של
החומרה, הפינים, השעונים, USB, TrustZone, A/B update והשינויים ביחס לקוד של ST
ראו גם את [`../README.md`](../README.md). שני המסמכים משלימים זה את זה:
ה־README הראשי הוא ספר הארכיטקטורה של המוצר, והמסמך הנוכחי הוא ספר המעבדה של
החיישן והמודל.

## הארכיטקטורה הפנימית

### ארבעת הקונטקסטים והאתחול

זה אינו קובץ יחיד שרץ ישירות אחרי Reset. הפרויקט מכיל ארבעה קונטקסטים;
שלושה מהם משתתפים בשרשרת האתחול הרגילה והרביעי הוא כלי צריבה:

```text
BootROM
  |
  v
FSBL ---- בוחר Slot A/B, מאמת image ומעתיק אותו מה־NOR החיצוני
  |
  v
AppliSecure ---- TrustZone, SAU/RIF/RISAF, שעוני NPU ושירות update מאובטח
  |
  v
AppliNonSecure ---- ThreadX, חיישן, USB, מסך, preprocessing ו־Neural-ART

ExtMemLoader ------ קונטקסט צריבה נפרד שבו STM32CubeProgrammer משתמש דרך SWD
```

`ExtMemLoader` אינו שלב שמורץ בכל Reset ואינו ענף מתוך `AppliNonSecure`.
זהו יישום עזר נפרד ש־STM32CubeProgrammer טוען בעת הצורך כדי לגשת ל־NOR
החיצוני בזמן צריבה.

- ה־`FSBL` מאתחל את ה־xSPI, קורא metadata כפול, בוחר image מאושר מ־Slot A או
  Slot B ומבצע rollback אם גרסת trial לא אישרה את עצמה.
- `AppliSecure` פותח ל־Non‑Secure רק את אזורי הזיכרון והפסיקות הדרושים. הוא
  גם הבעלים של כתיבת ה־Flash, בדיקת SHA‑256/ECDSA ומדיניות version עולה.
- `AppliNonSecure` הוא היישום עצמו. הוא אינו כותב ישירות ל־NOR: בזמן update
  הוא מעביר chunks דרך ממשק NSC צר אל השירות המאובטח.
- ה־weights הם חלק מאותו image חתום של `AppliNonSecure`. בזמן האתחול הם
  מועתקים ל־SRAM6, ולכן קוד ומשקולות מתעדכנים וחוזרים לאחור כיחידה אחת.

### זרימת פריים בתוך ה־Firmware

```text
PD9 interrupt
  -> ToF Acquisition task
  -> I3C1 + GPDMA אל אחד משלושה raw slots
  -> ready queue
  -> ToF Processing task
       -> VL53L9 transform: depth/amplitude/ambient/reflectance/confidence
       -> preprocessing קבוע של depth ל־64x50x1
       -> D-cache clean
       -> STAI / LL_ATON / Neural-ART
       -> snapshot יחיד של frame ID, scores ותוצאת המחלקה
       -> CDC ANSI / N6DF v3 / GC9A01
  -> החזרת ה־raw slot לתור החופשי
```

משימת ה־acquisition בעדיפות 7 מחזיקה לבדה את החיישן ואת I3C. משימת העיבוד
בעדיפות 10 מחזיקה את ה־transform והמודל. שלושת ה־raw slots מאפשרים לרכישת
הפריים הבא לחפוף לעיבוד הקודם. אם הצרכן מפגר, נזרק הפריים הישן ביותר שטרם
עובד במקום לעצור את החיישן או לצבור latency. אותו עיקרון קיים ב־USB: מספר
buffers סטטי ומוגבל, ללא allocation במסלול הרציף.

### מפת ה־RAM הנוכחית

הכתובות הבאות מגיעות מ־linker scripts ומ־map של ה־build הנוכחי. הכתובות
`0x34...` הן ה־Secure alias והכתובות `0x24...` הן ה־Non‑Secure alias של בנקי
ה־SRAM. לכן פלט ראשוני של STEdgeAI עשוי להזכיר `0x342E0000`, בעוד שלב 08
מתקין ברשת שרצה ב־Non‑Secure את `0x242E0000`.

| אזור | טווח/גודל נוכחי | מה נמצא בו ולמה |
|---|---:|---|
| Secure SRAM1 | `0x34000400..0x340FFFFF`, ‏1023KiB | קוד, data, heap ו־stack של `AppliSecure` |
| FSBL staging | `0x34180400..0x341FFFFF`, ‏511KiB | סביבת הריצה הזמנית של ה־FSBL; לאחר המעבר ליישום אין צורך לשמר אותה |
| Non‑Secure SRAM2 | `0x24100400..0x241FFFFF`, ‏1023KiB | קוד ו־rodata שהועתקו מה־Flash, BSS, שלושת ה־raw frames, עומק/workspace, שלושת ThreadX pools ו־C heap |
| NPU SRAM3, אזור CPU שמור | `0x24244000..0x2426FFFF`, ‏176KiB | `npu_shared_bss`: שני snapshots של RPS, scratch של preprocessing, stacks ו־slots סטטיים של CDC |
| NPU SRAM3, חלק תחתון | `0x24200000..0x24243FFF` | אינו מוקצה ביישום הנוכחי; שלב 08 דוחה מודל שבוחר SRAM3 כדי למנוע חפיפה עתידית |
| NPU SRAM4 | `0x24270000..0x242DFFFF`, ‏448KiB | פנוי במודל הנוכחי |
| NPU SRAM5 | החל מ־`0x242E0000`; ‏17,408 bytes בשימוש | input ו־activation arena שהקומפיילר Neural‑ART הקצה לרשת הנוכחית |
| NPU SRAM6 | החל מ־`0x24350000`; ‏55,425 bytes בשימוש | weights שמוטמעים ב־Firmware ומועתקים לכאן בזמן `RPS_AI_Init()` |

בתוך SRAM2 נמצאים שלושה pools סטטיים עוד לפני תחילת ה־C heap:

| Pool | גודל | שימוש עיקרי |
|---|---:|---|
| `tx_app_byte_pool` | 159KiB | stack של עיבוד ToF ‏96KiB, acquisition ‏16KiB, display ‏4KiB, CLI ‏6KiB ו־firmware confirmation ‏2KiB |
| `ux_device_app_byte_pool` | 56KiB | USBX arena ‏32KiB, משימת USB device ‏16KiB, bookkeeping ו־headroom |
| `usbpd_app_byte_pool` | 16KiB | משימת USB‑PD CAD בעלת stack של 8KiB ואובייקטי Type‑C |

ה־map האחרון מציב את `_end` ב־`0x2419F778` ואת תחילת MSP השמור ב־
`0x241FF800`. ההפרש הוא 393,352 bytes של קיבולת C heap. זהו תקציב חשוב:
ספריית ה־VL53L9 transform משתמשת ב־heap בזמן יצירת pipeline, ולכן build תקין
מבחינת גודל binary עדיין יכול להיכשל בזמן ריצה אם pools או BSS גדלים יותר
מדי. כלי ה־build עוצר אם נשארים פחות מ־360KiB.

האזור `npu_shared_bss` תופס כרגע 162,048 מתוך 176KiB. מתוכם כ־24.1KiB הם
RPS וכ־134.2KiB הם CDC. ה־CDC כולל שני TX slots של 48KiB, שמונה control slots
של 768 bytes, שישה־עשר RX slots של 512 bytes ושני worker stacks של 12KiB.
ההפרדה הזו משאירה את ה־C heap הגדול ל־VL53L9 ומונעת פיצול זיכרון במסלול
ה־USB הרציף. כלומר, אין הקצאות ושחרורים חוזרים שעלולים לפצל את השטח
החופשי ולגרום לכשל שמופיע רק אחרי זמן ריצה ממושך.

## למה לא לשמור BMP

BMP איננו קלט "קל יותר" ל־STM32Cube.AI או ל־STEdgeAI. יוצר המודל איננו לומד
מתיקיית BMP באופן ישיר; במסלול N6DF v3 קוד האימון טוען את מערך ה־NPU המספרי
שהבקר שלח. מימוש ה־preprocessing ב־Python משמש לבדיקה עצמאית bit-for-bit
ול־legacy מפורש בלבד, ולא כמקור התמונה במסלול המודרך. בפועל יש כאן שלושה
צרכים שונים:

1. מקור מדעי מדויק: `NPZ` מכיל מערך `uint16` של 54×42 ערכי מילימטר, ובצילום
   N6DF v3 גם את מערך ה־`uint8` המדויק שהבקר הכניס ל־NPU.
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

ל־`MAP ON` נוסף תת־תפריט לימודי של חמש תמונות שה־VL53L9CX וה־transform של
ST מפיקים מאותו פריים:

1. `DEPTH` — מרחק מכויל במילימטרים;
2. `AMPLITUDE` — עוצמת החזרת האור הפעיל של החיישן;
3. `AMBIENT` — רמת אור הסביבה;
4. `REFLECTANCE` — אומדן ההחזריות של המטרה;
5. `CONFIDENCE` — מידת הביטחון במדידת המרחק.

ברירת המחדל היא ערוץ 1. בזמן שהמפה פתוחה, לחיצה על `1` עד `5` מפעילה או
מכבה כל ערוץ בנפרד. אם הופעלו, לדוגמה, 1 ו־2, נשלחת תמונת עומק בפריים אחד
ותמונת amplitude בפריים הבא, וחוזר חלילה. כל כותרת כוללת את מספר הפריים,
מזהה הערוץ, שמו ורשימת כל הערוצים הפעילים, ולכן תוכנת מחשב יכולה לדעת מה
מוצג. לחיצה נוספת על 1 משאירה רק את 2. הפקודות הבאות מציגות ומעדכנות את
אותו מצב מתוך התפריט:

```text
MAP CHANNELS
MAP CHANNELS 1
```

רק ערוץ העומק עובר דרך `MAP PROCESSING`; שאר הערוצים מוצגים בסקאלה אוטומטית
לכל פריים. מבחינת זיכרון, ערוץ העזר משתמש מחדש בשטח העבודה של מסנני העומק
ומצויר לפני שאותו שטח ממוחזר; לא נשמרות חמש תמונות מלאות. ערוץ העומק
ממשיך להזין לבדו את מודל ה־RPS הקיים. פורמט ההקלטה `N6DF v3` עדיין לא השתנה:
הרחבה עתידית לאימון רב־ערוצי תצטרך להגדיר record חדש ששומר ערוצים מאותו
פריים באופן אטומי, ולא לנסות להסיק סנכרון מתצוגת ANSI מתחלפת.

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

### פילטרי `MAP PROCESSING`

פותחים את התפריט באמצעות `MAP PROCESSING`, בוחרים פילטר, ומשנים פרמטר בצורה
`MAP PROCESSING <FILTER> <PARAMETER> <VALUE>`. לדוגמה:

```text
MAP PROCESSING BOX radius 2
MAP PROCESSING BOX passes 2
MAP PROCESSING MEDIAN threshold_mm 150
MAP PROCESSING SHARPEN amount_percent 75
```

הפילטרים `OFF` עד `MAX` משפיעים על תצוגת העומק בלבד. הם אינם משנים את raw
depth שנשמר ב־N6DF ואינם משנים את ה־tensor הקבוע שנכנס למודל. כך אפשר ללמוד
על סינון תמונה בלי להפוך שינוי תצוגה לשינוי שקט בחוזה האימון.

| מצב | פעולה | פרמטרים | מתי הוא מועיל ומה המחיר |
|---|---|---|---|
| `OFF` | מחזיר את העומק ללא עיבוד | אין | נקודת הייחוס למדידה ולהשוואה |
| `BOX` | ממוצע פשוט של כל השכנים התקינים בחלון | `radius=1..3`, ‏`passes=1..3` | מפחית רעש אקראי במהירות, אך מטשטש קצוות ועלול לחבר עצמים קרובים |
| `MEDIAN` | ממיין שכנים תקינים ובוחר את החציון | `radius=1..2`, ‏`threshold_mm=0..1000` | מצוין להסרת pixel חריג בלי למרוח קצה. המרכז מוחלף רק אם הוא invalid או אם ההפרש מהחציון גדול מהסף; `0` פירושו החלפה תמידית בחציון |
| `GAUSSIAN` | טשטוש משוקלל separable: קודם אופקי ואז אנכי | `radius=1..2`, ‏`passes=1..3` | נותן מעבר חלק ופחות מרובע מ־BOX. שכנים קרובים מקבלים משקל גדול יותר, אך עדיין נגרם טשטוש |
| `SHARPEN` | unsharp mask: ‏`original + amount*(original-blur)` | `radius=1..3`, ‏`amount_percent=0..200` | מדגיש מעברי עומק וקצוות; ערך גבוה מדי מגביר רעש ויוצר overshoot. ‏`0%` משאיר את התמונה כמעט ללא שינוי |
| `MIN` | בוחר את המרחק התקין הקטן ביותר בשכונה | `radius=1..3` | בעומק, קטן פירושו קרוב: עצמים קרובים מתרחבים וחורים קטנים בהם נסגרים, אך הפרטים שלהם מתעבים |
| `MAX` | בוחר את המרחק התקין הגדול ביותר בשכונה | `radius=1..3` | הרקע הרחוק מתרחב ועצם קרוב מצטמצם; שימושי לניקוי בליטות קרובות קטנות, אך עלול למחוק אצבעות דקות |

כל הפילטרים מדלגים על ערכים שאינם finite או שאינם גדולים מאפס. אם אין אף
שכן תקין נשמר הערך המקורי. `BOX` מחליף בין image ו־workspace בכל pass;
`GAUSSIAN` מבצע שני מעברים חד־ממדיים; אין הקצאת heap לכל פריים.

המצבים `OBJECT 1..7` ו־`NPU` שונים: הם אינם פילטרי blur כלליים אלא חלונות
לימוד לתוך שלבי ה־preprocessing של RPS. הם מאפשרים לראות מדוע pixel מסוים
נכנס או לא נכנס למודל.

`MAP PROCESSING OBJECT 1` עד `OBJECT 7` מציגים ב־`MAP ON` את העיבוד המצטבר:

1. עומק תקין בטווח האבחון 100..1200mm;
2. מועמדי העומק שנכנסו לסף האדפטיבי;
3. הרכיב המחובר הקרוב לאחר דחיית כתמים קטנים והתרחבות לאורך משטח רציף מקומית;
4. crop עם margin, נרמול עומק יחסי ו־resize ממורכז ל־64×50;
5. אותו עיבוד עם מגבלת מודל של 600mm, margin של 4 pixels בחיישן ומסגרת נוספת
   של 4 pixels בקנבס המודל; ללא אובייקט קרוב מתקבלת תמונה שחורה;
6. צללית בינארית אגרסיבית: כל פיקסל שאינו שחור בשלב 5 הופך ל־255,
   ולאחר מכן הרחבת 3×3 אחת מתקנת חורים ופסי dropout דקים; הרקע נשאר 0.
7. צללית בינארית ניסיונית המסננת לפי העומק היחסי המנורמל של שלב 5. רק
   פיקסלים שעוצמתם גבוהה מה־`threshold` נשארים לבנים; לכן ערך גבוה יותר
   מסיר חלקים רחוקים יותר ממשטח כף היד, ובדרך כלל מסנן בהדרגה את הזרוע.

את הסף של שלב 7 אפשר לבחור ולהפעיל בפקודה אחת:

```text
MAP PROCESSING OBJECT 7 210
```

הטווח הוא `0..255` וברירת המחדל היא `210`, שנבחר לאחר בדיקה על החומרה.
ערך `0` נותן אותה צללית כמו שלב 6, ו־`255` נותן תמונה שחורה. הצורה הארוכה
`MAP PROCESSING OBJECT 7 threshold 210` שקולה לפקודה המקוצרת. הסף פועל על
עוצמה מנורמלת ולא ישירות על מילימטרים: `255` הוא המשטח הקרוב ביותר, וערכים
נמוכים יותר הם חלקים רחוקים יותר בתוך אותו אובייקט. גם שלב 7 מפעיל הרחבת
3×3 מואצת ב־Helium/MVE כדי לסגור חורי חיישן דקים.

`MAP PROCESSING NPU` מציג את מערך ה־`uint8` המדויק שנמסר ל־Neural‑ART, כלומר
כל שלבי הייצור ובפרט סינון שלב 7 עם סף קבוע `210`. נשמרים רק snapshot לימודי אחד וה־snapshot
הסופי, ולא שבעה buffers. ה־resize, הרחבת 3×3 והעתקת הפלט ל־input משתמשים
ב־Helium/MVE של
Cortex‑M55; ה־inference עצמו רץ ב־Neural‑ART. התצוגה הזו משנה את ה־CDC בלבד;
`MAP ON SCREEN` ממשיך להציג את מפת העומק 54×42. הפקודה הישנה
`MAP PROCESSING OBJECT` נשארה alias ל־`MAP PROCESSING NPU`.

הערך `210` קודם לחוזה הייצור: קלט ה־NPU בבקר ו־`preprocessing.json` של
Python משתמשים שניהם באותו סף. הפקודה של OBJECT 7 עדיין מאפשרת להציג ערכים
אחרים לצורך ניסוי, אך שינוי תצוגת OBJECT 7 אינו משנה בשקט את קלט ה־NPU.
שינוי ייצור עתידי חייב להתבצע יחד בקושחה וב־Python ולעבור שוב השוואה מלאה.

המודל הנוכחי אומן מחדש על חוזה הצללית עם threshold קבוע 210. לאחר תיקון גבול
ה־quantization הוא עבר Stage 11 HIL על חומרה: 100/100 תוצאות היו משויכות
לפריים הנכון, class agreement בין TFLite ל־Neural‑ART היה 1.0 והפרש raw מרבי
היה 4–5 יחידות בלבד מול סף 16. זה מוכיח נאמנות של המימוש; איכות סיווג בעולם
האמיתי עדיין תלויה בגיוון האנשים, המרחקים, הזוויות וה־sessions שב־dataset.

`DATASET STREAM ON` מכבה אוטומטית את מפת ה־ANSI של `MAP ON`, אבל איננו עוצר
את החיישן ואיננו תלוי במסך SPI. task העיבוד ממיר כל pixel של מערך ה־float
הטרנספורמי ל־`uint16` מילימטר, מסמן invalid כ־`0xFFFF`, מכין record בתוך אחד
משני buffers סטטיים של CDC ושולח ללא allocation וללא המתנה ל־USB הפיזי. אם
שני buffers תפוסים, הפריים נספר כ־dropped וה־ToF ממשיך—זרם האימון לעולם אינו
אמור לעצור את acquisition task. אותו record מכיל גם snapshot של 64×50 bytes
שנלקח לפני ש־Neural‑ART משתמש מחדש ב־activation arena; לכן שני ה־payloads
חולקים frame ID ואינם יכולים להגיע מפריימים סמוכים.

### N6DF v3

כל המספרים little-endian. גודל header הוא 84 bytes. אחריו 4536 bytes של
`54 * 42 * uint16`, ומיד אחריהם 3200 bytes של `64 * 50 * uint8`.

| Offset | Field | משמעות |
|---:|---|---|
| 0 | `N6DF` | magic לסנכרון מחדש גם אם טקסט CLI נמצא בזרם |
| 4 | version/header size | `3` ו־`84` |
| 8 | frame ID | המספר שהגיע ממנגנון ה־processing של החיישן |
| 12 | timestamp ms | `HAL_GetTick()` בזמן processing |
| 16 | width/height | `54`, `42` |
| 20 | format/flags | format 1 = `uint16 mm`; bit 0 raw, bit 1 model tensor קיים |
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
| 60 | model width/height | `64`, `50` |
| 64 | model format/flags | format 2 = `uint8`; exact, binary 0/255 וסטטוס MVE |
| 68 | model payload size | 3200 bytes |
| 72 | model frame ID | חייב להיות זהה ל־raw frame ID |
| 76 | model CRC32 | CRC‑32/IEEE נפרד של ה־tensor שהוזן ל־NPU |
| 80 | header CRC32 | CRC‑32/IEEE של bytes 0..79 |

Python מחפש magic, בודק sanity, ממתין לאורך המלא ובודק raw CRC, model CRC
ו־header CRC. לאחר מכן הוא מפעיל `preprocess_depth()` על ה־raw ומשווה את כל
3200 ה־bytes ל־tensor של הבקר. הבדל של pixel אחד עוצר את Capture לפני שמירה.
במקרה של
byte חסר או טקסט בין records הוא מתקדם byte אחד ומסתנכרן מחדש. HIL דורש גם
ש־frame ID יתקדם; CRC תקין לבדו לא מגלה FW שמשדר שוב ושוב record ישן.
ה־decoder עדיין קורא N6DF v1/v2 לכלים ישנים, אך Capture דורש v3. v2 יכול
להצמיד scores לפריים, אך אינו מסוגל להוכיח מה היו 3200 bytes בכניסת ה־NPU.

ניתוק CN8, כניסה ל־firmware update או reset מכבים את הזרם. גם סגירת handle של
ה־COM במחשב מורידה DTR ומכבה מייד את `MAP` ואת `DATASET STREAM`, בעוד רכישת
ה־ToF ממשיכה ברקע. כך גם קריסה של Python אינה משאירה producer בינארי שממלא
את תור ה־CDC; הפעלה הבאה יכולה לפתוח את אותו COM ולהמשיך. הפקודה `MAP ON`
מכבה את הזרם הבינארי גם היא כדי שלא לערבב binary ו־ANSI.

### VIEW_LIVE — צפייה מלאה ללא קריעת פריימים

`MAP ON` שולח פקודות צבע ANSI ו־Tera Term מצייר אותן שורה אחר שורה. זה טוב
לדיבוג CLI, אבל צילום המסך עלול לתפוס את הטרמינל באמצע מעבר בין שני frames.
`VIEW_LIVE.bat` אינו קורא ANSI: הוא משתמש בחבילות התמונה הבינאריות והממוסגרות
של `N6DF v3`, ולכן יודע היכן frame מתחיל ונגמר.

לצפייה חיה יש לסגור תחילה את Tera Term, משום שרק תוכנה אחת יכולה להחזיק את
CN8/COM בכל רגע, ואז להפעיל מתוך תיקיית `training`:

```bat
VIEW_LIVE.bat
```

ללא פרמטרים מופיע תפריט דומה לזה:

```text
Available serial ports:
  1. COM8   USB Serial Device  [CN8 - recommended]
  2. COM6   STMicroelectronics STLink Virtual COM Port
Select COM port [default 1]:
```

אפשר ללחוץ Enter לבחירה המומלצת, להקליד את המספר משמאל, או לדלג על התפריט:

```bat
VIEW_LIVE.bat --port COM8
```

ה־viewer מדפיס תמיד איזה COM נפתח ושולח אוטומטית `MAP OFF` ולאחריו
`DATASET STREAM ON`. בכל record קיימים `frame_id`, רוחב וגובה raw בשדות
16/18, רוחב וגובה model בשדות 60/62, אורכי שני ה־payloads ושלושה CRCs.
התוכנה ממתינה לחבילה שלמה ותקינה ורק אז מחליפה bitmap שלם ב־Tk; פריים חדש
אינו יכול להיכנס באמצע ציור של הפריים הקודם.

בחלון מוצגות זו לצד זו מפת העומק הגולמית ותמונת ה־`uint8` המדויקת שנמסרה
ל־NPU. מתחתיהן מופיעים המידות שהגיעו מהבקר, מספר frame, קצב התצוגה, CRC של
כל payload ו־`DEVICE/PYTHON BIT-EXACT`. אם הממשק הגרפי איטי, פריימים שלמים
ישנים נזרקים לטובת latency נמוך — אף פעם לא מוצג חצי פריים. סגירת החלון או
Escape שולחים `DATASET STREAM OFF` וסוגרים את ה־COM. הכלי אינו שומר דוגמאות
אימון ואינו משנה את המודל.

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
  review/                  החלטות ביקורת ו-cache של דירוג חשודים
  state/                   manifests שמאפשרים resume/idempotence
  00_SETUP.bat ...         כניסה מודרכת לכל שלב
  VIEW_LIVE.bat            Viewer מלא ל־raw ול־NPU עם בחירת COM
  BUILD_MODEL_FOR_N6.bat   orchestrator משלבים 03–08
  99_STATUS_RESUME.bat     תמונת מצב read-only
  RESET_TRAINING_DATA.bat  איפוס מוגן של data ותוצרי הלמידה
```

התיקיות הגדולות/מקומיות מוחרגות מ־Git, אבל קובצי `.gitkeep`, הקוד וה־config
נשמרים. אין מחיקה אוטומטית של raw data, model או checkpoint. כשרוצים להתחיל
ניסוי נקי מריצים `RESET_TRAINING_DATA.bat` ומקלידים `DELETE`. הוא מוחק רק את
`data/raw`, `data/prepared`, `models`, `generated`, `reports`, `review`, `state` ואת
`st_ai_output`. הוא משאיר את כלי העבודה ואת המודל האחרון שכבר נמצא
ב־`AppliNonSecure/AI`, כדי שה־FW יישאר buildable ויוכל לצלם dataset חדש; שלב
08 יחליף את המודל הזה בהמשך. נכתב גם `reset_log.json` עם פירוט האיפוס.

## מילון מלא של קובצי ה־BAT

כל BAT מתחיל ב־`cd /d "%~dp0"`, ולכן הנתיבים הם יחסיים לתיקיית `training`
ולא ל־`C:\Users\netan` או למיקום קבוע אחר. אפשר להעביר את כל repository
לתיקייה אחרת; הדרישה היא לשמור על מבנה התיקיות ולהתקין את כלי ST/Python
במחשב החדש. רוב הקבצים קוראים ל־`_env.bat`, שבוחר תמיד את Python מתוך
`training/.venv` ולא Python אקראי מה־PATH.

| קובץ | מה הוא עושה | מה משתנה / האם נדרש לוח |
|---|---|---|
| `_env.bat` | helper פנימי: עובר לתיקייה הנכונה, מגדיר UTF‑8, מאתר `.venv` ודורש Python 3.11 | אינו מיועד להפעלה ישירה ואינו משנה נתונים |
| `00_SETUP.bat` | יוצר `.venv`, מתקין את `requirements.txt`, בודק את הסביבה ומריץ self-tests | משנה רק סביבת Python מקומית; צריך Internet בהתקנה הראשונה, לא צריך לוח |
| `01_CAPTURE.bat` | פותח צילום מודרך, מאתר CN8, מפעיל N6DF v3 ושומר bursts עם labels | דורש לוח ו־CN8; מוסיף session ו־raw samples, לעולם אינו מוחק session קיים |
| `02_IMPORT_PNG.bat` | מסלול אופציונלי ליבוא dataset ישן מתיקיות לפי מחלקה | לא צריך לוח; מוסיף samples. ‏16-bit depth מדויק, 8-bit רק עם אישור מפורש, RGB נדחה |
| `02_REVIEW_DATASET.bat` | ממשק אנושי ל־Accept/Reject/Relabel עם עדיפות לפריימים חשודים | לא משנה raw; כותב החלטות הפיכות ב־`review/dataset_review.json` |
| `03_VALIDATE.bat` | בודק shape, dtype, hashes, PNG, כפילויות, איזון, sessions ו־bursts | לא צריך לוח; קורא raw וכותב דוח/state בלבד |
| `04_PREPARE.bat` | מאמת MCU מול Python bit-for-bit, מסיר duplicates ומחלק לפי burst ל־train/validation/test | כותב `data/prepared` ו־manifest; אינו מאמן |
| `05_TRAIN.bat` | מאמן/ממשיך מודל Keras float, שומר checkpoint בכל epoch ומחשב confusion matrix ודיוק test | לא צריך לוח; כותב `rps_float.keras` ודוחות. `--force` מתחיל weights חדשים אך אינו מוחק raw |
| `06_QUANTIZE.bat` | ממיר ל־full-integer TFLite בעזרת representative dataset ובודק מחדש את test | כותב `rps_int8.tflite` ו־`model_contract.json`; דורש input uint8 scale=1 ללא CAST ו־output int8 |
| `07_GENERATE_N6.bat` | מריץ STEdgeAI עם `--target stm32n6 --st-neural-art` | לא צריך לוח; כותב C/headers/blob תחת `generated/st_ai_output`; אין fallback שקט ל־CPU |
| `08_INTEGRATE_MODEL.bat` | מתקין את הרשת, runtime וה־weights בתוך עץ ה־Firmware ומתקן כתובות/מאפייני NPU | משנה את `AppliNonSecure/AI`; עדיין אינו צורב לוח |
| `09_BOOTSTRAP_NPU_SWD.bat` | מתקין פעם אחת FSBL+Secure שמפעילים clocks, TrustZone והרשאות NPU | דורש ST‑LINK ומצב boot מתאים; כותב Flash רק אחרי `BOOTCHAIN`, ומשמר את שני app slots. ‏`--build-only` אינו כותב חומרה |
| `10_LOAD_RAM.bat` | בונה incremental וטוען Secure+Non‑Secure+model ל־SRAM דרך SWD | דורש DEV boot ו־ST‑LINK; זמני בלבד, ללא חתימה/version/Flash ונעלם ב־RESET |
| `11_HIL.bat` | קורא את דגלי radio, מאמת גרסת NCP ו־BLE/Wi‑Fi פעילים, ואז קורא 100 פריימים ומשווה חיישן, CRC, tensor, TFLite ו־Neural‑ART לאותו frame ID | דורש להריץ 10 מיד לפניו, Bluetooth פעיל במחשב אם BLE מאופשר, ולהזיז יד בין המחוות; אינו כותב Flash, כן כותב דוח HIL |
| `12_FLASH_RELEASE.bat` | בונה, מעלה version בדיוק באחד, חותם, יוצר `.n6fw`, שולח XMODEM, מאתחל ומוודא trial confirmation | משנה Flash רק אחרי `FLASH`; דורש Stage 09 ו־HIL תואם. `--package-only` בונה חבילה בלי לגעת בלוח |
| `13_FACTORY_PROVISION.bat` | בונה וחותם את כל השרשרת, מוחק את כל ה־NOR החיצוני, כותב ומאמת FSBL+Secure+Slot A+metadata, ואז בודק version דרך CN8 | הרסני ודורש `ERASE ALL`; מיועד למעגל חדש או שחזור מפעל. `-BuildOnly` אינו נוגע בחומרה |
| `99_STATUS_RESUME.bat` | מציג counts, state, stale/current והפקודה הבאה המומלצת | read-only; לא צריך לוח ולא משנה תוצרים |
| `BUILD_MODEL_FOR_N6.bat` | orchestrator resumable של 03→04→05→06→07→08 | לא מצלם ולא צורב; ממחזר תוצר תואם ועוצר ב־quality gate אמיתי |
| `VIEW_LIVE.bat` | viewer חי של raw depth ושל ה־tensor המדויק, עם החלפת frame אטומית | דורש CN8 פנוי; אינו שומר training samples ואינו משנה מודל |
| `ANALYZE_TRAINING.bat` | יוצר ופותח דוח HTML לימודי בעברית מהנתונים והדוחות הקיימים | לא צריך לוח; read-only ביחס למודל/data, מוסיף snapshot תחת `reports/html` |
| `RESET_TRAINING_DATA.bat` | מוחק ניסוי למידה מקומי: raw/prepared/models/generated/reports/review/state | פעולה הרסנית מקומית הדורשת `DELETE`; משמרת scripts, config, `.venv` ואת המודל שכבר מוטמע ב־Firmware |

כלל עבודה פשוט: `99_STATUS_RESUME.bat` אומר מה חסר, ו־BAT ממוספר אפשר להריץ
שוב בבטחה. כל שלב שומר fingerprint של הקלט; שינוי ב־dataset, config, model או
Firmware מסמן רק את השלבים התלויים בו כ־stale. החריגים המכוונים הם פעולות
חומרה: 09 ו־12 דורשות מילת אישור, 13 דורש `ERASE ALL`, ו־RESET דורש `DELETE`.

## הכלים והספריות שבהם השתמשנו

| שכבה | כלי/ספרייה | תפקיד בפרויקט |
|---|---|---|
| תצורת MCU | STM32CubeMX וקובץ `N6.ioc` | פינים, clocks, DMA, I3C, USB, TrustZone ויצירת skeleton; לאחר Generate Code בודקים ידנית שינויים שמחוץ ל־USER CODE |
| קומפילציה | STM32CubeIDE + GNU Arm Embedded GCC | קומפילציית Cortex‑M55, linker maps, `-O3`, debug symbols ו־`-fstack-usage` |
| צריבה ודיבוג | STM32CubeProgrammer, ST‑LINK ו־ExtMemLoader | SWD, טעינה זמנית ל־SRAM, צריבת NOR חיצוני ואימות כתובות |
| חתימה ועדכון | STM32 Signing Tool, PowerShell, SHA‑256, ECDSA‑P256 ו־XMODEM‑CRC | יצירת images בפורמט ST וחבילת `.n6fw`, אימות, A/B trial/rollback והעברה דרך CN8 |
| קומפילציית AI | STEdgeAI Core 4.0 / Neural‑ART compiler | תרגום TFLite ל־C, descriptors, epochs ו־weight blob עבור STM32N6 |
| Runtime AI | STAI, LL_ATON ו־Neural‑ART | אתחול הרשת, cache maintenance, DMA/NPU epochs והחזרת output quantized |
| מערכת הפעלה | Azure RTOS ThreadX | tasks, priorities, event flags, semaphores, queues ו־byte pools |
| USB | USBX + USB‑PD/TCPP0203 | CDC ACM ב־CN8, attach/detach, CLI, N6DF ו־XMODEM |
| חיישן | X‑CUBE‑53L9A1, VL53L9CX transform ו־I3C/GPDMA | רכישת raw frame והפקת depth, amplitude, ambient, reflectance ו־confidence |
| עיבוד MCU | C, CMSIS ו־Helium/MVE | preprocessing ללא allocation, resize, העתקת tensor ו־dilation וקטורי |
| סביבת ML | Python 3.11, TensorFlow 2.20, Keras ו־TFLite | אימון float, quantization, inference reference ו־XNNPACK במחשב |
| נתונים | NumPy 2.1, Pillow 11.3, PyYAML ו־pyserial | NPZ/PNG, config, CRC/framing ותקשורת COM |
| ניתוח ותצוגה | Matplotlib, Tk ו־HTML מקומי | Capture/Review/Live Viewer, עקומות, confusion matrix וגלריית תחזיות |

CRC ו־hash ממלאים תפקידים שונים: CRC32 מגלה corruption בתוך stream חי;
SHA‑256 מזהה בדיוק dataset/model/artifact לאורך זמן; ECDSA מוכיח שחבילת
update נחתמה במפתח המורשה. בפרויקט החינוכי מפתח הפיתוח משותף בכוונה ולכן הוא
אינו root of trust מתאים למוצר מסחרי.

## דוח HTML אינטראקטיבי — ANALYZE_TRAINING

`ANALYZE_TRAINING.bat` הוא כלי לימודי ו־read-only ביחס לשרשרת המודל. אפשר
להריץ אותו בכל שלב; הוא אינו מצלם, מאמן, משנה raw/prepared data, מחליף מודל,
בונה firmware או ניגש ללוח. הוא קורא את ה־metadata, הדוחות, ה־CSV, מודלי
Keras/TFLite ודוח ה־HIL הקיימים, מריץ inference מקומי על הפריימים השמורים
כאשר המודלים זמינים, ופותח דוח HTML בעברית.

כל הפעלה יוצרת snapshot חדש תחת:

```text
reports/html/YYYYMMDD_HHMMSS__<model-hash>/
```

`reports/html/latest.html` הוא רק קיצור דרך לדוח האחרון. תיקיות ה־snapshot
הקודמות אינן נדרסות, אך הן עדיין snapshots של ה־pipeline הנוכחי ולא מערכת
model-runs מלאה ששומרת עותק עצמאי של כל model artifact.

הדוח כולל:

- `index.html` — תמונת מצב ומסלול קריאה;
- `dataset.html` — samples, sessions, bursts וחלוקת train/validation/test;
- `training.html` — עקומות accuracy/loss, confusion matrix ו־Precision/Recall/F1;
- `predictions.html` — גלריה מסוננת של raw preview, model input, label,
  תשובת TFLite, confidence וארבעת ציוני ה־int8;
- `quantization.html` — Keras מול TFLite וחוזה tensor;
- `npu_hil.html` — coverage, class agreement, raw-score delta ותחבורת N6DF;
- `files.html` — המקור, זמן העדכון ו־SHA-256 של כל דוח משמעותי.

אפשר ליצור דוח מהיר ללא טעינת TensorFlow באמצעות:

```bat
ANALYZE_TRAINING.bat --skip-inference
```

דוח מהיר עדיין מסביר את JSON/CSV הקיימים, אך גלריית הפריימים לא תקבל תחזיות
Keras/TFLite חדשות. ברירת המחדל המומלצת היא ההרצה המלאה ללא arguments.

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
אותו באופן persistent רק בבדיקת release באמצעות `12_FLASH_RELEASE.bat`.

לאחר מכן מריצים `01_CAPTURE.bat`:

- ללא arguments נפתח תפריט: session חדש, המשך session קיים מתוך רשימה עם
  ספירות, הגדרות מתקדמות, או הצגת sessions. במצב המתקדם אפשר לבחור את כל
  אפשרויות הסקריפט: `port`, `session`, `label`, יעד למחלקה, samples ל־burst
  וקצב שמירה. העברת arguments מפורשים ל־BAT ממשיכה לעקוף את התפריט.
- התוכנה מאתרת בדיוק device אחד עם VID `0483`, PID `5740`. אפשר להעביר
  `--port COM12` כשמחוברים כמה devices.
- היא שולחת `MAP OFF`, לאחר מכן `DATASET STREAM ON`, ומציגה זו לצד זו את מפת
  העומק הגולמית ואת `MODEL INPUT` שהגיע מהבקר. לפני התצוגה Python מחשב את אותו
  input עצמאית ודורש התאמה bit-for-bit; השורה
  `DEVICE/PYTHON BIT-EXACT` מאשרת זאת. אם האצבעות אינן ברורות בחלון הימני —
  לא מצלמים את ה־burst.
- `R`, `P`, `S`, `N` בוחרים label.
- רווח מתחיל burst רציף; מזיזים את היד ימינה/שמאלה, למעלה/למטה, מסובבים מעט
  ומשנים מרחק. לאחר הלחיצה יש countdown של 1.5 שניות שבו מחזיקים את המחווה
  יציבה; רק אחריו מתחילה שמירה. כך פריים של מעבר בין תנוחות אינו מקבל label
  שגוי. רווח נוסף מסיים את ה־burst.
- ה־BAT שואל בתחילתו כמה samples לשמור בכל מחלקה. ברירת המחדל היא 96.
  כל sample שומר את tensor הבקר בתוך ה־NPZ וגם
  `model_inputs/*.model.png`, ולכן אפשר לבדוק בדיעבד בדיוק מה הוזן למודל ולא
  רק preview צבעוני של החיישן.
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

### 02 — ביקורת אנושית לא־הרסנית

לאחר כל סבב צילום או יבוא מריצים `02_REVIEW_DATASET.bat`. הכלי אינו מוחק או
משנה RAW/metadata; הוא שומר החלטות לפי SHA-256 ב־`review/dataset_review.json`.
`Accept`, `Reject` ו־`Relabel` מיושמים אחר כך באופן אחיד ב־Capture, Validate,
Prepare ובדוח HTML. החלטה ניתנת לביטול או לניקוי בכל רגע.

ברירת המחדל `Recommended first` מדרגת קודם אובייקט חסר, חיתוך אפשרי בגבול,
גודל חריג, כפילות, חוסר הסכמה עם המודל ו־confidence נמוך. אלה המלצות לבדיקה
בלבד; המודל לעולם אינו פוסל פריים אוטומטית. `→ none/rock/paper/scissors`
גם מתקן label וגם מאשר את הפריים, ולכן אין צורך ללחוץ אחריו `Accept`.
`Recommended first`, `Unreviewed` ו־`Flagged only` מסתירים מיד פריים שקיבל
החלטה; כשהתור ריק סיימנו אותו. `All` ו־`Rejected` מאפשרים לחזור להחלטות.

אם Review מגלה שבתוך burst אחד נשמרו בטעות כמה מחוות, מותר לתקן כל פריים לפי
מה שבאמת מופיע בו או לדחות אותו. Stage 04 מקבץ לפי `session_id + burst_id`,
ללא תלות ב־label, ולכן כל הפריימים הסמוכים נשארים יחד באותו split ולא נוצרת
דליפה בין Train ל־Test. `Apply action to entire burst` נשאר כאפשרות נוחה כאשר
כל ה־burst תויג לא נכון; Relabel קבוצתי אינו מאשר מחדש פריימים שכבר נדחו.
כל כפתור החלטה עובר אוטומטית לפריים הבא, ו־`Undo` משחזר גם פעולה קבוצתית.

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

1. invalid וכל מה שמחוץ לטווח הייצור 100..600mm הופכים לרקע 0;
2. ספי עומק נבדקים בהדרגה מ־percentile 1 ועד 100;
3. בכל סף נמצאים רכיבי 8-neighbor מחוברים. רעש קטן מ־12 pixels נדחה, ונבחר
   הרכיב התקין הקרוב ביותר לפני שמרחיבים את החיפוש לרקע הרחוק;
4. רצועת 220mm משמשת רק למציאת seed אמין. ממנו מתבצעת צמיחת אזור אל שכנים
   שהפרש העומק המקומי שלהם עד 120mm. כך נייר אלכסוני בעל טווח עומק מצטבר גדול
   אינו נחתך לרצועות, ומגבלת 600mm עדיין מוחלטת;
5. מתבצע crop עם margin של 4 pixels ברזולוציית החיישן. בנוסף נשמרת מסגרת
   קבועה של 4 pixels בקנבס 64×50, גם כאשר האובייקט נוגע בשפת החיישן;
6. ערכי הרכיב מנורמלים ביחס ל־percentile 10 *של אותו רכיב*: טווח תבליט של
   260mm ממופה זמנית ל־32..255 והרקע נשאר 0;
7. ה־crop מוגדל ב־nearest-neighbor, שומר יחס ממדים וממורכז ב־64×50;
8. רק pixel שעוצמת העומק המנורמלת שלו גבוהה מ־210 נדרס ל־255; השאר הופכים
   לרקע 0. לאחר מכן dilation יחיד של 3×3 מתקן חורים ופסי dropout דקים. כך
   הזרוע הרחוקה יותר מסוננת ותבליט עומק פנימי אינו הופך לרעש. התוצאה היא
   `uint8` בינארי NHWC `[N,50,64,1]`.

Nearest-neighbor נבחר מפני שקל לממש אותו באופן זהה ב־C והוא אינו ממציא מרחק
ביניים. ה־dilation מתבצע ב־Helium/MVE. percentile/crop דורשים ב־FW histogram קטן ו־bounding box, ועדיין אינם
דורשים floating point או allocator. הקונפיגורציה נמצאת ב־`config/preprocessing.json`;
שינוי בה משנה hash ומכריח הכנה ואימון מחדש.

במסלול המודרך Stage 04 משתמש ב־tensor שהבקר שמר בתוך ה־NPZ, מחשב שוב את
גרסת Python ודורש שוויון מלא לפני הכנסת הדוגמה ל־train/validation/test. דגימה
ישנה או מיובאת שאין בה tensor של N6DF v3 נדחית כברירת מחדל. רק שימוש מפורש
ב־`04_prepare_dataset.py --allow-host-preprocessing` מאפשר legacy data ומסומן
ב־manifest כ־host-only; זו איננה הוכחת התאמה לבקר.

הפיצול איננו random לפי frame. כל צמד `session_id + burst_id` נשאר כולו
ב־train, validation או
test. אחרת frame 100 יכול להיות ב־train ו־frame 101 הכמעט זהה ב־test, ולקבל
accuracy מרשים אך שקרי. exact duplicates נשמרים פעם אחת בלבד. מבין החלוקות
החוקיות נבחרת החלוקה הקרובה ביותר ל־70/15/15 לפי מספר samples בכל מחלקה—not
לפי מספר bursts בלבד. שער נוסף דורש לפחות 10 samples מכל מחלקה בכל split
ולפחות 50% מדוגמאות המחלקה ב־train; burst זעיר של תמונה אחת אינו יכול להפוך
ל־validation שקרי. אם ביקורת אנושית תיקנה labels שונים בתוך אותו burst,
החלוקה מאזנת את כל המחלקות יחד אך עדיין שומרת את ה־burst הפיזי בשלמותו.

### 05 — אימון

`05_TRAIN.bat` בונה `spatial_cnn_v3_compact`: ארבע שכבות Conv2D ושלוש MaxPool. במקום
`GlobalAveragePooling`, שאיבד את מיקום האצבעות ועודד את המודל לספור בעיקר את
שטח הכתם, נעשה `Flatten` ולאחריו Dense קטן. כך נשמר המבנה המרחבי של אגרוף,
כף יד ושתי אצבעות. רק נתוני train עוברים augmentation דטרמיניסטי: הזזה של עד
4 pixels ו־mirror אופקי. שינוי עוצמה מבוטל כדי לשמור על חוזה הצללית 0/255;
validation ו־test נשארים מדידות אמת
בלתי משונות. הרשת עדיין פשוטה בכוונה:

- מעט parameters וזיכרון;
- ops סטנדרטיים שקל יותר לכמת ולמפות ל־NPU;
- אין post-processing מורכב;
- אפשר לאמן מהר גם על CPU.

גבול הכניסה של מודל Keras הוא `float32` בתחום הערכים המקורי `0..255`, ורק
בתוך המודל מתבצעת חלוקה ב־255. אין פירוש הדבר שה־Firmware שולח float: שלב 06
ממיר את הגבול ל־`uint8` quantized אמיתי עם `scale=1` ו־`zero_point=0`, ולכן
הבקר ממשיך למסור בדיוק את 3,200 הבתים הבינריים 0/255 ללא המרה בזמן ריצה.
המבנה הזה חשוב ל־STEdgeAI: מודל Keras שקלטו כבר `uint8` השאיר בגרף פעולת
`UINT8 -> FLOAT` שהקוד המיוצר הרחיב באותו buffer מ־3,200 ל־12,800 בתים. קלט
שחור הסתיר את התקלה, אך פיקסלים לא־אפסיים נדרסו במהלך ההמרה.

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

בנוסף הוא דורש במפורש input `scale=1`, `zero_point=0` ומוודא שאין פעולת
`CAST` בגרף TFLite. כך שלב 06 עוצר לפני STEdgeAI אם חוזר מבנה הכניסה שהוביל
לתוצאות `NOTHING` קבועות עבור כל תמונה לא־ריקה.

לאחר מכן כל test set רץ שוב דרך TFLite Interpreter. בודקים את ירידת הדיוק ולא
רק שהקובץ נוצר. `models/model_contract.json` מקפיא:

- SHA‑256 וגודל המודל;
- input/output shape ו־dtype;
- quantization scale/zero point;
- סדר המחלקות;
- preprocessing.

זהו ה־ABI בין Python, הקוד המיוצר על ידי ST וה־FW.

ה־quality gates מוגדרים ב־`config/training.json`. בפרופיל הלימודי הנוכחי
נדרשים לפחות 50% macro accuracy, לפחות 35% בכל מחלקה, וירידה שאינה גדולה
מ־5 נקודות אחוז אחרי quantization. אלה ספי לימוד שמונעים מודל שבור, לא יעד
איכות למוצר; לפני release רציני נכון להעלות אותם. הכשל שומר את הדוחות לצורך
ניתוח, אבל עוצר את ה־orchestrator לפני יצירת גרסת NPU שאינה עומדת בחוזה.

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

אם מריצים את `07_GENERATE_N6.bat` והפלט כבר תואם ל־TFLite ולכלי הנוכחיים,
ה־BAT שואל אם ליצור אותו מחדש עם `--force`. תשובת `N` משאירה את הקבצים
התקינים כפי שהם; תשובת `Y` מוחקת רק את `generated/st_ai_output` ומפעילה שוב
את קומפיילר Neural‑ART. קריאה ישירה מה־orchestrator נשארת לא־אינטראקטיבית.

שלב 07 מקמפל את **המודל** ל־Neural‑ART בלבד. שינוי בקובצי Firmware כגון
`tof_app.c` דורש Build של `AppliNonSecure`, ולא מצריך `--force` בשלב 07 כל
עוד קובץ ה־TFLite עצמו לא השתנה.

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

במודל הנוכחי blob המשקולות הוא 55,425 bytes. במקום להוסיף partition ופורמט
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

ה־generated input וה־activations של המודל הנוכחי נמצאים ב־SRAM5 החל
מ־`0x242E0000` ותופסים 17,408 bytes.
ה־FW שומר את החלק העליון של SRAM3 (`0x24244000..0x2426FFFF`) ל־CDC ול־scratch
של preprocessing, כדי להשאיר לפחות 360KiB heap ל־VL53L9. שלב 08 מסרב לשלב
מודל עתידי שבחר SRAM3, ומסרב ל־weight blob גדול מ־SRAM6; אין overlap שקט.

שלב 08 גם מתקין snapshot תואם של headers, sources וספריית runtime מתוך אותה
גרסת STEdgeAI שיצרה את הרשת. הוא אינו מבצע fallback ל־M55.

### 09 — bootstrap חד־פעמי של Secure

הפעלת שעוני NPU/CACHEAXI, פתיחת SRAM3–6 והעברת NPU interrupts ל־Non‑Secure
שייכות ל־TrustZone Secure. `.n6fw` מעדכן בכוונה רק את האפליקציה, ולכן מריצים
פעם אחת לכל לוח את `09_BOOTSTRAP_NPU_SWD.bat`. הוא בונה וחותם הכול, ואז—רק
אחרי הקלדת `BOOTCHAIN`—צורב דרך SWD רק FSBL + Secure. שני app slots ו־A/B
metadata נשמרים. `--build-only` בודק את כל התוצרים בלי לשנות חומרה.

### 10 — טעינת המודל המשולב ל־RAM

`10_LOAD_RAM.bat` הוא מסלול הפיתוח המהיר: incremental build ל־Secure
ול־Non‑Secure (target שלא השתנה הוא no-op) וטעינת שניהם דרך SWD ל־SRAM. כך גם
SAU/RISAF ו־bootstrap ה־NPU נבדקים בלי Flash. אין חתימה, write ל־Flash או שינוי
version; reset מוחק את ההרצה.

### 11 — HIL על תמונת ה־RAM הנוכחית

מריצים את `11_HIL.bat` מיד אחרי `10_LOAD_RAM.bat`, בלי לבצע RESET ביניהם.
במהלך הבדיקה מציגים לחיישן יד ומחליפים בין אבן, נייר ומספריים. הבדיקה קוראת
ברירת מחדל של 100 frames אמיתיים ובודקת:

- רישום Stage 10 חייב להכיל fingerprint זהה לקוד ולמודל הנוכחיים; שינוי קוד
  או מודל מחייב להריץ שוב `10_LOAD_RAM.bat` לפני שה־HIL ניגש ללוח;
- לפני טעינת TensorFlow או איסוף frames הוא שולח `RPS ON` ו־`RPS STATUS`.
  image ישן, פקודה חסרה או `ready=0` נעצרים מיד עם הסבר ולא אחרי 100 frames;
- הוא קורא את דגלי `APP_ST67W6X_*` מהקוד ומשווה אותם ל־`radio hardware` של
  התמונה שרצה. כאשר radio פעיל הוא דורש manager=`ready`, ‏`W6X_Init=passed`
  וגרסת SDK מדויקת לפי `radio_firmware/contract.json`;
- כאשר BLE פעיל הוא דורש GATT ו־advertising, וסורק מהמחשב פרסום יחיד בשם
  `N6-MAINT-xxxx` שמכיל את UUID שירות ה־CLI. כאשר Wi‑Fi פעיל הוא דורש גם
  `wifi status` ו־scan מוצלח;
- שני CRC לכל frame;
- frame IDs מתקדמים ללא חזרה/קפיצה בלתי סבירה;
- timeout אם התהליך נתקע;
- קצב observed ומספר payload CRC ייחודיים;
- אם TFLite קיים: prediction live על המחשב עם אותו preprocessing.
- לפחות 80% מה־frames מכילים תוצאת NPU של אותו frame;
- מונה ה־NPU עולה בכל תוצאה ואינו נתקע;
- לפחות 95% decision consistency בין TFLite ל־Neural‑ART. התאמת class ישירה
  עוברת; גם החלפת argmax בגבול כמעט שווה עוברת רק אם margin שתי המחלקות מוסבר
  במלואו על־ידי טולרנס ציוני ה־int8. סטייה מעבר לטולרנס עדיין נכשלת;
- לפחות 20% טנזורי מודל שאינם שחורים ולפחות ארבעה טנזורים שונים, כדי שסצנה
  ריקה או קבועה לא תוכל לאשר בטעות נתיב NPU שאינו מקבל את הקלט החי;
- הפרש מרבי שמוגדר ב־`config/training.json`. בפרופיל הלימודי הוא 16 יחידות
  raw `int8`, כלומר 0.0625 לפי output scale של 1/256.

ה־preflight והתוצאה נשמרים גם ב־`reports/hil_validation.log`; הדוח המובנה
נשמר ב־`reports/hil_validation.json`. רוב הודעות TensorFlow מוסתרות כדי
להשאיר את הפלט קריא; הודעת `Created TensorFlow Lite XNNPACK delegate` יכולה
עדיין להופיע והיא רק מציינת שההשוואה במחשב משתמשת ב־delegate של TFLite.

זה בודק את החיישן, processing task, framing, CDC וה־decoder בלי להסתמך על מסך
SPI. ההשוואה היא על אותו frame ID ועל raw output quantized, לא רק על label
סופי; לכן counter ישן או תוצאה ממוחזרת אינם יכולים לעבור את השער.

פערים ב־frame IDs מדווחים כ־CDC backpressure ואינם מוסתרים. הם אינם כשל לבדם:
ברירת המחדל שומרת 3 samples/sec ולכן ה־gate דורש לפחות 3 records תקינים לשנייה,
אפס שגיאות CRC, IDs שאינם חוזרים ולפחות 80% payloads שונים. כך sensor של 10Hz
יכול לדלג על frames ב־transport ועדיין לספק קצב צילום תקין ומדיד.

### 12 — התקנת release קבועה

`12_FLASH_RELEASE.bat` הוא מסלול בדיקת מערכת סופית: version נוכחי + 1, build
incremental, חתימת Non‑Secure, `.n6fw`, שליחת XMODEM דרך CN8, reset ואימות
אחרי חלון trial. המשקולות כבר בתוך אותו image. הוא דורש Stage 09 שהושלם ו־Stage 11 HIL
שעבר עבור fingerprint זהה, ומבקש להקליד `FLASH` לפני השינוי. `--package-only`
בונה וחותם בלי לשנות את הלוח ובלי להשאיר version חדש ב־header.
מיד לאחר HIL על RAM מחזירים את BOOT0 ואת BOOT1 ל־`1-2` בלי ללחוץ RESET:
תמונת ה־RAM המאומתת ממשיכה לרוץ, ו־Stage 12 משתמש בה להעברת XMODEM. ה־reset
שהסקריפט מבצע בסוף יעלה אז את הגרסה החדשה מה־Flash החיצוני.

### 13 — שחזור/התקנת מפעל למעגל ריק

`13_FACTORY_PROVISION.bat` הוא מסלול נפרד והרסני. לאחר הקלדת `ERASE ALL` הוא
מבצע full build/sign, מוחק את כל ה־NOR החיצוני, וכותב עם verify את FSBL ב־
`0x70000000`, ‏Secure ב־`0x70100000`, ‏Slot A ב־`0x70180000` ושני עותקי
metadata ב־`0x703E0000` וב־`0x703F0000`. לאחר החלפת jumpers ו־RESET הוא פותח
את CN8 ודורש שהפקודה `version` תחזיר את גרסת המקור שנבנתה.
אפשר להריץ `13_FACTORY_PROVISION.bat -BuildOnly` כדי לבדוק את כל תוצרי
הבנייה והחתימה בלי למחוק או לכתוב חומרה. הבנייה יוצרת גם
`FlashImages/factory-manifest.json` עם מספר הגרסה ו־SHA-256 לכל image.
הרצה עם `-SkipBuild` תיעצר לפני מחיקה אם ה־manifest חסר, אם גרסת המקור השתנתה,
או אם hash כלשהו אינו תואם. זיהוי CN8 משתמש גם ב־registry של Windows כאשר
מדיניות המחשב חוסמת WMI/CIM.

Full erase מוחק גם Slot B וכל trial/pending state. זה אינו תחליף ל־Stage 12:
עדכון רגיל נשאר A/B אטומי דרך XMODEM ואינו מוחק את התמונה המאושרת. במעגל חדש
שזקוק גם לעדכון NCP יש להריץ קודם את
`..\radio_firmware\01_UPDATE_MODULE.bat`; המדריך המלא נמצא ב־
[`../radio_firmware/README_HE.md`](../radio_firmware/README_HE.md).

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
2. במעגל חדש: `..\radio_firmware\01_UPDATE_MODULE.bat`, ואז
   `13_FACTORY_PROVISION.bat`. בלוח שכבר מריץ את הפרויקט מדלגים עליהם.
3. `10_LOAD_RAM.bat` כדי להריץ FW עם `DATASET STREAM` בלי flash.
4. לפחות 2 sessions של `01_CAPTURE.bat`, ובסך הכול 8 bursts לכל מחלקה.
5. `03_VALIDATE.bat`; לצלם עוד אם class/session diversity חלשים.
6. `BUILD_MODEL_FOR_N6.bat`.
7. `09_BOOTSTRAP_NPU_SWD.bat` פעם אחת ללוח; להחזיר BOOT0/BOOT1 ל־1-2.
8. `10_LOAD_RAM.bat` שוב כדי להריץ את המודל המשולב ב־SRAM.
9. מיד לאחר מכן, בלי RESET, להריץ `11_HIL.bat` ולהמשיך רק אם PC ו־NPU עברו את השער.
10. רק בסוף, `12_FLASH_RELEASE.bat` לגרסת flash שעולה אחרי RESET.
