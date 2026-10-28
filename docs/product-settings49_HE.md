# גרסת בדיקות ידניות A49 — הגדרות מתמידות

תאריך: 2026-10-27. ענף: `feature/n6-xip-ota-usb`.
הבקשה הנוכחית מאפשרת שמירת הגדרות כחלק משימוש רגיל במוצר.

## מה השתנה

- `APP_SETTINGS_WRITES_ENABLED=1` ו־`APP_SETTINGS_TRANSITION_ENABLED=1` כברירת מחדל.
- גם `Build-Xip.ps1` דורש פרופיל זה ומתעד אותו במניפסט.
- כתיבה אינה ננעלת אחרי הצימוד הראשון או אחרי טעינה מחדש. חיבור Wi-Fi מוצלח שומר הגדרות; ניתוק מכוון מעדכן את כוונת החיבור; שינוי מצב Cloud וניתוק צימוד נשמרים.
- `status` מציג במפורש Wi-Fi CONNECTED, מוכנות IPv4, מצב מאגר ההגדרות, יכולת כתיבה, דור שמירה וכוונת חיבור אוטומטי. אין הצגת סיסמה או token.
- `cloud stats` נתמך כשם נוסף ל־`cloud status`; סירוב מקומי לצימוד מציג גם מצב הגדרות וקוד סטטוס. הודעת queued אינה הוכחת צימוד.
- מסלול legacy נשאר מפורש: כאשר מוצג legacy, יש להשתמש ב־`cloud prepare yes` ב־USB עם חיבור Wi-Fi שמור ומאומת, לבדוק `cloud status` ואז לבצע צימוד בקוד חדש. ההכנה נשמרת ב־RAM בלבד; הקובץ הישן אינו נמחק. מצב corrupt/I/O/unsupported אינו מקבל מעקף.

## בדיקות שבוצעו

בדיקות C אמיתי עם מדיה מדומה: adapter, מעבר legacy בארבעה שילובי מדיניות, בעלות Cloud/Wi-Fi, טעינה מחדש ו־15 נקודות הפסקת כתיבה, בקרת Cloud, scope ו־store.
בדיקת המעבר כוללת כעת כתיבה נוספת אחרי צימוד, טעינה מחדש, ניתוק Wi-Fi, החלפת רשת ומחיקת צימוד תוך שימור שדות Wi-Fi.
כישלון כתיבה או תוצאת כתיבה לא ידועה עדיין מחייבים טעינה וארביטרציה; אין ניסיון כתיבה עיוור נוסף.

FSBL, Secure ו־NonSecure נבנו. חבילת XIP-A49 חתומה ואומתה:
`.local-dependencies/xip/v49-A-product-settings/N6-XIP-A-v49.n6fw`.
גודל 483200 bytes; heap בפרופיל RAM: 397776; בפרופיל XIP: 852528.
ניסיון ראשון נעצר ב־COM8 Access denied לפני כתיבה. לאחר שהמשתמש פינה את הפורטים, A49 הותקנה פעם אחת ב־CDC OTA: חתימה אומתה, EOT אושר ואירע אתחול אוטומטי. Secure אישר גרסה 49 בבדיקת header-only ללא כתיבת תמונה נוספת. B48 נשמר כגיבוי.

HIL100 עבר: 100 טנסורים מדויקים, 100 תוצאות NPU, maxdelta0, CRC0, משך26.219s. שלושת הלוגואים ללא מחיקת מסך נשמרו. הפקודות status ו־cloud stats נבדקו בפועל: Settings empty, writes enabled; Wi-Fi/IP אינם מחוברים. ToF/NPU תקינים וזרם dataset כבוי בסיום. אין עדיין הוכחת שמירת סיסמה או צימוד אמיתי על החומרה.

ראיות: `.local-dependencies/xip/product-settings49/`,
`.local-dependencies/xip/hil-XIP-v49-product-settings49.json`,
ופלט אישור Secure בתיקיית בדיקת `product-settings49-confirmed`.

## סדר בדיקה ידנית לאחר ההתקנה

1. `version` חייב להראות 49; `status` ו־`cloud stats` חייבים להציג מידע מלא.
2. להתחבר ל־Wi-Fi באמצעות ההנחיה לסיסמה מוסתרת. לא להעביר סיסמה בצ׳אט או בלוג.
3. להמתין לתוצאת החיבור, לוודא CONNECTED=YES ו־IPv4 ready=YES; לבדוק Settings ready, Wi-Fi saved yes, autoconnect yes.
4. לאתחל ולוודא חיבור מחדש ללא הזנת סיסמה.
5. לצמד עם קוד טרי מהאתר; לבדוק paired ו־Cloud saved yes, ולא רק queued.
6. לאתחל ולוודא שהצימוד נשמר. לבדוק disable/enable ואת הישארות הבחירה אחרי אתחול.
7. לבדוק ToF/NPU וזרימת האתר במקביל לחיבור, וכן את נתיבי USB ו־BLE שבמדריך.

## פערים גלויים מול מוצר סופי

- Cloud נשאר כרגע בפרופיל HTTP של המעבדה. קיימת בעיית TLS מול השרת המתועדת ב־`st67-t01-tls-interoperability-fae.md`. אין כאן אישור מוכנות להפצה או העברת פרטי צימוד מאובטחת.
- שגיאת Wi-Fi ERROR(2) שדווחה היא שגיאה כללית; סריקה מוצלחת אינה מוכיחה חיבור לרשת. שורש התקלה לא אומת עדיין על החומרה.
- תצוגת GC9A01 נשארת כבויה לפי הגדרת הפרויקט הקיימת; ניתוב תמונה אוטומטי לאחר pairing כבוי ב־XIP. ניתן להפעיל זרם ידנית. Radio, Wi-Fi, BLE GATT, Cloud relay, USB CLI ו־NPU מופעלים; watchdog פעיל בבניית XIP.
- כלי guarded RAM ההיסטורי מיועד לפרופיל read-only ואינו מסלול התקנת המוצר; הוא ממשיך לסרב לטעינה של קושחה כותבת. אין לשנות את הגנותיו כדי לעקוף את פרופיל XIP.
- אין Generate Code לשינוי זה.

## אימות שמירת Wi-Fi בפועל

לאחר הזנת סיסמה מקומית על ידי המשתמש: Settings ready, generation1, Wi-Fi saved yes, autoconnect yes. בוצע reboot yes אחד דרך CDC. לאחר העלייה A49 התחברה אוטומטית ל־nati_sash וקיבלה 192.168.68.74 ללא הזנת סיסמה. דור ההגדרות נשאר1; בדיקת המשך אישרה שאין operation in progress, ו־ToF/NPU/SPI תקינים ללא שגיאות או התאוששויות. זו בדיקת אתחול תוכנה, לא ניתוק מתח. Cloud עדיין אינו מצומד; שמירת צימוד לא נבדקה.

ראיות: `.local-dependencies/xip/product-settings49/wifi-before-reboot.json`, `wifi-reboot-verification.json`, וכן `.local-dependencies/xip/status-settings49-wifi-reboot-final.json`.

## השלמת בדיקות עצמאית ומסירה לבדיקה ידנית

- סריקת Wi-Fi בזמן חיבור לרשת: PASS, כולל מציאת nati_sash ושימור חיבור/IP.
- בדיקת יציבות בת שתי דקות: 11 דגימות ו־55 פקודות USB עברו. זמן הריצה ומספרי הפריימים מתקדמים; דור ההגדרות נשאר1; ללא שגיאות SPI/NCP/NPU.
- HIL נוסף עם Wi-Fi פעיל: 100/100 טנסורים מדויקים, 100/100 תוצאות NPU, maxdelta0, CRC0, משך26.281s.
- BLE אמיתי: 5/5 פקודות PONG עברו, 94–109ms. פקודות help (2632 bytes), status ו־cloud stats עברו במלואן עם סיום תגובה תקין. לא בוצע OS pairing, וחיבור BLE נסגר.
- בריאות שרת מהמחשב: HTTPS GET /api/health החזיר200/status ok. זו אינה הוכחת TLS או העברת Cloud מהמודול. קושחה ללא צימוד אינה שולחת בקשות Cloud רגילות, גם כאשר מבקשים reconnect/test.
- בסיום: A49, Wi-Fi/IP מחוברים, הגדרות ready/saved/autoconnect, ToF/NPU תקינים; BLE מנותק ומפרסם, נתיב תמונה NONE ו־dataset כבוי. כל חיבורי הבדיקה נסגרו.

נשארו לבדיקה ידנית: צימוד בקוד חדש ושמירתו, זרימת Cloud/אתר בפועל, והפעלה לאחר ניתוק מתח. TLS נשאר פער להפצה; החיבור הנוכחי של הקושחה הוא HTTP של המעבדה. לא נדרשת עזרת המשתמש להשלמת הבדיקות המפורטות כ־PASS.

ראיות נוספות: connected-soak.json, ble-multiline.json ו־host-cloud-health.json בתוך תיקיית product-settings49; תוצאת BLE הראשונה נכשלה רק בשל סביבת Python ללא bleak לפני גישה לחומרה, ונשמרה. הרצה בסביבת הפרויקט עברה. נתוני HIL נשמרו ב־hil-XIP-v49-product-settings49-wifi-online.json; מצב המסירה ב־status-settings49-manual-handoff.json.
