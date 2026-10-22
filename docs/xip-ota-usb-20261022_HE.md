# XIP ועדכוני USB / OTA — ענף ניסוי 2026-10-22

## ניסיון אתחול חיצוני 18:42 UTC — טרם אומת

המשתמש אישר העברת BOOT1 ל־1–2 ולחיצת RESET. המקליט הפסיבי היה פתוח,
אך קיבל אפס בתים; במצאי USB הופיע רק ST-LINK, ללא COM8 של האפליקציה.
לכן אין אישור אתחול קבוע. קריאת BOOTSR דרך AP0 בלבד נכשלה; לא בוצעו
איפוס נוסף, כתיבה לפלאש או חיבור דיבאגר AP1. מצב הריצה הנוכחי אינו ידוע.
המקליט הראשון נסגר ושחרר בעלות בצורה מסודרת; נתוניו נשמרו.

נבדק [מסמך ST ES0620, גרסה 5](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf).
סעיף 2.2.18 מתאר תקלה ב־NRST החלה גם על Rev B, כפי שזוהה בלוח.
סעיף 2.2.22 דורש השבת בוררי שעון מסוימים לברירת מחדל לפני software reset.
בפועל, בריצה התקינה נמדד CCIPR6=`0x00010000`, ובקוד USART1 נבחר HSI;
שניהם תנאי סיכון קונקרטיים. כרגע זהו הסבר אפשרי, לא הוכחה מבודדת לסיבה.
לא נשנה OTP או הרשאות דיבאג כדי לחקור זאת.

הבדיקה הפיזית הבאה היא **ניתוק כל מקורות המתח וחיבור מחדש, כשהג׳מפרים
נשארים במצב FLASH: ‏BOOT0=1–2, ‏BOOT1=1–2**. יש להכין הקלטת UART
לפני ביצועה. ניסיון לפתוח מקליט עם DTR פעיל נחסם על ידי auto-review לפני
תחילת התהליך, עקב חשש להשפעה על קווי בקרה. לא בוצע ניסיון חוזר עם DTR
פעיל. המקליט הבא נפתח בהצלחה עם DTR/RTS כבויים וללא שידור UART.
אין עדיין טענה ש־DTR היה הגורם להיעדר לוג באתחול הראשון.

לאחר קבלת baseline של cold boot, יש לטפל במסלול האיפוס של העדכון:
השבת שדות השעון לפי errata עם שני מקורות שעון פעילים, רוטינת מעבר ב־RAM
וללא API מאובטח חדש. טיפול ב־NRST דורש גם בדיקת workaround בתחילת FSBL
והקצאת זיכרון שמור מפורשת; אין להעתיק בעיוורון כתובת magic מהדוגמה של ST,
כי העתקת תמונת Secure הנוכחית דורסת אותה. טרם יושם או נבדק תיקון כזה.

שרשרת האתחול שנכתבה והגיבויים לא שונו בסבב הנוכחי. כל התוצאות להלן
הן ראיות קודמות; ההודעה על מצב DEV/לולאת FSBL הוחלפה במצב הלא־ידוע לעיל.

## מצב מאומת חדש — לפני אתחול קבוע מהפלאש

הענף הוא `feature/n6-xip-ota-usb`. ‏main לא שונה, לא מוזג ולא נדחף.
שרשרת FSBL/Secure החדשה **כבר נכתבה לפלאש** ונבדקה בשתי קריאות מלאות
ובקר קריאה עצמאי. כל הבתים מ־`0x70180000` ועד סוף המטא־דאטה נשמרו:
A/v12, כל B/v11 ו־seq33 במצב CONFIRMED/A12 עם B11 לשחזור.
SHA256 של הגיבוי העדכני:
`6cc2cfb51d893b06e75d32c1614818406bcc2a6219f68cb2b98a9c9cae43faaf`.
הגיבויים המקוריים מלפני כל כתיבה נשמרו גם הם.

**הפעולה הפיזית הבאה:** להשאיר BOOT0 במצב 1–2, להעביר BOOT1 מ־2–3
ל־1–2 וללחוץ RESET פעם אחת. לאחר מכן להודיע שהפעולה בוצעה.
אין צורך לשנות OTP, מתחי HSLV, הרשאות אבטחה או לבצע Pair ב־Windows.
כרגע הלוח ב־DEV, עצור בלולאת Secure של FSBL ב־RAM; האפליקציה אינה רצה.
האתחול הפיזי הבא הוא בדיקה שעדיין לא בוצעה, ולא הבטחה שהאתחול הקבוע עבר.

מה כבר נמדד:

- ‏A12 הגיע ל־`main` ב־`0x70191588` מתוך הפלאש, SP=`0x24200000`.
  נמדדו VTOR=`0x70180400`, ‏I-cache פעיל ו־MPU לקריאה והרצה בלבד בסלוט A.
- ‏100 פריימים אמיתיים: 100/100 טנזורים מדויקים, 100/100 החלטות תואמות,
  CRC ללא שגיאות, הפרש ציון מרבי 1, במשך 28.703 שניות.
  הסצנה סטטית עם טנזור ייחודי אחד; זו בדיקת חישוב, לא דיוק זיהוי בשטח.
- חמש פקודות BLE עברו, המרבית 176.548ms מול סף קיים של 1500ms;
  `pair=False`, ללא מנוי תמונות ועם ניתוק מסודר.
- ה־Secure החדש שומר שני ממשקי כתובות לאותם שבעה שירותים קיימים:
  B11 ב־`0x3400F600`, ‏A12 ב־`0x3400FF40`. ‏B11 עבר את שער השעון והגיע
  ל־main, ואז נעצר לפני הפעלת הקוד הישן. A12 עבר ריצה מלאה ואישור אתחול
  עם אותו Secure. אין כאן בדיקת ריצה מלאה של כל שבעת השירותים ב־B11.
- בסטטוס האחרון של A12: ‏NPU300/errors0, ‏SPI faults0, ‏ToF מתקדם,
  Cloud ToF sent0, ‏dataset off, ‏image NONE. לא נשלחו דגימות חיישן לענן.

קיבולת הערימה הסטטית עלתה מ־369,136 ל־862,256 בתים, תוספת 493,120.
טרם נמדדו שיאי שימוש דינמיים במחסנית/ערימה או פיצול זיכרון. ה־NPU משתמש
בבריכות נפרדות: קלט 3,200, פלט 4, אקטיבציות 17,408 ב־SRAM5 ומשקולות
55,425 ב־SRAM6. זיכרון CPU שהתפנה ב־SRAM2 אינו אוטומטית בריכת NPU;
מודל גדול מחייב חלוקה מפורשת בכלי Neural-ART ובדיקת קישור, cache והרשאות.
המשקולות הנוכחיות עדיין מועתקות ל־SRAM6; לא נטען שהן עובדות ישירות מפלאש.

״רק מהפלאש״ מתייחס לקוד ולנתונים הקבועים של האפליקציה הלא־מאובטחת.
ROM מתחיל את האתחול, FSBL ו־Secure פועלים ב־RAM, ונתונים משתנים,
מחסניות, ערימה, מאגרי USB/רדיו/חיישן ובריכות NPU מחייבים RAM. גם דרייבר
מחיקת/כתיבת הפלאש חייב לרוץ מ־RAM בזמן שמצב המיפוי של אותו שבב מושבת.
אין כאן הבטחה לאפליקציה פיזיקלית ללא RAM או לכל קוד המערכת ב־NOR.

החיישן מפיק 54×42. מיקוד RPS הקיים הוא בחירת רכיב קרוב וחיתוך בתוכנה,
לא הוכחה למיקוד אופטי אוטומטי. הנתיב `spatial_depth_v1` כבר תומך בשדה
המלא ובהמרה ל־64×50; במטלה הקודמת מודל מרחבי עבר 100 פריימי NPU.
יש לשמור בחירה בין חוזי העיבוד: אין להזין תמונה מלאה למודל שאומן על חיתוך.
לא אומן כאן מודל חדש ולא נוצרה טענה לדיוק משופר.

מה עדיין פתוח: אתחול חיצוני אמיתי אחרי RESET/ניתוק מתח; כתיבת חבילה מלאה
תוך כדי XIP דרך USB; עדכון OTA אמיתי; בדיקות חבילה פגומה, ניתוק העברה,
rollback ואישור לאחר עדכון עם השרשרת החדשה. התקנת A12 הקודמת דרך USB
אומתה, אך המתקין אז רץ ב־RAM. אישור האתחול של XIP כבר כתב מטא־דאטה;
זו אינה הוכחה לכתיבת תמונת firmware מלאה בזמן XIP.

לשחזור: לחזור ל־DEV עם BOOT0=1–2 ו־BOOT1=2–3 וללחוץ RESET.
יש להשתמש בגיבוי המדויק ובבקר הקריאה המאומת, ללא mass erase וללא ניסיון
לשנות OTP. אין להתחבר לדיבאגר בזמן ריצת NS; תחילה AP0/NRST ואז אימות
ROM. מצב Under Reset של CubeProgrammer נכשל, אבל HotPlug ובקר הקריאה
פעלו. מנהל הפלאש הרשמי נכשל במחיקה; קריאה עצמאית הוכיחה שלא שינה בית.
הכתיבה שהצליחה השתמשה בדרייבר FSBL ב־RAM, ארבעה סקטורים שבבעלות
שרשרת האתחול בלבד, Secure לפני FSBL, עם שימור זנבות ובדיקה מלאה.
אין לחזור אוטומטית על כתיבה שנכשלה או שתוצאתה אינה ידועה.

לצורך בדיקת OTA הבאה יש להשתמש רק בשרת ובצימוד הקיימים. יש להשאיר
מפת Cloud כבויה ולא לפתוח איסוף דגימות. סביבת העבודה הייתה inactive/409;
הפעלתה לצורך OTA תיעשה רק לאחר אימות A12. ‏B11 נשמר עד להוכחת שחזור
ואתחול קבוע תקינים. שרשרת האתחול עצמה אינה A/B: כשל כתיבה שלה דורש
DEV ו־ST-LINK; לכן נשמרו גיבויים מדויקים לפני השינוי.

הסעיפים המתוארכים בהמשך הם היסטוריית בדיקות; מצב הלוח העדכני הוא לעיל.

## עדכון 16:41 — rollback עצמאי וריצת XIP מלאה

חיבור המתח המלא החזיר את AP1: נקראו PC=`0x18003514` ו־BOOTSR=2.
בקר הקריאה נעצר לפני בחירת האפליקציה ושמר שני גיבויי NOR זהים של4MiB,
SHA256=`8a7bca4efc889a65b2928b5b8b0dbba46357a1862bb0323e43a31b0b73ffaf30`.
שתי רשומות ה־CRC תקינות. החדשה היא seq30/CONFIRMED/B/v11 ללא pending;
כל ה־1MiB של B ושרשרת האתחול ב־NOR זהים לגיבוי המקורי.
תוכן A תואם בדיוק לחבילת A/v12. זהו אימות עצמאי של ה־rollback.

ניקוי הקריאה נכשל תחילה כי הסקריפט השתמש ב־0, שהוא ENABLE בממשק ST.
תוקן שימוש ב־EXTMEM_DISABLE, וקריאה על הלוח אישרה שערכו1 ותוצאתו0.
ה־PC נבדק בתוך Secure Error_Handler, ללא כניסה לאפליקציה הישנה.
גם סירוב הבקר לטעון RAM כשהמעבד אינו ב־ROM נבדק בחומרה.
הקוד מתעד כעת פקודות MI ונמנע מ־interrupt כשהמעבד כבר עצור.
עשר בדיקות host עברו. אין כאן טענה שההרצה הראשונה הסתיימה ללא כשל.

לאחר אימות B/v11 ללא pending הועברה אותה חבילת A/v12 חתומה דרך USB:
498336/498336 בתים, finalization מאומת. זו העברה חוזרת מכוונת אחרי rollback
מאומת, ללא עריכת metadata ידנית. FSBL/Secure תואמים נטענו ל־RAM בלבד.
נמדדו שוב PC=`0x70191588`, ‏LR=`0x701A1817`, ‏SP=`0x24200000`;
הפעם האפליקציה המשיכה לרוץ: USB תקין, ToF frame143, ‏NPU runs56/errors0,
BLE GATT מוכן ו־advertising ACK. זו אינה עדיין בדיקת BLE באוויר או soak.

ב־UART נמדד בזמן10208ms: `boot confirmed; rollback window closed`.
כלומר שירות Secure כתב ואימת את metadata האישור בזמן שהאפליקציה מבצעת XIP.
מצופה כעת seq33/CONFIRMED/A12 עם B11 כ־fallback; קריאה עצמאית של הרשומה
לאחר האישור עדיין חסרה. זו אינה עדיין העברת חבילת firmware מלאה מתוך XIP.
נמדדו imageNONE, ‏datasetoff ו־Cloud ToFsent0. מאוחר יותר Wi-Fi קיבל IP
והשרת השיב409/workspace_inactive; לא נשלחה בקשה לזרימת חיישן לענן.

בדיקת100 פריימים נעצרה לפני פתיחת USB ופקודת STREAM ON: קובץ עזר מקומי
שיצרתי בשם inspect.py הסתיר את מודול Python התקני. טעינתו דרך dataclasses
הפעילה בטעות probe לדיבאגר, שניסה לקרוא כתובות Secure בזמן ריצת NS.
התקבל detachE31, פתיחת USB נתקעה ו־resume ללא reset נכשל בגישה ל־AP1.
מספר פריימי ההשוואה שהתקבלו הוא0; אין לטעון שעברה בדיקת100 פריימים.

הקובץ שונה ל־probe_dev_rom_attach.py ונעטף ב־main guard. בדיקת HIL מסירה
את תיקיית העזרים מ־sys.path, מאמתת inspect מהספרייה התקנית ומציעה
`--preflight-only`. הבדיקה ללא חומרה עברה עם TensorFlow, המודל המקורי
59f72382… וה־contract המקורי5137ed48…. מנגנון כשל ה־debug/NS עצמו עדיין
לא הוכח; לא יופעלו probes לדיבאגר בזמן ריצת NS בסיבוב הבא.

כל הידיות וה־lease שוחררו. מצב הריצה הנוכחי אינו מאומת ונדרש חיבור מתח
מלא מחדש ב־DEV. אחרי האישור: קודם לקרוא metadata באמצעות הבקר המתוקן,
ואז לאתחל את A12 שכבר שמור עם שרשרת RAM תואמת, ללא כתיבת USB נוספת.
רק אחר כך להריץ100 פריימים ב־USB אחרי preflight. שרשרת NOR עדיין מקורית;
OTA, עדכון חבילה מתוך XIP, אתחול מתמשך, בדיקות הפרעה וחבילות פגומות חסרים.

## ארכיון — עדכון אחרי RESET פיזי ב־16:22 UTC

המשתמש אישר לחיצה על RESET במצב DEV. ניסיון attach ללא reset עדיין נכשל
ב־`Target unknown error 32`, לפני חיבור GDB ובלי טעינת RAM. דרך AP0 זוהו
device486/revZ ומתח3.28V, אך גם קריאת DBGMCU דרך הכתובת NonSecure נכשלת.
מצב ה־PC, ה־BOOTSR והריצה אחרי הלחיצה אינם ידועים. לא בוצע reset נוסף
מהפרוב, לא נטען קוד ולא נכתבו image או metadata בסבב הזה. כל הידיות וה־lease שוחררו.

התוצאה שוללת את ההנחה שלחיצה פיזית על RESET מספיקה לשחזור המצב הנוכחי.
היא אינה מוכיחה מה מקור התקלה. נדרש שוב ניתוק מלא של כל מקורות המתח,
כולל ST-LINK/CN8/מתח חיצוני אם מחוברים, וחיבור ב־DEV. יש להודיע כשבוצע.
לאחר מכן קוראים קודם את השחזור דרך ה־FSBL; אין להיכנס אוטומטית ל־B/v11 הישנה.

נוסף [Tools/read_xip_recovery.py](../Tools/read_xip_recovery.py). ברירת המחדל
מבצעת בדיקות host בלבד. הפעלה עם `--execute` מחייבת lease משותף מתאים,
בראנץ feature מדויק, hash של FSBL, ארבעה symbols וקריאת DEV ROM לפני load.
הבקר משתמש ב־GDB/MI אינטראקטיבי, מכיוון ש־GDB המותקן אינו כולל Python.
הוא עוצר לפני boot selection, מעביר PC ל־Secure Error_Handler לפני MapMemory,
קורא NOR פעמיים לשמות חדשים, מאמת את החזרה ללולאה לפני detach ומבקש
disconnect לפני סגירת GDB במקרה שגיאה. אם קישור הדיבאג מת, גם פעולת ההחזרה
ללולאה עלולה להיכשל; מצב הלוח במקרה כזה מדווח כלא ידוע, ללא הבטחת שחזור.

תשע בדיקות host עברו, לרבות כשל symbol, כשל dump, מצב CPU לא מתאים,
החזרה ללולאה שלא אומתה, פירוש כתובת PC עם שם symbol, שתי קריאות מלאות,
דחיית hash/ELF לא מתאימים ושגיאה מול GDB האמיתי שאינה סוגרת MI.
גם preflight על ה־FSBL המדויק עבר. הבקר עדיין לא נבדק על הלוח.
שני גיבויי ה־4MiB המקוריים נבדקו שוב ונשארו זהים ל־SHA256 המתועד.

[מאמר ST על דיבאג XIP](https://community.st.com/stm32-mcus-60/how-to-debug-stm32n6-using-stm32cubeide-151187)
מתאר תקלה ב־DeInit של loader מסוג stldr שדורשת power cycle.
לא הופעל external loader בניסיון ה־attach הזה, ולכן הקשר הסיבתי למקרה שלנו
לא הוכח ואין כאן תיקון מוכח לתקלה ההיא.
לפי [תיעוד GDB/MI](https://sourceware.org/gdb/current/onlinedocs/gdb.html/GDB_002fMI-Target-Manipulation.html),
detach בדרך כלל מחדש ריצה; disconnect בדרך כלל אינו מחדש אותה. נדרשת עדיין
מדידת התנהגות הפרוב והלוח האלה. לא בוצעו debug unlock או שינוי הרשאות.

## ארכיון — עדכון אחרי חיבור המתח ב־12:45 UTC

החיבור המלא אושר ונמדדו ROM PC=`0x18003514` ו־BOOTSR=2. ה־FSBL קרא
רשומת TRIAL מספר29, ביצע rollback ואימת בפועל את חתימת B/v11 ואת ה־hash
שלו. זהו rollback שנצפה בחומרה, אך dump עצמאי של רשומת התוצאה עדיין חסר.

סקריפט הבדיקה טען symbols של האפליקציה במקום של ה־FSBL, ולכן קריאת
`MapMemory` נעצרה לפני ה־dump. ניתוק דיבאגר בהמשך חידש את B/v11 הישנה.
נצפו אתחול ToF ורדיו וניסיון שחזור Wi-Fi. אין מדידה מספקת כדי להבטיח שלא
הופעלו setters של ה־NCP או שלא היו העלאות Cloud בחלון הזה; לא נשלחו פקודות
pairing, credentials או איסוף תמונות. גרסת RAM המוגנת החדשה לא הוחזרה עדיין.

לאחר מכן AP1 איבד גישה גם בלי כתיבת AIRCR חדשה. AP0 עדיין מזהה device486,
revZ ומתח3.28V. ניסיונות hot-plug בתדר1MHz ו־HWRSTPULSE לא החזירו את AP1;
גם אחרי ש־CubeProgrammer דיווח `Hard reset is performed`, נותר error32.
קריאות BOOTSR/DBGMCU דרך AP0 נכשלו, וקריאת UART פסיבית8שניות הייתה ריקה.
סיבת התקלה עדיין לא הוכחה. אין כאן ראיה לתקלה ייחודית ב־XIP או ב־OTA.

השלב הפיזי הבא הוא לחיצה אחת על RESET בלוח, עדיין ב־DEV, כדי לברר האם
נתיב NRST של הפרוב אכן מאפס את המעבד. נדרשת הודעת ביצוע לפני חידוש probes.
אין לבצע כרגע עוד כתיבת slot, שרשרת אתחול, OTP או שינוי הרשאות.

הוכן בלבד `recovery_inspect_next.py` בתיקיית הראיות המקומית. הוא בודק מראש
ארבעה symbols ב־FSBL, עוצר לפני `Firmware_Boot_Prepare`, מעביר PC ללולאת
`Error_Handler` לפני קריאות memory mapped, וקורא גיבויים בשמות חדשים.
כך כשל קריאה לא אמור להמשיך לגרסה הישנה. בדיקת syntax ו־symbols עברה;
הסקריפט עדיין לא הורץ על הלוח.

לא הייתה כתיבת image נוספת בסבב הזה. הוכחת USB A/v12 ו־PC מתוך Flash מהסבב
הקודם נשמרות; ריצה מלאה ב־XIP, boot confirmation, עדכון מתוך XIP, OTA,
אתחול מתמשך ובדיקות חבילות פגומות/העברה מופרעת עדיין חסרים.

## ארכיון — עדכון חומרה — הקבלה עדיין חלקית

ה־checkpoint הראשוני בהמשך מתאר את המצב לפני חיבור הכבל מחדש. מאז התקדם:

- גישה ל־ROM ו־BOOTSR=2 (DEV) אומתה. שתי קריאות NOR של4 MiB זהות; SHA256
  `cb3d9e4ffee29d832c7ca0cb516f06232dba2c4c5598e77fd6c81ce7feb9f05a`.
  שני CRCs תקינים וחתימות/hash של B/v11 המאושר ו־A/v10 הקודם אומתו עצמאית.
  ELF השחזור המקורי גם נטען מחדש והוכיח USB/ToF/NPU ורדיו תקינים.
- הותקן ב־RAM runtime תואם ויישום התקנה עם heap369136, config-preserve1,
  settings-writes0 ו־Cloud auto-map0. Wi-Fi קיבל IP וה־pairing הקיים נשמר;
  destinationNONE, datasetoff, ToFsent0. בדיקת C של auto-map0/1 עברה בשני modes.
- **כן בוצעה כתיבת Flash מורשית:** נתיב USB/XMODEM המקורי העביר498336 בתים של
  `N6-XIP-A-v12.n6fw`, SHA256
  `6861ba66f5222043683f76730c3dd502b01200cc6d152b306d1a3a79f8b66f24`.
  Secure אימת וכתב רק inactive A ו־metadata חלופי, וסיים finalization בהצלחה.
  B/v11 ו־FSBL/Secure ב־NOR לא תוכנתו. זה עדיין אינו אישור boot/confirmation.
- FSBL/Secure תואמים נטענו ל־RAM וה־trial הגיע ל־NS main עם
  **PC0x70191588, LR0x701A1817, SP0x24200000**. UART הוכיח את רצף ה־startup,
  vector0x70180400 ו־`no NS code copy`. זו הוכחת XIP אמיתית עד תחילת main;
  אין עדיין קבלת יישום מלא, tensors/100-frame NPU, heap runtime או cache/MPU
  readback. קריאות SCS דרך debug alias החזירו0 והן מסומנות inconclusive.
- בוצע GDB AIRCR reset יזום לפני confirmation. ניסיון rollback הבא לא התחיל:
  ST-LINK חזר לשגיאה32 גם ב־connect-under-reset. אין להסיק שזהו כשל של reset
  ב־production/OTA: זהו מסלול בדיקה שונה והסיבה אינה מוכחת. המצב האחרון שאומת
  הוא trial של A12 עם B11 מאושר שנשמר; מצב הריצה אחרי reset אינו ידוע.
- כל ידיות החומרה וה־lease שוחררו. נדרשת הודעה מפורשת שכל מקורות המתח נותקו,
  כולל ST-LINK/CN8/מתח חיצוני אם קיימים, וחוברו שוב ב־DEV. עד אז אין probes
  נוספים. אין דחיית automatic approval review בסבב הזה.

אחרי החיבור יש קודם להריץ את ה־FSBL החדש ב־RAM ולוודא rollback וכניסה ל־B11
לפני קוד תצורה; אין להשתמש ב־FSBL הישן כדי לבחון XIP pending. אחר כך אפשר
לחזור ליישום ההתקנה ב־RAM ולנסות שוב **אותה חבילת A12 בדיוק**, שעדיין לא אושרה
כגרסה released, או לבחור גרסה גבוהה חדשה באופן מפורש. יש לבדוק XIP מלא ואישור,
להתקין boot chain תואם רק אחרי אימות recovery, ולעבור פיזית ל־external boot
לבדיקת reset מתמשך. OTA אמיתי ל־B הבא ובדיקות עדכון תוך כדי XIP עדיין NOT RUN.
יש לבחור slot לפי metadata טרי: לפני הכתיבה הראשונה B/v11 היה המאושר, ולכן
ה־builds המוקדמים B12/A13 מתאימים לבדיקה סטטית בלבד ולא היו סדר ההתקנה הנכון.

ה־artifacts שבשימוש נמצאים ב־`.local-dependencies/xip/v12-A-no-export` וב־
`v13-B-no-export`; ה־RAM companion נשמר כ־ram.elf/bin/map. כל hashes של1080
קובצי המקור האפקטיביים בשתי הבניות אומתו מול הקוד שנשמר ב־8f74056c. ה־heap
התואם הוא369136 מול862256 ב־XIP, כלומר493120 בתים סטטיים פנויים יותר. הפעלת
instruction cache נמצאת כעת ב־Secure handoff, בלי תוספת לקוד startup של RAM.
ברירת המחדל של דמו ישן נשארה auto-map1; רק builder ה־XIP משתמש ב־auto-map0.
ה־lease החדש משתמש ב־Git common directory כדי לחלוק בעלות עם ה־checkout
המקורי, ו־`--scope xip-update` מתעד כתיבות NOR מורשות; אין בכך הרשאת OTP/credentials.

הדוח הנוכחי הוא [results](xip-ota-usb-20261022-results.json). הדוח הישן נשמר
בנפרד כ־[initial results](xip-ota-usb-20261022-initial-results.json); הטבלאות
והמספרים בהמשך הם תיעוד של שלב הבנייה הראשוני, ולא מצב החומרה הנוכחי.


## מצב אמיתי

העבודה נמצאת רק ב־`feature/n6-xip-ota-usb`, ב־worktree
`C:/Users/netan/Dropbox/DevelopPersonal/N6/n6-xip-ota-usb`, שנוצר מ־
`80f2b511029be6d87f9e72c32b00515457671f89` לאחר אימות `origin/main` ברשת.
ה־checkout המקורי נשאר ב־main וקובץ התוכנית הלא־מנוהל של המשתמש לא השתנה.
אין merge, push או deployment. זהו מימוש שנבנה ונבדק במחשב; **עדיין לא התקנת
XIP מאומתת על הלוח ולא קבלת USB/OTA על חומרה**. אין צורך ב־Generate Code.

| שלב | תוצאה |
|---|---|
| baseline, בעלות וגיבוי artifacts | PASS; אינו גיבוי NOR |
| שלושת ההקשרים ובניית XIP-A / XIP-B | PASS; ELF/BIN/MAP וחבילות חתומות |
| הוכחת כתובות מתוך ELF/map | PASS סטטי בלבד |
| PC בפלאש, ToF/NPU/USB/BLE לאחר XIP | BLOCKED; טרם נמדד |
| USB: העברה, boot ואישור על חומרה | NOT RUN |
| OTA: העברה דרך השרת הקיים, boot ואישור | NOT RUN |
| corruption / partial metadata / rollback | PASS בסימולציית C; חומרה NOT RUN |
| reset מתמשך / ניתוק מתח אמיתי | NOT RUN |

בתחילת העבודה COM8 דיווח גרסה11, ToF מתקדם, NPU174005 ריצות/0 שגיאות,
BLE מנותק ומפרסם, Wi-Fi ללא חיבור ו־Cloud paired אך ללא בקשות/תמונות.
בהמשך קריאת register דרך ST-LINK נכשלה, COM8 נתקע בפתיחה, וגם GDB attach
נכשל. ניסיון גיבוי נתמך דרך external loader **ביצע reset** אך נכשל ב־Data read
failed. גיבוי NOR מלא לא נוצר. ניסיון טעינת הדמו המוגן נכשל בחיבור ST-LINK
לפני GDB/download. מצב הריצה הנוכחי **אינו מאומת**; אין להציג את דמו ה־RAM
הקודם כאילו הוא עדיין רץ. לא נשלחו פקודות מחיקת/תכנות מערך NOR או OTP.
כל תהליכי הבדיקה שבבעלותנו וידיות החומרה נסגרו וה־lease שוחרר.
נדרשת הודעה מפורשת שהלוח נותק מכל מקורות המתח וחובר במצב DEV לפני ניסיון נוסף.
אלו שגיאות חיבור בפועל, לא דחייה של automatic approval review.

## מה רץ היכן

BootROM וה־FSBL עדיין זקוקים ל־RAM. ה־Secure runtime, שירותי האימות/כתיבה,
הפסיקות שלהם, ה־stack והנתונים שלהם נשארים ב־SRAM1. קוד היישום הלא־מאובטח,
טבלת הפסיקות, constants ו־initializer של המשקולות עוברים ל־NOR. `.data`
מועתק ב־startup מ־Flash ל־SRAM2; `.bss`, heap, stacks ו־DMA buffers נשארים RAM.
ה־linker מאפשר גם `.RamFunc` ב־`.data` אם תידרש שגרה כזאת. זהו XIP של היישום,
לא הבטחה לפעולה ללא RAM. בבנייה הנוכחית שירות הכתיבה המכריע כבר Secure/RAM.

מפת הפלאש הקיימת נשמרת:

| אזור | כתובת | תפקיד |
|---|---|---|
| FSBL | `0x70000000` | ROM loads into RAM |
| Secure | `0x70100000` | FSBL loads into SRAM1 |
| A | `0x70180000`, 1 MiB | vectors at `0x70180400` |
| B | `0x70280000`, 1 MiB | vectors at `0x70280400` |
| metadata 0/1 | `0x703E0000` / `0x703F0000` | שני erase sectors עצמאיים |

אין remap מדומה או relocation של בינארי ARM. בונים שתי תמונות לכתובות פיזיות
שונות. `manifest.flags`, הכלול בחתימת ECDSA, מציין RAM=0, XIP-A=1 או XIP-B=2.
ה־Secure Begin דוחה package של ה־slot הלא נכון לפני erase, וה־FSBL בודק את
אותו חוזה. שרשרת boot ישנה דוחה flags שאינם0; לכן נדרשת התקנת FSBL+Secure
תואמים, עם גיבוי ושחזור מוכחים, לפני תמונת XIP ראשונה. אין להעלות חבילת XIP
ללוח הישן ולצפות שהתקנת boot-chain תקרה מעצמה.

ה־FSBL מאמת manifest/hash/vectors, מעתיק את Secure, ומוסר ל־Secure רק שני
vector words של XIP דרך אזור ה־handoff הקיים ב־SRAM2. הוא אינו מעתיק את קוד
ה־NS. Secure שומר את ה־vectors לפני שה־startup משתמש ב־SRAM2, פותח SAU רק
ל־slot הפעיל, ומגדיר MPU לקריאה/הרצה בו. RISAF12 מגן על חלון ה־XSPI2 בשלושה
אזורים שאינם חופפים: prefix Secure, ה־slot הפעיל NS לקריאה בלבד, ו־suffix
Secure. הגדרות אלה volatile, ללא fuse או lock. XSPI2/XSPIM וה־slot השני אינם נפתחים
ב־SAU. ה־Secure handoff מפעיל את instruction cache של ה־NS; מדיניות data cache הקיימת נשמרת.
בדיקת SAU/MPU/RIF/attributes בפועל ו־PC sampling עדיין נדרשות על חומרה.

## כתיבה כשהקוד נמצא באותו שבב NOR

מעטפת NSC רצה ב־Secure SRAM. היא שומרת וממסכת `PRIMASK_NS`, משאירה Secure
SysTick פועל כדי ש־HAL timeouts יתקדמו, ומסיימת cache/barrier לפני הסרת המיפוי.
היא דוחה DMA פעיל שהמקור/יעד שלו בזיכרון חיצוני או שיש לו linked list,
וכן דוחה קונפיגורציה שמעבירה HardFault/NMI ל־NS. הכתיבה וה־readback מתבצעים
ב־indirect mode; המיפוי ו־cache חוזרים **לפני** שחזור הפסיקות וחזרה ל־NS.
אם אי אפשר להחזיר מיפוי, היא נשארת ב־Secure במקום לחזור לקוד שלא ניתן לקרוא.
זה מחייב שחזור ST-LINK/ROM; אין כאן watchdog חדש או הבטחה להתאוששות אוטומטית.

במודל הנוכחי המשקולות וה־NPU activations נמצאים ב־SRAM5/6; קוד ניהול epochs
רץ על ה־CPU. מודל עתידי שקורא משקולות/command blobs ישירות מה־NOR מחייב מדיניות
עצירה והוכחת quiescence נוספת. אין להניח שבדיקת GPDMA לבדה מגינה על כל AXI
master עתידי. גם משכי erase, אובדן IRQ events/backpressure, DMA פעיל, cache
ו־USB/Radio בזמן כתיבה טרם אומתו על הלוח. אלה תנאי קבלה לפני שימוש אמיתי.

השירות הקיים כותב רק ל־slot הלא פעיל; hash של הזרם, readback, מבנה וחתימה
קודמים ל־PENDING. CRC ושני metadata sectors משמרים record ישן עד commit חדש.
FSBL כותב TRIAL לפני jump. reset לפני confirm מחזיר לתמונה המאושרת, ו־confirm
שומר את הקודמת כ־fallback. reset/power loss באמצע כתיבת ה־slot משאיר את metadata
המאושר. ההוכחות החדשות לכך הן host simulation בלבד, לא ניסויי ניתוק מתח.
חלון האישור הקיים אחרי5 שניות נשמר: הוא אינו אישור בריאות לכל peripherals,
ואינו watchdog שמאתחל יישום תקוע. עדיין נדרשת בדיקת התאמת מדיניות זו ל־XIP.

## מדידת RAM והמשמעות למודל גדול

המדידות הבאות הן ממפות linker של אותו קוד guarded, אותו מודל ואותם stack sizes:

| פריט | RAM companion | XIP |
|---|---:|---:|
| heap start | `0x241A5690` | `0x2412CFD0` |
| stack limit | `0x241FF800` | `0x241FF800` |
| קיבולת C heap | 369008 | 862256 בתים |
| `.text` | 344592 | 344592 בתים ב־Flash |
| `.rodata` | 147772 | 147772 בתים ב־Flash |
| `.data` | 3920 | 3920 בתים ב־RAM; initializers ב־Flash |
| `.bss` | 179308 | 179308 בתים ב־RAM |

ההפרש התואם הוא493248 בתים (כ־481.69 KiB). מול דמו ה־RAM השמור, heap369136,
השיפור הסטטי הוא493120. ה־companion החדש אינו תחליף מאושר לדמו השמור: הוא
מתחת לסף M6 המוגן369072, אף שהוא מעל סף הלינק הכללי368640. לא נטען אותו
במקום ELF השחזור המקורי. ה־XIP עצמו מעל שני הספים. אין כאן malloc fragmentation
או stack high-water חדש, מבחן עומס, או הוכחת שיפור יציבות על חומרה.

SRAM3 workspace נשאר180224 בתים; SRAM4 של היישום150656 ושל הרדיו65536 בתים.
המודל הנוכחי עדיין מקבל3200 בתים uint8 (`1x50x64x1`) ומחזיר4 בתים int8.
ה־generated activation pool ב־SRAM5 הוא17408 בתים לפי תיאור ה־network;
אין לפרש את רשימת virtual pools כאילו כל הקיבולת שלהם הוקצתה. המשקולות הן
55425 בתים: initializer משולב בחבילה ועכשיו ב־NOR, ועותק עבודה עדיין ב־SRAM6
ב־`0x24350000`. קיבולת הבנק היא448 KiB, לא כל ה־RAM שהתפנה ל־CPU.

פינוי SRAM2 נותן מיד מרווח גדול יותר ל־VL53L9 ול־CPU heap. כדי להשתמש בחלק ממנו
כ־NPU scratch צריך לשנות במכוון את descriptor/pool של STEdgeAI, להחריג אזור
מה־CPU linker/heap, לשמר גישה של NPU ו־cache coherence, לייצר מחדש ולבדוק
Stage11. אין לספור את אותו אזור גם כ־heap וגם כ־activation pool.
מגבלת `maximum_embedded_weight_bytes` של TRAINING עדיין64 KiB; היא לא הוגדלה
כדי להעביר בדיקה. מסלול Stage10 הקיים הוא RAM, ולכן הגדלת התקציב עבור XIP
דורשת גם חיבור stages10–12 לבנייה ול־HIL של XIP, ולא שינוי מספר לבדו.
אין כרגע הוכחת דיוק או ריצה למודל גדול יותר.

## כל שדה העומק לעומת RPS

היישום מפיק grid עומק54×42. RPS מבצע בתוכנה בחירת connected component קרוב,
חיתוך/נרמול יחסיים, שינוי גודל וסף silhouette. אין בקוד הזה הוכחה ל־autofocus
אופטי או שינוי פוקוס של עדשת החיישן. יש להבחין בין grid העומק המעובד לבין
כל הגלאים/הערוצים הפנימיים של החיישן; לא הורחבה רזולוציית חומרה.

כבר קיים `spatial_depth_v1`: `spatial_depth_profile.h` וה־Python המקביל לוקחים
את כל54×42, ממפים nearest-neighbour ל־64×50, שומרים מקום וטווח מוחלט,
מסמנים invalid=0 ומכמתים valid ל־1..255 בטווח המוגדר. אין בו בחירת אובייקט,
crop או dilation. השוואת C/Python הנוכחית עברה byte-for-byte גם ל־invalid,
מיקום וטווח; בדיקת contract עברה. הקבלה הקודמת של spatial2 על100 NPU frames
מ־2026-10-21 נשארת היסטורית ומסומנת כך; לא הורץ כאן HIL חדש למודל הזה.

בחירת profile קשורה לפרויקט, dataset, model contract ו־headers שנוצרים ב־stages
04–08. shape/quantization נשארים `1x50x64x1`, uint8 scale1/zero0; החלפת קלט
למודל RPS שכבר אומן תהיה שגויה. שימוש native54×42 או תמונה גדולה יותר מחייב
שינוי חוזה, pipeline האימון/כימות/יצירה, assertions ו־workspace/HIL. בענף זה
לא הוחלף המודל, לא שונו dataset/labels ולא נאספו או הועלו דגימות חדשות.

## בנייה ובדיקה ללא לוח

מתוך ה־worktree בלבד:

```powershell
git branch --show-current  # חייב להיות feature/n6-xip-ota-usb
.\Tools\Build-Xip.ps1 -Slot B -FirmwareVersion 12 -Label candidate1
.\Tools\Test-XipPackage.ps1 -Package .local-dependencies\xip\v12-B-candidate1\N6-XIP-B-v12.n6fw -ExpectedSlot B -ExpectedVersion 12
```

אלו פקודות build/package בלבד. ה־builder משתמש ב־IDE workspace פרטי, בונה את
שלושת ההקשרים, שומר artifacts חתומים תואמים של FSBL/Secure/NS, מקשר ל־slot
הנבחר, משמר NCP config ומכבה settings writes. הוא משחזר headers ו־IDE settings
ב־finally. `build.json` מכיל hashes של ה־sources האפקטיביים, כולל version/config
זמניים ששונים מברירות המחדל המשוחזרות, וכן hashes של artifacts ותקציבי map.
הוא אינו פותח COM, כותב Flash, מאתחל את הלוח או יוצר key חדש.
מספרי12/13 כאן הם candidates שלא הותקנו; לפני שימוש יש לאמת את הגרסה המאושרת
ב־metadata ואת המספור הפנוי. אין להניח שהגרסה שהוצגה מ־RAM היא גרסת NOR.

המשדר המקורי ב־`Tools/Send-Xmodem.ps1` נותר נתיב USB. ה־Cloud UI הקיים משתמש
באותו signed byte stream ו־XMODEM; `validateN6Package` והשרת אינם צריכים שינוי
עבור flags1/2. נבדקה סימולציה מלאה עם החבילה האמיתית על מקור השרת ב־5905a7d;
לא בוצע deployment ולא הועבר byte של firmware או sensor לשרת בפועל.
אין להשתמש ב־`Install-NonSecureUpdate.ps1` כדי לבנות XIP: הוא עדיין בונה RAM.
אחרי מעבר XIP אין להתייחס גם ל־Stage12 RAM HIL כאל אישור לחבילת XIP.

## המשך בטוח לאחר חזרת החומרה

1. לקבל אישור מפורש על חיבור מחדש ב־DEV (`BOOT0=1-2`, `BOOT1=2-3`), לבדוק שאין
   בעלות אחרת, ולרכוש lease משותף. ה־lease הקיים מוגדר RAM-only; בדיקות NOR
   יצטרכו scope מתועד מתאים, בלי לעקוף marker או לקחת lease זר.
2. לשחזר קודם את הדמו המוגן מהעותקים המדויקים בתיקיית recovery. אין להריץ
   `Debug-NonSecureRam -NoBuild` עם Debug אקראי: יש להציב רק את FSBL/Secure
   המקוריים ואת `candidate.elf/.bin/.map` השמורים ולהחזיר outputs לאחר מכן,
   כפי שמתועד בניסיון השחזור וה־hashes. להוכיח ToF/NPU, no Cloud images,
   BLE disconnected, settings writes0, וסגירת הידיות.
3. ליצור גיבוי NOR אמיתי של FSBL+Secure+שני slots+שני metadata sectors, לבצע
   קריאה נוספת והשוואת hashes, לאמת headers/manifest/CRC ולזהות confirmed slot.
   העותק של ELF אינו מחליף זאת. צריך גם להוכיח שאפשר לטעון את recovery דרך
   ROM/ST-LINK לאחר reset. **אין NOR write ראשון לפני הבדיקות האלו.**
4. לבדוק שה־slot שנבחר ל־XIP אינו confirmed. לשמור אותו ואת config/credentials.
   להתקין רק boot chain תואם חתום; לא להפעיל `program_flash.ps1` בלי mode,
   `Factory-Provision`, full erase או כתיבת factory metadata. אין OTP/fuse/locks,
   Windows Pair/cache changes או הרחבת הרשאות credentials.
5. לבצע bring-up מבוקר: PC samples מתוך `.text` ב־slot, `VTOR_NS`, vectors,
   MPU/SAU/RIF/cache ו־map תואם. להוכיח ש־NS code אינו מועתק ל־SRAM2. למדוד heap,
   stacks, ToF,100 NPU frames והשוואה מספרית, USB/BLE ללא exports מיותרים.
6. לבדוק USB ו־OTA בנפרד, כל אחד בחבילה ל־slot הלא פעיל וגרסה חדשה: אותן bytes,
   authenticated finalization, trial, confirmation, version/model, והמשך אחרי reset.
   לבדוק כתיבה בזמן ביצוע XIP, גם B→A וגם A→B, חבילה פגומה, interrupt/cancel
   בטוח ו־reset-before-confirm. לא להציג ACK ל־EOT כהוכחת boot.
7. persistent boot דורש BOOT0/BOOT1 במצב external Flash (`1-2`/`1-2`). DEV חוזר
   ל־ROM אחרי reset ואינו מבחן reboot מתמשך. לתעד את מעבר הג'מפר הפיזי ואת
   power-cycle האמיתי; לא להמציא בדיקה תוכנתית במקומם. כל הזרמה של תמונות
   לענן נשארת כבויה; OTA מורשה דרך השרת הקיים אינו אישור ל־sensor uploads.

## דוח הקבלה השמור

הדוח [xip-ota-usb-20261022-results.json](xip-ota-usb-20261022-results.json) מכיל
את commit הקוד המדויק, hashes של שני ה־builds בתיקיות `*-checked`, ה־budgets,
תוצאות כל בדיקה והפרדה מפורשת בין host ל־HIL. כל hashes של artifacts ושל
מקורות הבנייה האפקטיביים אומתו שוב, ו־ordinary Debug המקורי זהה ל־hashes
השמורים מהקבלה הקודמת. artifacts ביניים נשמרו לצורך בירור ואינם יעד התקנה.

עברו21 מקרי vectors/boot בקוד C בפועל וחמש קבוצות תרחישי Secure נוספים עם
NOR/PKA/CMSE/HAL מדומים;9 בדיקות חבילה,8 בדיקות Cloud קיימות, העברת החבילה
האמיתית במשדר Cloud מדומה ב־487 בלוקים,5 בדיקות drain, בדיקות spatial ו־contract,
ו־72 תגובות version מפוצלות. גם חסימת build מקביל אומתה לפני שינוי headers.
בדיקת boot-chain הישנה עברה את חמשת assertions, אך cleanup נכשל בשתי הרצות
בגלל directory handle נעול בתוך Dropbox. הכישלונות נשמרו. העברת fixture זמני
ל־system TEMP, ללא שינוי assertions, החזירה process exit0; זו התאמת harness,
לא שינוי firmware או הסתרת כישלון חומרה.

## מקורות רשמיים

נבדקו תבנית ST [Template_FSBL_XIP](https://github.com/STMicroelectronics/STM32CubeN6/blob/main/Projects/NUCLEO-N657X0-Q/Templates/Template_FSBL_XIP/README.md)
והמקור המקומי של STM32CubeN6 V1.4.0. תבנית
[Template_Isolation_XIP](https://github.com/STMicroelectronics/STM32CubeN6/blob/main/Projects/NUCLEO-N657X0-Q/Templates/Template_Isolation_XIP/README.md)
מאשרת ש־RISAF12 מגן על חלון ה־XSPI2; מזה נלקח שיוך החומרה, תוך התאמה
ל־Secure runtime ב־RAM ול־slot הפעיל בלבד. התבנית מזהירה מפני VDDIO3_HSLV OTP בלתי
הפיך; `OTP_Config` שלה לא הועתק ולא הופעל. קצב/מצב XSPI של הפרויקט נשמרו.
ראו גם [AN5050](https://www.st.com/resource/en/application_note/an5050-getting-started-with-octospi-hexadecaspi-and-xspi-interfaces-on-stm32-mcus-stmicroelectronics.pdf)
ל־memory mapped access ו־bus masters. סקירת מקור אינה תחליף למדידה על לוח זה.
