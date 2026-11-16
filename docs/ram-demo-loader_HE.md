# טעינת דמו ל־RAM עם הגנה מפני כתיבות האתחול

הכלי במאגר הוא [Tools/load_checked_ram.py](../Tools/load_checked_ram.py).
הוא מבוסס על `load_checked_ram.py` המקומי ששימש בדמו ב־16.11.2026,
ומופעל גם מתוך `training/10_LOAD_RAM.bat`. ברירת המחדל של הכלי הישיר
היא בדיקה במחשב בלבד; רק `--execute` פותח חיבור ללוח.

## מדוע RAM לבדו אינו מספיק

הורדת ELF/BIN ל־SRAM אינה פקודת צריבת Flash, אבל היא מריצה FSBL:
`Firmware_Boot_Prepare()` יכול לקרוא ל־`boot_metadata_commit()` בעת מעבר
PENDING→TRIAL, חזרה מ־TRIAL, דחיית מועמד או מעבר לתמונת גיבוי.
הפונקציה מוחקת וכותבת את סקטור נתוני האתחול. גם אתחול האפליקציה או
הרדיו עלול לשמור הגדרות. לכן אין להסיק “אין כתיבות קבועות” רק מהשם RAM.

הכלי הישן `Tools/Debug-NonSecureRam.ps1` אינו מציב את מחסום הכתיבה הזה.
הוא נשאר כלי דיבוג הנדסי, ואינו מסלול הדמו המוגן.

## ההגנות במסלול הזה

1. מועמד נבנה עם `APP_SETTINGS_WRITES_ENABLED=0U`,
   `APP_SETTINGS_TRANSITION_ENABLED=0U` ו־`W61_CONFIG_PRESERVE=1`.
   נשמר סף heap של 369072 בתים. `--keep-network` משנה רק את מדיניות
   Wi-Fi/Cloud של המועמד; הוא אינו מתיר כתיבת הגדרות.
2. `ram-load.json` קושר SHA-256 של ששת קובצי FSBL/Secure/Non-Secure
   מסוג ELF ו־BIN. הכלי בודק התאמת ELF/BIN, תחומי טעינה ב־SRAM,
   וקטורים וסמלי העצירה לפני פתיחת חומרה. מדובר ברשומת בנייה מהימנה,
   לא בחתימה שמוכיחה דגלי קומפילציה מול קלט שרירותי.
3. בוחרים ST-LINK לפי `--board-serial` ומחזיקים את נעילת החומרה הקיימת.
   נוכחות CDC של אפליקציה גורמת לסירוב לפני חיבור הדיבוגר. לאחר החיבור
   נדרשים PC בתחום Boot ROM ו־`BOOTSR & 3 == 2` לפני הורדת RAM.
4. אחרי הורדת FSBL ולפני הרצתו מותקנת **נקודת עצירה חומרתית בכניסה
   ל־`boot_metadata_commit`**. אם מגיעים אליה במקום אל `JumpToApplication`,
   עוצרים לפני גוף הפונקציה; לא מדלגים על הכתיבה ולא ממשיכים את האתחול.
   בהגעה למסירת השליטה נדרש `boot_work_record.state == 1` ‏(CONFIRMED).
   גרסה 0 מותרת אם זו רשומת ברירת המחדל של השרשרת המותקנת.
5. מחליפים Secure ב־`0x34000400` ו־Non-Secure דרך הכינוי המאובטח
   `0x34100400`; קוראים בחזרה **את כל הבינארי** ומשווים בתים, לא רק
   וקטורים. ממשיכים דרך נקודות העצירה הידועות עד אתחול ThreadX.
6. בכשל אחרי הורדה נכתב ל־SRAM לולאת עצירה ונבדקים הקוד וה־PC לפני
   ניתוק. אם האימות נכשל, התוצאה `UNCERTAIN` ואין detach שממשיך ביודעין
   את מסלול האתחול. שומרים דוח ולוגים; אין ניסיון חוזר אוטומטי.

זו הגנת תוכנה על מסלול אתחול ידוע, **לא נעילת כתיבה פיזית של Flash**.
היא אינה מכסה פקודת עדכון שתישלח לאחר העלייה, קושחה שרירותית או שינוי
עתידי בנתיבי הכתיבה. אין להפעיל פקודות Flash/עדכון/שמירת הגדרות במהלך
הדמו. בדיקת SRAM אינה השוואת NOR מלאה לפני/אחרי.

הכלי המסודר אינו שולח Reset. בטעינה המקומית השנייה של הדמו הישן נשלח
איפוס AP0 דרך ST-LINK אחרי אישור מצב DEV; העובדה הזאת נשמרת בראיות.
במסלול המתועד כאן נכנסים ל־DEV ידנית לפני הטעינה. אין bootstrap, factory,
erase, שינוי OTP, עדכון רדיו או חתימת גרסת Flash במסגרת הפעולה.

<a id="reload-demo"></a>

## הכנה וטעינה חוזרת בפרויקט הראשי

כל הפקודות להלן רצות משורש `N6/project`. הייבוא מביא את הכלי והתיעוד;
הוא אינו מביא את תיקיית `danger-demo` או את הקבצים הקפואים מהעותק הניסיוני.
לשחזור הדמו ההיסטורי עצמו, הקבצים נשארו ב־
`D:\N6_AI_TEST\.local-dependencies\ram-demo-20261116\reload-inputs\ram-load.json`.
אפשר למסור לכלי את הנתיב המלא הזה, בלי להעתיק או לאמן את המודל מחדש.

### מועמד חדש

בפרויקט הראשי `APP_SETTINGS_WRITES_ENABLED` ו־
`APP_SETTINGS_TRANSITION_ENABLED` נשארו `1U`, כפי שהיו לפני הייבוא.
לפני בניית מועמד RAM מוגן יש להגדיר במכוון את שניהם ל־`0U` בקובץ
`AppliNonSecure/Core/Inc/app_settings.h`, בסביבת העבודה המיועדת לדמו.
שלב 10 מסרב לבנות מועמד אם ההגנה אינה מוגדרת; הוא אינו משנה את הדגלים
האלה אוטומטית. אין להריץ במקביל בנייה או עריכת קושחה אחרת.

לאחר 03–08, וכאשר FSBL ו־Secure תואמים כבר נבנו, סגרו מסופים ופנו BLE.
ודאו BOOT0=1–2, BOOT1=2–3 ולחצו Reset. לאחר מכן:

```powershell
$demo = Read-Host 'Training project ID'
$boardSerial = Read-Host 'Verified ST-LINK serial number'
.\training\10_LOAD_RAM.bat --project $demo --keep-network --board-serial $boardSerial
.\training\11_HIL.bat --project $demo
```

הריצו 11 רק אחרי הצלחת 10, ללא Reset ביניהם. שלב 10 שומר ומשחזר את
דגלי הרדיו והגרסה ותוצרי Debug שהוא משנה. דגלי ההגדרות שהכנתם ידנית
נשארים כפי שהגדרתם; אחרי סיום שלב 11 ושמירת דוח HIL ניתן להחזיר את
`app_settings.h` לברירות המחדל הרגילות. החזרת הדגלים אינה משנה את
הבינארי הקפוא. אין להריץ בנייה נוספת בין טעינה ל־HIL של אותו מועמד.

הטוען משתמש בעותקים תחת
`training/projects/<id>/generated/ram_candidates/<candidate>/load-inputs/ram-load.json`.
במסלול legacy הנתיב מתחיל ב־`training/generated/ram_candidates`.
דוח הטעינה הראשי הוא `load.json`, והפירוט ב־`checked-load/result.json`.
אין החלפה נוספת של קובצי Debug בזמן הטעינה.

### טעינה חוזרת מקבצים קפואים

בחרו manifest שנוצר למועמד שכבר נבדק. הבדיקה הבאה אינה נוגעת בלוח:

```powershell
$py = '.\training\.venv\Scripts\python.exe'
$manifest = Read-Host 'Full path to the verified ram-load.json'
& $py -B .\Tools\load_checked_ram.py --manifest $manifest
```

רק אחרי `PREFLIGHT PASS`, סגירת מסופי CN8 ו־ST-LINK, הפסקת איסוף/תמונות,
ניתוק לקוח BLE ו־Reset ידני ב־DEV, מריצים:

```powershell
$boardSerial = Read-Host 'Verified ST-LINK serial number'
$out = '.\.local-dependencies\ram-reload-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
& $py -B .\Tools\load_checked_ram.py --manifest $manifest --execute `
  --board-serial $boardSerial --output $out
```

תיקיית הפלט חייבת להיות חדשה. אפשר להוסיף `--expected-device` עם זהות
NCP מאומתת; מזהה ST-LINK נבחר לפני החיבור, וזהות NCP נבדקת אחרי העלייה.
לאחר `LOADED` בדקו `version`, `tof status`, `rps status` ובדיקה אחת בכל
מצב שהוגדר לדמו. Reset או אובדן מתח מאבדים את ההרצה.

אין דגל `--keep-network` בכלי הישיר, כי מדיניות הרשת כבר הוטמעה במועמד
הקפוא. בשלב 10 הדגל משמר כוונת Wi-Fi/Cloud לצד BLE; בלעדיו ברירת המחדל
היא BLE בלבד. מסוף Cloud דורש Workspace פתוח, ואיסוף USB מחייב פינוי BLE.

בכשל קראו את `result.json`,‏ `gdb.log` ו־`server.log` בתיקיית הפלט.
אל תעקפו סירוב metadata או תריצו שוב בלי להבין את מצב הלוח.
`--ide-root` מאפשר מיקום CubeIDE אחר; `--gdb-port` מאפשר יציאה אחרת.
אין סריקת יציאות או ניסיון חוזר אוטומטי.

## אימות הכלי

העברת הכלי והייבוא לפרויקט הראשי נבדקו במחשב: סירוב למצב שאינו DEV, עצירה לפני כותב
metadata, סירוב למצב לא מאושר, בדיקת גיבובים/ELF/BIN/גבולות SRAM,
כשל הורדה/קריאה חוזרת ועצירה בכשל. בוצעה גם בדיקת preflight על תוצרי
הדמו האמיתיים שנותרו ב־`D:\N6_AI_TEST`. **הגרסה המסודרת לא הורצה מחדש על חומרה בשינוי הזה.**
ראיות החומרה הקודמות שייכות לכלי המקומי ולתוצרים הקודמים, ולא מהוות
בדיקת חומרה חדשה של המעטפת המסודרת.

```powershell
& .\training\.venv\Scripts\python.exe -B -m unittest discover -s hil_tests -p test_checked_ram_loader.py
& .\training\.venv\Scripts\python.exe -B -m unittest discover -s training/scripts -p test_guarded_ram_network.py
```
