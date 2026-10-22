# XIP ועדכוני USB / OTA — ענף ניסוי 2026-10-22

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
ב־SAU. ה־NS מפעיל instruction cache; מדיניות data cache הקיימת נשמרת.
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
