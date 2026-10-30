# הפעלת לוגים מלאה — A57, ‏2026-10-29

הותקנה A57 ב־USB באמצעות החבילה החתומה והמתקין הקיים לתא הלא פעיל. B56 נשארה בתא השני. הקוד נשאר זהה ל־B56 פרט לשלושת קובצי האבחון ולמספר הגרסה הזמני בבנייה. לא נדרש Generate Code.

- `N6_DEBUG_OUTPUT_ENABLED=1` מפעיל UART, הודעות האפליקציה ולוגי ST67.
- `N6_CLI_DIAGNOSTICS_ENABLED=1` מחזיר אבחון פקודות CLI.
- `LOG_DEFAULT_LEVEL=LOG_DEBUG` מפעיל את כל רמות הלוג כבר באתחול.
- NCP trace מתחיל פעיל. `n` מכבה אותו; לחיצה נוספת מפעילה. הסינון הקיים של תוכן NCP נשמר.

הבנייה, הקישור, החתימה ואימות החבילה עברו. גודל החבילה514592 בתים, SHA256:
`43a12edf47edee1bf92f4a8279d492332f0b979b893805e8b6c9db4e6ac16e66`.
מקור: `.local-dependencies/xip/v57-A-full-diagnostics`.

העברת USB הסתיימה באימות מוצלח ובאתחול אוטומטי. הלוג תיעד `boot confirmed; rollback window closed` ב־17723ms. גרסה57 אומתה ב־USB. הודעות האתחול והאפליקציה נקלטו בפועל ב־COM6; `?`, `a`, `n` OFF ו־`n` ON נבדקו, ובסיום NCP trace נשאר ON. רמת DEBUG אומתה אחרי האתחול.

בדיקות native של CLI reply failure ו־radio service status וכן שלוש בדיקות USB disconnect עברו. HIL עם הלוגים פעילים עבר100/100 tensors מדויקים,100 חישובי NPU, סטיית ציון מרבית1, CRC0, במשך27.953s. המפענח רשם אירוע framing אחד סביב פתיחת זרם הטקסט/בינארי; אין טענה ל־framing0. זו בדיקה קצרה, לא הוכחת עמידות ממושכת או תיקון הבאגים הקיימים.

## מגבלות שנחשפו

בעומס DEBUG ו־NCP trace התור הקצוב משמיט הודעות: לפני בדיקת המקשים/HIL היו1058 השמטות, ובסיום1759 (תוספת701). queued=sent=5135 בסיום; transport/internal/timeouts/HAL/RX errors=0. כל סוגי הלוגים מופעלים, אך הקלטת כל הודעה אינה מובטחת. לא הוגדלו תורים ולא שונתה מדיניות התזמון כדי להסתיר את העומס. באתחול הופיעו גם הודעות `Wi-Fi result receive failed: 29`; הסיבה לא נחקרה במסגרת הפעלת הלוגים.

בסיום ToF ready, NPU errors0, dataset OFF, Cloud sensor sent0 והגדרות generation2 נשמרו. כל חיבורי COM וה־lease שוחררו. ניתן לפתוח את `training/DUAL_COM_DEBUG.bat`, לעבור עם ESC למצב UART ולראות את הלוגים. ב־Tera Term: ‏COM6, ‏115200, ‏8N1, ללא flow control. אין צורך לצרוב שוב או לשנות ג׳מפרים.

ראיות מקומיות:

- `.local-dependencies/xip/usb-update-full-diagnostics57/result.json`, `uart.log`, `sender.log`.
- `.local-dependencies/xip/full-diagnostics57-verification/result.json`, `uart.log`, `hil.log`.
- `.local-dependencies/xip/hil-XIP-v57-full-diagnostics57.json`.

## עדכון עיצוב לוגים וצבעי מסוף — 30 באוקטובר

בקוד החדש מנגנון `vLoggingPrintf` מנרמל את רשומת האבחון בתוך הבאפר שבבעלות
הכותב: שורות ריקות/רווחים בלבד מוסרות, ובין שורות נשמר CRLF יחיד. אין תוספת
באפר במחסנית או מצב משותף בין הכותבים. הסינון מוגבל לאבחוני ST67; תשובות CLI,
מעברי השורה שמסיימים פקודה ונתוני התעבורה הבינאריים אינם משתנים.

נמצא ותוקן גם גורם בצד המחשב: כאשר CR ו־LF התקבלו בשתי קריאות serial שונות,
`DUAL_COM_DEBUG` הציג שתי ירידות שורה. נשמר כעת מצב נפרד לכל ערוץ. בתחילת
ההפעלה הכלי מפעיל Windows VT עבור צבעי ANSI, בלי לשנות את מצב הקלט/ESC ובלי
להסיר צבעים מקובצי הלוג. אם ההפעלה אינה נתמכת מוצגת הודעה.

אימות: קוד C ממשי נבדק מול CR/LF/CRLF, שורות ריקות ורווחים, ANSI וגבולות510
גדלי באפר;11 בדיקות Python עברו, כולל כל נקודות הפיצול של CRLF וקוד צבע.
מסוף Windows PTY אמיתי החזיר TTY=True ו־VT=True והפיק ANSI לטקסט ולרקע.
זה אינו צילום או אימות חזותי של חלון המשתמש שכבר פתוח.

חבילת A59 נבנתה ונחתמה ב־`.local-dependencies/xip/v59-A-compact-uart-ansi`
והותקנה דרך USB לאחר אישור המשתמש שהחיבורים פנויים. Secure אישר את האתחול
ב־17823ms; B58 נשמרה בתא השני. החבילה514912bytes, SHA256
`dacabc4a2b289c2461eaf229a9d7640de605adaf3c3bb9c3cb69aafa11eacf87`.
אין צורך ב־Generate Code. חלון dual-COM קיים צריך להיפתח מחדש כדי לטעון את
שינויי Python.

אימות בפועל: בלכידת UART של20שניות התקבלו89051bytes,2223 שורות שלמות,
615 רשומות NCP, אפס שורות ריקות ואפס LF ללא CR. שתי שורות בקצוות הלכידה
אינן נספרות כי ייתכן שהן חלקיות. מפת USB אמיתית הפיקה5411 קודי צבע רקע
ANSI; לאחר הבדיקה הזרם כובה ונבדק requested/active NONE. בדיקת HIL עברה
100 tensors מדויקים ו־100 תוצאות NPU, הפרש score מרבי0 ו־CRC0. כל החיבורים
והנעילה שוחררו. זה אינו מבטיח שכל הודעות הלוג נלכדות בעומס DEBUG.

הניסיון הראשון נעצר לפני שליחת קושחה: נשאר יעד BLE ומונה Cloud היסטורי674.
הדמו הופסק וחיבור BLE נסגר בהכנה לעדכון המאושר. נתיב עדכון מפורש מאפשר כעת
מונה היסטורי שאינו אפס רק עם יעד NONE בשתי דגימות ומונה שלא עלה ביניהן;
ברירת המחדל עדיין דורשת אפס.4 בדיקות אימות לכך עברו. המונה לא אופס.
העברת הקושחה היחידה הושלמה ואושרה, אך בדיקת `rps status` מיד לאחר האתחול
נתקלה ב־timeout. תוצאת הניסיון נשמרה ככישלון; בדיקות מצב בחיבור חדש ו־HIL
עברו בלי צריבה חוזרת. סיבת ה־timeout נותרה לא מבוססת.

ראיות מקומיות נוספות:

- `.local-dependencies/xip/usb-update-compact-uart59/result.json` — העצירה לפני העברה.
- `.local-dependencies/xip/usb-update-compact-uart59-idle/` — העברה, אישור אתחול וה־timeout.
- `.local-dependencies/xip/compact-uart59-postflight.json` — מצב בחיבור חדש.
- `.local-dependencies/xip/hil-XIP-v59-compact-uart59-idle-verify.json`.
- `.local-dependencies/xip/compact-uart59-verification/` — UART גולמי, מפת USB וסיכום.
