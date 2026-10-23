# Watchdog ומשימות תקועות — תכנון ובדיקת אבחון

המימוש opt-in בבניית XIP עם `-Watchdog -ResourceDiagnostics`. בבנייה הרגילה
`N6_WATCHDOG_ENABLED=0`: אין הפעלה של watchdog ואין פקודת תקיעה. לא משנים
OTP, option bytes, RIF, מדיניות debug או הרשאות. IWDG נגיש דרך המיפוי NS
הקיים; אין פתיחת גישה חדשה ל־peripheral. הבדיקה בחומרה עדיין נדרשת.

מקור ST: [HAL IWDG של STM32N6](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/main/Src/stm32n6xx_hal_iwdg.c)
ו־[LL IWDG](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/main/Inc/stm32n6xx_ll_iwdg.h).
LSI עצמאי ממשיך גם אם שעון הליבה תקוע. לאחר הפעלה בתוכנה אי אפשר לעצור
אותו עד איפוס. מחלק256 ו־reload1999 נותנים16s נומינליים ב־32kHz; תדר LSI
משתנה ולכן זמן האיפוס הפיזי טעון מדידה. אין ISR שמזין אותו ואין הזנה בכותב NOR.

## ניטור

משימת אישור האתחול הקיימת, בעדיפות6 ובלי stack נוסף, הופכת ל־supervisor.
כל100ms היא בודקת תשעה owners: UART TX, פקודות UART, CLI, רכישת ToF,
עיבוד/NPU, תצוגה, רדיו, Wi-Fi control ו־Cloud. רק הקוד שרץ במשימה מעדכן
heartbeat; קריאה מ־ISR נדחית. הזנה לא מעידה לבדה על דיוק המודל או תקינות חיישן.
משימות פנימיות של ספק אינן מנוטרות אחת־אחת; תקיעות השירות נראות דרך owners
והפעולות התחומות שלהם. אין הבטחת איתור כל תקלה לוגית או השחתת זיכרון.

תקציבי אי־התקדמות, בשניות: UART TX3, UART control4, CLI8, ToF acquire12,
process6, display6, radio35, Wi-Fi control45, Cloud35. תקציבים אלה כוללים
פעולות מוגבלות בקוד ואינם טענה למדידת WC מלאה. Wi-Fi idle הוא30s; heartbeat
נוסף מפריד את סוף ההמתנה מתחילת פעולה. אין הארכת budget בלתי מוגבלת לפי
דגל update. UART TX ממתין לכל היותר1s; process/display ממתינים עד100ms
בפרופיל הזה בלבד, וכך ממשיכים להוכיח התקדמות גם ב־ToF pause.

יש grace חד־פעמי של45s מתחילת ה־supervisor עבור startup חסר. לפני ששני
סימוני התקדמות נצפו מכל owner נדרש, אין אישור גרסת ניסיון. לאחר חריגה,
מוחזק failure mask וההזנה נעצרת עד reset גם אם owner חוזר אחר כך. ה־mask
נשמר ב־RAM בנפרד מתור הלוג; הודעת כשל מוגבלת לפעם אחת. בהיעדר יכולת
לשדר לוג, ה־IWDG עדיין פועל. אם ה־supervisor עצמו נתקע/מורעב או פסיקות
נחסמות, לא תתבצע הזנה והחומרה היא שמאפסת.

## אבחון UART בלבד

רק ST-LINK VCP USART1 מפענח אותיות אלה; אין פקודת תקיעה ב־USB/BLE/Cloud.
אחרי HEALTHY, ללא updater פעיל או finalization, `w` דורך את משימת פקודות
ה־UART, ו־`s` דורך את ה־supervisor. שליחת `W` בתוך חמש שניות מפעילה את
היעד שנבחר. פקודה אחרת מבטלת דריכה; CR/LF לבדם אינם מבטלים. W בלי דריכה,
דריכה שפגה או updater busy נדחים. הודעת target משודרת לפני while(1), עם
flush מוגבל לשנייה. הדריכה נצרכת לפני התקיעה ולא נשמרת באתחול הבא.
אין הזנה מתוך לולאת התקיעה; פסיקות נשארות מופעלות.

יש לאמת החלון בחומרה בנפרד: `wW` מוכיח supervisor שמפסיק הזנה עבור owner
תקוע; `sW` מוכיח שגם supervisor שאינו מבצע בדיקות אינו מסתיר תקיעה.
אין לבצע במהלך עדכון או על גרסת ניסיון שטרם אושרה.

## Reset ומרווחי זיכרון

מציגים RCC RSR ואת סיבית IWDGRSTF לפני ניקוי דגלי reset הנדיפים. זה אינו
שינוי אבטחה קבוע. איפוס MCU אינו ניתוק מסילות ST67/VL53/LCD: חובה לאמת
בריאותם לאחר אתחול ולא לכנותו power cycle של כל הלוח.
אין malloc במנטר, אין printf ב־ISR, אין task/stack נוסף. סימוני התקדמות
מוגבלים בגודל, count רווי מונע wrap של מונה seen; חישובי זמן תומכים ב־wrap.
עדיין צריך בנייה, מדידת stack/heap בפרופיל ומבחן עדכון עם IWDG פעיל.

## בדיקות מחשב שכבר עברו

`hil_tests/test_watchdog_supervisor.py`: עשר קבוצות בדיקת C של הקוד בפועל,
עם IWDG/RTOS מדומים: גבולות/wrap, סירוב ISR, הזנה מותנית, כשל ננעל,
startup מוגבל, supervisor תקוע, sync failure, expiry, update busy,
ביטול/צריכת דריכה ושני יעדי fault. יבוא Python תחת hardware-denied עבר
ללא side effects. אלו אינן הוכחת איפוס בחומרה.
