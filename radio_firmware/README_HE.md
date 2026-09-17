# עדכון Firmware למודול ST67W611M1

התיקייה הזאת היא מסלול עצמאי ומונחה לעדכון ה־NCP שמספק BLE/Wi‑Fi על
`X-NUCLEO-67W61M1`. היא מקבילה ל־`training`: כל מה שנדרש לעדכון Windows
נמצא בתוך ה־repository, בלי תלות בעותק מקומי של חבילת X‑CUBE.

הגרסה שנדרשת על־ידי היישום היא profile ‏`mission T01`, ‏SDK ‏`2.0.106`.
T01 כולל את מחסנית הרשת בצד ה־NCP ומתאים לדרייבר שהפרויקט מקמפל.

## הפעלה קצרה

1. סגור terminals שמשתמשים ב־ST‑LINK Virtual COM Port.
2. הרץ `00_CHECK.bat`. הוא מאמת SHA‑256 לכל הקבצים הקריטיים.
3. הרץ `01_UPDATE_MODULE.bat`, הקלד `UPDATE ST67` ופעל לפי הוראות ה־jumpers.
4. אחרי העדכון הרץ `training\10_LOAD_RAM.bat` ואז `training\11_HIL.bat`.
   Stage 11 קורא `radio info`, דורש SDK ‏2.0.106, ובודק בפועל את פרסום ה־BLE.

הסקריפט מבצע את הרצף הבא:

1. במצב DEV ‏(`BOOT0=1-2`, ‏`BOOT1=2-3`) הוא שומר ב־Flash החיצוני host
   bootloader זמני ומאמת אותו.
2. במצב external Flash ‏(`BOOT0=1-2`, ‏`BOOT1=1-2`) הוא צורב את ה־ST67 דרך
   ה־ST‑LINK VCP בעזרת QConn. כישלון ראשון מקבל retry יחיד ומוגבל.
3. גם במקרה של כשל, בלוק `finally` מבקש לחזור ל־DEV ומנסה להחזיר ולאמת את
   ה־FSBL. אם `FlashImages/N6_FSBL-trusted.bin` קיים הוא מוחזר; אחרת מוחזר
   FSBL הייחוס של ST כדי שהלוח לא יישאר עם ה־host הזמני.

## מעגל חדש לחלוטין

במעגל חדש אין עדיין שרשרת boot של הפרויקט, ולכן הסדר הוא:

1. `training\00_SETUP.bat` להתקנת סביבת המחשב.
2. `radio_firmware\00_CHECK.bat`.
3. `radio_firmware\01_UPDATE_MODULE.bat` לעדכון ה־ST67.
4. `training\13_FACTORY_PROVISION.bat` למחיקה מלאה ולכתיבת FSBL, Secure,
   Slot A ושני עותקי metadata.
5. לאחר boot מוצלח אפשר להשתמש בלולאה הרגילה
   `10_LOAD_RAM.bat` → `11_HIL.bat` → `12_FLASH_RELEASE.bat`.

`10_LOAD_RAM.bat` לבדו אינו provisioning למעגל ריק: הוא נעזר ב־FSBL שכבר
מותקן כדי לבצע handoff מאובטח ל־Secure ול־Non‑Secure שב־SRAM.

## אזהרות ורישוי

- קובץ ה־NCP הוא binary חתום של ST. לפי כלי הייחוס של ST, צריבתו עלולה לנעול
  לצמיתות מודול שעדיין אינו נעול. לכן נדרש האישור המדויק `UPDATE ST67`.
- תהליך העדכון מחליף זמנית את ה־FSBL ב־NOR החיצוני. אין לנתק מתח בזמן כתיבה.
- הקבצים תחת `vendor` מקורם ב־X‑CUBE‑ST67W61. תנאי ההפצה נמצאים ב־
  `vendor/LICENSE_BINARIES`, והודעות QConn ב־`vendor/NOTICE_QConn_Tools.txt`.
- `01_UPDATE_MODULE.bat` אינו מפעיל Wi‑Fi באפליקציה. הדגל
  `APP_ST67W6X_WIFI_SERVICES_ENABLED` עדיין קובע אם Stage 11 יריץ גם בדיקת
  station ו־scan; BLE נבדק רק כאשר דגל ה־BLE פעיל.
