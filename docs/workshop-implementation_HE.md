# מסירת סדנת N6 — 24.10.2026

העמוד „איך מתחילים לעבוד עם N6?” הוחלף **מקומית במאגר האתר האמיתי**
בעמוד „בוא נתנסה ב TOF ו NPU על גבי רכיבים של ST”.
כתובות preview: `http://127.0.0.1:4183/wiki` פותחת כעת את הסדנה כברירת
מחדל; `/wiki/workshop` נשארת כניסה ישירה. פרק הארכיטקטורה נשמר בכרטיסייה נפרדת.
לא בוצעו push, merge או deployment.

## מה הוחל

- `Web_N6_ST67W611M1_VL53L9CX/src/Workshop.tsx`: מדריך עברי בשני חלקים,
  12 שלבים, הכנת מדריך, בדיקת RPS המוכן, תכנון משימה חדשה, איסוף/Review/
  אימון/quantization, מסלול XIP ידני, התאוששות ובעלות מרובת תחנות.
- `src/Workshop.css`: עיצוב RTL, תוכן עניינים, תרשימי מסלול, טבלאות,
  קטעי פקודות LTR, תמונות וכיתובים, התאמה למסך צר ו־focus גלוי.
- שינוי ממוקד ב־`src/App.tsx`: החלפת המאמר בלבד וחיבור `/wiki/workshop`.
- `public/workshop`: שלוש תמונות אמיתיות ו־`verify_session_split.py`,
  כלי audit לקריאה בלבד שמתווסף לסדנה ומסומן ככזה.
- `README.md` של האתר: הסבר על התוכן החדש וגבולות האימות.

נשמרו שינויי הטרמינל שהיו קיימים לפני העבודה. לא נערכו קובצי הקושחה,
קובץ המשתמש `training/PLATFORM_UPGRADE_PLAN_HE.md` או נתוני הלמידה המקוריים.
כל בדיקות המחשב שהפיקו תוצרים עבדו בעותק מבודד תחת
`.local-dependencies/workshop-audit-20261024`.

## הראיות שנאספו עכשיו

קריאת pyserial זיהתה COM6/STLINK `000C00344142501620353451` ו־COM8 עם
serial `N6TOF001`. נרכש lease ללא גניבה; נפתח רק COM8. נשלחו פקודות
גרסה וסטטוס, ללא MAP ON, ללא DATASET ON, ללא Wi-Fi/Cloud enable וללא reset.

תשובות: firmware47, SDK2.0.106.0, BLE disconnected, מפת תמונה OFF,
dataset OFF, requested/active destination NONE. ToF frame67315→67323,
NPU ready/runs24604/errors0. Cloud כבר היה paired ומבצע polling עם last409,
request errors23; מונה תמונות ToF נשאר0 לפני/אחרי. לא שינינו את מצבו.
פקודת `cloud training status` אינה קיימת ב־47 והחזירה Usage; לא ניתן
להסיק מתמיכת M5 ב־main שתחנה47 כוללת אותו ערוץ Cloud capture.
הפורט וה־lease שוחררו. `board-status.json` מכיל workspace מושחר.

גרסאות כלים: Python3.11.9, TeraTerm5.3, CubeIDE2.2.0 נמצא;
STEdgeAI CLI החזיר בפועל **4.0.1-20581**, למרות שם תיקיית4.0.
לא הותקנה או עודכנה תוכנה.

`test_model_contract` ו־`test_spatial_profile`: שני tests PASS.
`analyze_training.py --project m6-depth-two --skip-inference` יצר דוח HTML
מהדאטה/דוחות הקיימים בעותק מבודד. אין אימון חדש, ואין תחזיות חדשות בטענה זו.

`verify_session_split.py` מצא חפיפת שני sessions בין כל splits בדאטה הקיים,
כצפוי מהפרדה ברמת burst. נוצר fixture בלבד של16 sessions, שמונה לכל
מחלקה,12 דוגמאות ו־burst אחד לכל session. שימוש בפונקציית assign_groups
האמיתית של Stage04 הפיק144/24/24 דוגמאות ו־12/2/2 sessions;
audit PASS ללא חפיפת sessions או hashes. אין זו בדיקת סצנות כוס אמיתיות.

האתר: build TypeScript/Vite PASS, lint PASS. בדפדפן נמצאו12 שלבים,
אפס עוגנים חסרים, שתי תמונות תקינות ואפס שגיאות console.
בדיקת390px: אין overflow אופקי. נבדקו גם תצוגת desktop ותוכן עברי/LTR.
העוגנים והקישורים עבדו; לא נלחץ Connect או בוצע חיבור חומרה בדפדפן.

## צילומים ומה הם מוכיחים

- `current-wiki-before.png`: העמוד הציבורי הישן, לפני שינוי.
- `serial-status.png`: צילום **דוח מקומי של פלט USB שמור** שנקרא מכרטיס47.
  הוא אינו צילום Tera Term או תמונת חיישן חדשה.
- `training-report.png`: צילום דוח confusion matrix אמיתי שנוצר עכשיו
  מתוצרי m6-depth-two (none/rock). אינו מודל כוס ואינו RPS ארבע מחלקות.
- `workshop-desktop.png`, `workshop-mobile.png`: צילום העמוד החדש המקומי.
- `workshop-evaluation.png`: צילום תוכן העמוד המקומי באזור Review/evaluation.

צילומי חיווט/ג'אמפרים פיזיים, Tera Term חי, בורר BLE מחובר ו־capture חי
עדיין חסרים. צילום Review הושלם לאחר אישור המשתמש לניסיון נוסף אחד. לא הומצאו צילומים במקומם. המדריך מציין את הפערים.

## הרשאות: מה קרה בפועל

1. פתיחת GUI ה־Review בתוך הסביבה המוגבלת נכשלה בטעינת init.tcl.
   פתיחת אותה תוכנה קיימת על העותק המבודד בהרצה מאושרת עם TCL_LIBRARY/
   TK_LIBRARY הצליחה; לא הותקנה תוכנה.
2. בקשת Computer Use לפתוח גישה לחלון `N6 — Classes and labels` מזהה19402720
   **הסתיימה ב־approval timeout**. לא התקבל אישור גישה, לא בוצעה לחיצה או
   תמונת מסך, ולא חזרנו על הבקשה באותו מועד. לאחר אישור אנושי חדש בוצע ניסיון נוסף אחד
   שהצליח, כמפורט בבדיקת המסירה בהמשך. זו אינה דחיית auto-review של צריבה.
3. כתיבת העמוד אל מאגר האתר מחוץ ל־writable roots אושרה במסלול scoped
   `require_escalated` והושלמה. אין חסם כתיבה שנותר.
4. Vite preview בהרצה מוגבלת נכשל ב־EPERM בעת כתיבת config זמני תחת
   node_modules/.vite-temp. אותה פעולה במסלול הרשאה ממוקד אושרה והשרת פועל.
   לא שונו ACL, Git trust או מדיניות אבטחה.

## מסלול XIP ידני קיים לעומת התאמות נדרשות

**אפשרות ידנית קיימת ללא שינוי מנגנון קושחה:** Stage08 בעותק XIP מקבל
פרויקט באמצעות `N6_TRAINING_CONTEXT_ROOT` ו־`--project`; PROJECT_ROOT
נקבע לפי מיקום הסקריפט. לכן מפעילים את script08 שבעותק XIP, לא script08
של main, עם Python3.11 והתלויות הנכונות. כך אפשר לשלב קוד ו־weights של
מודל חדש בלי merge בין ענפים. פעולה זו טרם בוצעה במסגרת העבודה.

`pwsh -NoProfile -File Tools/Build-Xip.ps1 -Slot B -FirmwareVersion 48 -Label group01` היא
דוגמה **רק אם אומת שוב A47 פעיל ו־B הוא היעד המתאים**. הסקריפט בונה RAM
control ותוצר XIP, חותם ומייצר חבילת
`.local-dependencies/xip/v48-B-group01/N6-XIP-B-v48.n6fw`.
`Test-XipPackage.ps1` בודק target/slot/version, vectors, גודל, SHA וחתימת
P256; `Send-Xmodem.ps1 -File ... -Port ...` מעביר דרך CN8 ומפעיל את
מנגנון A/B הקיים. אלה שמות ופרמטרים אמיתיים שנבדקו בקריאת הקוד.
אין כאן טענה שבנינו, התקנו או אימתנו מודל חדש ב־XIP.

**שינויי הקושחה הנחוצים למשימה חדשה:** התוצרים שה־pipeline כבר יודע ליצור:
מחלקות, n6_model_contract, preprocessing נבחר, network C/headers,
weights/runtime. אין ראיה לצורך בשינוי חדש ל־FSBL/Secure updater,
ל־USB, ל־DMA או ל־TrustZone רק כדי לתמוך בעוד מחלקות. טווח spatial
הנוכחי הוא100–1200mm; למשימה של אדם במרחק אחר צריך לאפיין פרופיל מתאים.
ה־UI הנוכחי בוחר profile אך אינו עורך שרירותית את גבולותיו.

**שינוי host מינימלי שנותר:** `hil_tests/run_xip_model_regression.py`
מקובע ל־SHA של מודל RPS ולארבע מחלקות. להוסיף קלט מפורש של project,
TFLite, contract ו־build manifest; לאמת provenance של החבילה והמודל;
להשתמש ב־class_count/output_count וב־preprocessing מהחוזה במקום constants;
ולהשוות tensor וציוני אותו frame ל־TFLite, תוך שמירת CRC, freshness,
coverage, distinct/nonempty והספים הקיימים. אין להפוך `--no-model` ל־PASS.
Stage11 הכללי כולל רבות מההשוואות, אך קשור ל־Stage10 RAM ולכן אינו תחליף
שאפשר להפעיל על XIP באמצעות זיוף state. התאמת HIL והפעלתו על מודל חדש
הן משימה נפרדת לאישור ההורה; לא שונו כעת.

**תצוגה:** RPS labels באתר נכונים לחלק א׳. למשימה חדשה אפשר לקרוא
class/scores מה־CLI ומדוחות המחשב. כדי להציג שמות חדשים באתר יש להכליל
`rpsProtocol.ts` (כרגע q.length=4 ורשימת ארבע מחלקות) ואת
`tofProtocol.ts` (classId<=3 ושמות קבועים) עם חוזה מודל מזוהה.
זו התאמת presentation/protocol נפרדת; לא נעשה refactor כזה במשימת התוכן.

## פעולות שנותרו מותנות

רדיו חדש: QConn `--help` בלבד הופעל, בלי port או פעולת חומרה. עזרתו
אומרת efuse options ואינה מבטיחה read-only. ה־README ותסריט T01 הרשמיים
של ST אומרים שהבינאריים מיועדים ל־locked NCP ושעדכון עשוי לנעול מודול
שטרם ננעל. לכן לא בוצעה פעולת רדיו, ויש להגדיר provisioning מאושר לפני
שמדגימים עדכון למודול חדש. יש לאמת את תצורת החומרה והשפעת מחיקת LittleFS.

factory-fresh: לא אומת לוח ריק עם XIP47; Stage13 של main מוחק NOR
ומתקין מסלול אחר, ולכן אינו מוצג כהכשרת XIP מוכחת. אין לערבב ביניהם.
לא בוצעה בדיקת power-loss בזמן כתיבת NOR.

Cloud: אין grant חדש לשיתוף חיישנים. HTTP409 ו־sensor0 מתועדים;
לא בוצעה הדגמת Cloud חדשה. נדרש אישור נתונים/נמען/כמות/מטרה לפני capture.

ערכת RPS מוכנה: פרויקט Git כולל `.gitkeep` בלבד בתיקיות raw/models/reports;
חומרי הלמידה המקומיים אינם אוטומטית חלק מ־clone. המדריך צריך להפיץ ערכת
חומרים קפואה עם hashes, לצד הקוד. לא בוצעה העלאת dataset ל־Library.

## תוצרים

גרסת HTML עצמאית כוללת את כל תמונות המסירה ואת כלי ה־audit להורדה,
ללא חומרי training גולמיים, credentials, workspace או token.
ה־preview המקורי מקומי ולא שונה בו קישור הייצור. השינוי המלא נשאר במאגר
האתר לעיון; אין commit חדש או deployment.

עותק HTML נשמר גם ב־Library בשם N6-workshop_HE.html. כתיבת xattrs מקומיים
באמצעות helper נכשלה משום ש־Windows Python אינו חושף os.setxattr;
שמירת קובץ Library עצמה הצליחה. זהות Library נשמרה ב־library-save-result.json,
אך אין טענה ש־xattrs הוחלו. פקודות המדריך משתמשות ב־PowerShell7/pwsh;
זוהתה גרסה7.6.5 בסביבת הבדיקה, ואין להניח שהותקנה בנפרד בכל תחנת משתתף.


## בדיקת מסירה אחרונה ואישור צילום Review

המשתמש אישר במפורש ניסיון נוסף אחד לפתיחת/צילום Review ללא שינוי נתונים.
נפתח חלון חדש657234 של Classes and labels בעותק המבודד, והגישה אליו אושרה.
נבחרה שורת Background קיימת לצפייה בלבד, והחלון הוגדל לצילום כל הפקדים.
`classes-review.png` הוא צילום אמיתי שהוטמע בעמוד. לא נלחצו Apply profile,
Assign label, Reject או פעולות מחלקות. השוואת4501 קובצי data/review/config
ו־project.json למקור הראתה אפס קבצים שונים. אין כאן capture חדש או אימון חדש.
ניסיון סגירה דרך כפתור החלון נכשל בהפעלת החלון; הוא נותר פתוח, ולא בוצע
ניסיון נוסף או עקיפת הרשאה לצורך הסגירה. אין לו חיבור חומרה.

המסלול הישן `/wiki` נבדק בדפדפן ומציג כעת את הסדנה כברירת מחדל, עם כותרת
טיוטת עבודה מפורשת. `/wiki/workshop` ממשיך להציג אותו תוכן.
פרק הארכיטקטורה עדיין נגיש. build ו־lint אחרי התיקונים עברו.

פסקת הרדיו מסומנת למדריך בלבד ומסבירה שהנעילה האפשרית במודול חדש עלולה
להיות בלתי הפיכה, וש־reset או החלפת image אינם מחזירים מצב factory.
אין פקודת צריבת רדיו בבלוק copy-and-run. אין הוראת fuse/OTP.

סריקת HTML הטקסטואלי לא מצאה PEM private keys, JWT או Bearer token value.
כל התמונות נבדקו חזותית ואין בהן credentials, קוד pairing או workspace token.
תמונת Review מכילה רק נתוני דוגמה היסטוריים ונתיבים יחסיים, לא סודות.
הסריקה אינה טענה להוכחה קריפטוגרפית להיעדר כל סוד אפשרי.

Tera Term תומך רשמית ב־`/R=<log>` להצגת קובץ שמור ללא פתיחת COM:
https://teratermproject.github.io/manual/5/en/usage/tips/loging_howto.html .
אפשרות זו נבדקה בתיעוד בלבד. אין חלון Tera Term קיים או גישת צילום מאושרת
שנבדקה עבורו בסבב זה, ולכן לא נפתח חיבור Serial ולא הופק צילום חלון כזה.
אין להשתמש בהרשאת Review כדי להרחיב גישה ליישום אחר. צילום Tera Term
עדיין מסומן כחסר; צילום פלט ה־USB המקומי אינו מוצג כתחליף מאומת שלו.


## ניסיון Tera Term offline replay — תוצאת מסירה אחרונה

נוצר `teraterm-status-replay.log` מפלט version/rps status/radio info שנקרא
באמת קודם מכרטיס47. בתחילת הקובץ כיתוב OFFLINE REPLAY ותאריך, והבהרה
שלא מדובר בבדיקת תמונה/חיישן חדשה. אין בקובץ Cloud workspace או credentials.

הופעל Tera Term5.3 עם `/R=<קובץ הלוג>` ו־`/NOLOG` בלבד, ללא host או
`/C` וללא macro. מסלול ההפעלה הרגיל אושר, כולל ניסיון חלון אינטראקטיבי
לצילום. תהליך60192 דיווח `N6-Workshop-OFFLINE-REPLAY - [disconnected] VT`.
למרות זאת, Tera Term לא הופיע ב־cua.listWindows או cua.listApps, ולכן
לא היה יעד חלון שניתן לבחור לפי מסלול הצילום הנתמך. לא בוצע צילום,
לא הופיעה בקשת הרשאת צילום נפרדת, ואין דחייה או בקשה שעדיין ממתינה.
הפעולה החסומה היא צילום חלון replay ב־Tera Term; הסיבה היא שאינו חשוף
במלאי החלונות הנתמך. לא ננקטה דרך צילום אחרת או עקיפת הרשאה.

תהליכי replay60192 ו־53916 שנוצרו למשימה נסגרו. תהליך21816 מהניסיון
המוסתר הראשון נשאר: Stop-Process נכשל ב־Object reference not set to an
instance of an object. לא בוצעו ניסיונות נוספים לאחר תוצאת הניקוי הזו.
זהו תהליך replay ללא פורט COM שהוגדר על ידינו; צילום לא הושלם.
חלון Review לא נסגר ולא נעשה ניסיון נוסף לסגור אותו.

העמוד עדיין מסמן צילום Tera Term חי/הגדרותיו כחסר; תמונת פלט ה־USB
מסומנת כדוח מקומי של פלט שמור. עותק Library עודכן באותה זהות עם דוח
התוצאה, ללא הוספת צילום Tera Term שלא הופק בפועל.
