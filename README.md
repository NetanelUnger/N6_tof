# STM32N6 ToF, Wi-Fi and BLE

Firmware for the NUCLEO-N657X0-Q: acquire 54×42 VL53L9CX depth images,
run Neural-ART inference, and view images or issue CLI commands over USB,
BLE or the Cloud relay. ThreadX runs the application; an FSBL and Secure
application provide external-NOR boot and signed Non-Secure A/B updates.

<a id="demo-30-minutes"></a>

## דמו ב־30 דקות

זהו מסלול הדגמה לפרויקט STM32N6 הראשי. כלי ה־RAM והתיעוד יובאו מעותק
הניסוי `D:\N6_AI_TEST`; המודל הקיים כאן נשאר RPS עם ארבע מחלקות.
**דמו `danger-demo` בעותק הניסוי הושלם; אין צורך להמשיך לשפר את הדיוק שלו.**
המודל, הדגימות והתוצרים של אותו דמו נשארו שם;
[סיכום הדמו](docs/danger-demo-ram_HE.md#demo-handoff) הוא תיעוד היסטורי.

תנאי פתיחה: לוח שכבר הוכן עם FSBL ו־Secure תואמים, כלי CubeIDE/STEdgeAI
וסביבת `training/.venv` מותקנים, ותוצרי RAM מוגנים זמינים. בפרויקט הראשי
ברירות המחדל של כתיבת הגדרות נשארו פעילות; להכנת מועמד RAM מוגן צריך
`APP_SETTINGS_WRITES_ENABLED=0U` ו־`APP_SETTINGS_TRANSITION_ENABLED=0U`.
שלב 10 מסרב כשהם פעילים. [הכנה וטעינה](docs/ram-demo-loader_HE.md).
התקנות ראשוניות, הכנת מועמד ראשון, לוח ריק ותיקון שרשרת אתחול אינם חלק
מחצי השעה. מריצים מהשורש `N6/project`.

| זמן | פעולה | נקודת יציאה |
|---|---|---|
| 0–4 דקות | חברו את המגנים, USB נתונים ל־CN8 ו־USB ל־ST-LINK. בחרו או שכפלו פרויקט ב־`training\00_PROJECT.bat`. | פרויקט, מחלקות וחיבורים מוגדרים. |
| 4–7 דקות | סגרו מסופים ונתקו לקוח BLE. BOOT0=1–2, BOOT1=2–3, לחצו Reset וטענו תוצרי RAM מוגנים לפי המדריך. | `LOADED`, USB חזר ו־`tof status`/`rps status` מציגים מוכנות. |
| 7–13 דקות | אספו ב־USB לפי התקציב שנקבע מראש ובדקו תיוג ב־`02_REVIEW_DATASET.bat`. בפיילוט AA היו 48 דוגמאות בכל אחת משתי מחלקות, בארבע קבוצות של 12. | איסוף קצר ומתוייג באותה הצבה; מקור הנתונים נשמר. |
| 13–24 דקות | הריצו 03–08 לפי הפקודות להלן. | מודל משולב שעבר את שערי ההמרה והזיכרון. |
| 24–28 דקות | שוב Reset ב־DEV, שלב 10 עם `--keep-network` ומזהה ST-LINK, ואז שלב 11 ללא Reset ביניהם. | 100 פריימים עוברים בדיקת CRC, קלט ותוצאת NPU. |
| 28–30 דקות | בצעו בדיקה אחת בכל מצב שהוגדר באמצעות `rps status`, רשמו את התוצאה בפועל וסיימו בסיכום. | המודל, הקבצים, טעינה חוזרת והמגבלות מתועדים. |

48 דוגמאות וארבע קבוצות היו בחירה לפיילוט AA, לא ברירת מחדל לכל מודל.
אין להקטין אוטומטית יעדי איסוף או להקל בשערי זיכרון/HIL. חצי שעה היא
תקציב להדגמה מוכנה. אם שער נכשל או חסר תנאי פתיחה, מתעדים את החסם ועוצרים;
לא מתחילים סבב דיוק נוסף. לשחזור מודל שכבר נבדק מדלגים על איסוף ואימון
ומשתמשים ב־manifest הקפוא שלו.

ב־PowerShell בוחרים את הפרויקט הקיים או החדש במפורש. הריצו כל שלב רק
אחרי הצלחת הקודם:

```powershell
$demo = Read-Host 'Training project ID'
.\training\01_CAPTURE.bat --project $demo --transport usb
.\training\02_REVIEW_DATASET.bat --project $demo
.\training\03_VALIDATE.bat --project $demo
.\training\04_PREPARE.bat --project $demo
.\training\05_TRAIN.bat --project $demo
.\training\06_QUANTIZE.bat --project $demo
.\training\07_GENERATE_N6.bat --project $demo
.\training\08_INTEGRATE_MODEL.bat --project $demo
```

אם באיסוף רץ פרופיל ישן, שלב 04 דורש בחירה מפורשת של
`--allow-host-preprocessing`; הטנסור המקורי נשמר, ומאמתים את הפרופיל החדש
בשלב 11. אחרי הכנת דגלי RAM מוגנים ו־Reset ל־DEV:

```powershell
$boardSerial = Read-Host 'Verified ST-LINK serial number'
.\training\10_LOAD_RAM.bat --project $demo --keep-network --board-serial $boardSerial
.\training\11_HIL.bat --project $demo
```

**תנאי התקשורת:** `--keep-network` משמר את כוונת החיבור השמורה של
Wi-Fi/Cloud לצד BLE; ללא הדגל ברירת המחדל היא BLE בלבד. הוא אינו יוצר
פרטי רשת חדשים. בזמן איסוף USB צריך לפנות זמנית חיבור BLE של דפדפן או
מסוף — האוסף מסרב לקחת את המסלול מלקוח מחובר. סוגרים גם מסוף שתופס את
CN8. אחרי האיסוף אפשר להתחבר שוב; אין לבצע Windows Pair.
למסוף הענן פותחים את ה־Workspace המתאים באתר ומשאירים אותו פתוח.
בדמו המתועד `HTTP409` נבע מ־Workspace לא פעיל; Wi-Fi מחובר לבדו אינו
מוכיח שמסוף הענן זמין. הדרישה למסוף אינה זהה לאיסוף Cloud מתוזמן דרך השרת.

**תנאי סיום:** אחרי הטעינה, HIL ובדיקה אחת בכל מצב, רושמים גם תוצאה שגויה
בלי לפתוח סבב שיפור. סיכום הסיום חייב לציין איזה מודל רץ, היכן הקבצים,
כיצד טוענים שוב ומה מחוץ להיקף. ראו
[דוגמת סיכום הדמו שהושלם](docs/danger-demo-ram_HE.md#demo-handoff).

## Hardware and connections

- **NUCLEO-N657X0-Q**, **X-NUCLEO-53L9A1** (VL53L9CX), and
  **X-NUCLEO-67W61M1** (ST67W611M1).
- A data-capable USB cable on **CN8** for the application console and updates.
  ST-LINK's separate USB/VCP connection provides boot and UART diagnostics
  at **115200 baud, 8N1**. COM numbers vary by computer.
- Optional GC9A01 240×240 SPI display; disabled by default in
  [config.h](AppliNonSecure/Core/Inc/config.h).

| Interface | Connections |
|---|---|
| ToF / I3C1 | SDA PC1, SCL PH9, XSHUT PD8, INT PD9 |
| ST67 / SPI5 | SCK PE15, MISO PG1, MOSI PG2, active-high CS PA3, CHIP_EN PE10, BOOT PD5, SPI_RDY PE9 |
| Optional display / SPI4 | SCL PE12, SDA PE14, DC PE1, CS PE13, RST PE2; **3.3 V** and common GND |

The display's SDA/SCL labels mean SPI, not I2C. ToF PD9 and radio PE9 share
EXTI9: the radio-enabled build uses PE9 interrupts and polls ToF readiness.
Check shield power, JP1/JP2 and SB31/SB34 against the intended wiring before
first use; software cannot validate solder bridges. Pin configuration lives in
[N6.ioc](N6.ioc). Do not change jumpers or power-cycle an already working board
for a routine USB update.

## Build

Use Windows PowerShell and **STM32CubeIDE 2.2.0**, including its GCC, make,
CubeProgrammer and signing tools. The scripts default to
`C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE`. Open/import the `FSBL`, `AppliSecure`
and `AppliNonSecure` projects if working in the IDE. Vendor radio sources are
tracked in `ThirdParty`; do not redirect builds to an external SDK copy.

Run commands below from the repository root, **`N6/project`**, on `main`.
For an existing generated build, compile Non-Secure changes without flashing:

```powershell
.\Tools\Build-NonSecureIncremental.ps1
```

For the persistent **XIP** application, first establish the board's confirmed
version and inactive slot. Enter those verified values; do not infer them from
an old README or the source version header:

```powershell
$nextVersion = [uint32](Read-Host 'Confirmed firmware version + 1')
$slot = Read-Host 'Verified inactive slot: A or B'
.\Tools\Build-Xip.ps1 -Slot $slot -FirmwareVersion $nextVersion -Label release
$package = ".local-dependencies\xip\v$nextVersion-$slot-release\N6-XIP-$slot-v$nextVersion.n6fw"
.\Tools\Test-XipPackage.ps1 -Package $package -ExpectedSlot $slot -ExpectedVersion $nextVersion
```

`Build-Xip` builds/signs the slot-specific package without programming hardware;
its output directory also contains build metadata and hashes. Keep the normal
watchdog, diagnostics and settings-preservation defaults. Output directories
are immutable: do not overwrite an earlier release to reuse its version.

Only regenerate code after changing `N6.ioc`. Review the
[CubeMX preservation rules](docs/engineering-reference.md#3-cubemx-rules) afterward. FSBL, Secure,
linker, startup or TrustZone changes need their corresponding build/validation;
a Non-Secure USB package cannot install a replacement boot chain.

## Run and update over USB

On an already provisioned board, keep the existing Flash-boot configuration
(BOOT0 and BOOT1 at 1–2), connect CN8 and open its CDC terminal. Start with
`version`, `status`, `tof status` and `rps status`.

To install the verified XIP package above, close any terminal using CN8 and run:

```powershell
.\Tools\Send-Xmodem.ps1 -File $package
```

The sender discovers CN8; use its `-Port` option only with the actual port.
The board finalizes the signed update and reboots automatically. Verify the
expected `version` and successful trial confirmation in the boot/update
diagnostics before declaring installation complete. An EOT ACK alone is not
proof of a confirmed boot; if verification fails, inspect the outcome before
retrying or selecting another version.

**Preserve the active slot and a known recovery package.** Updates must retain
signature/hash checks, strictly increasing versions, inactive-slot writes and
rollback. Do not erase NOR, bypass verification, or use the RAM-image update
lane as a substitute for a slot-specific XIP package. First provisioning or
boot-chain repair is a separate procedure: see the
[training/build guide](training/README_HE.md) and
[factory provisioning tool](Tools/Factory-Provision.ps1); it can erase Flash
and is not the routine USB update path.

## Everyday commands

For a bounded RAM demonstration, start with the
[30-minute route](#demo-30-minutes), [guarded reload procedure](docs/ram-demo-loader_HE.md)
and [handoff](docs/danger-demo-ram_HE.md#demo-handoff). Stage 10 now uses the
checked loader; DEV reset and an explicit `--board-serial` are required.
`--keep-network` retains saved Wi-Fi/Cloud intent; the default remains BLE only.
RAM loading alone is not a no-Flash-write guarantee: the documented FSBL,
settings and NCP guards are essential.

| Command | Purpose |
|---|---|
| `help`, `version`, `status` | Command list, running version and overall state |
| `tof status`, `rps status` | Sensor pipeline and NPU status |
| `radio status`, `wifi status`, `ble status`, `cloud status` | Radio health, recovery and transport counters |
| `MAP ON`, `MAP OFF` | Start/stop sensor images for the requesting transport |
| `MAP ENCODING UINT8` | Compact wireless images; RAW, UINT16 and JPEG are also supported |
| `DEMO MAP ON 1000`, `DEMO MAP ON 300` | Synthetic moving-pixel images every 1000 or 300 **milliseconds** |
| `DEMO MAP STATUS`, `DEMO MAP OFF` | Demo interval/admission/drop counters; stop the demo |

Demo intervals are 100–60000ms; legacy `ON 1`/`ON 2` operands are rejected.
Source IDs advance even when publication is skipped; `accepted` means queued,
not received by a browser. There is one remote image destination at a time
(USB, BLE or Cloud); switching transport can move the image stream.

## Detailed documentation and limits

- [Training, model build and BLE console](training/README_HE.md)
- [Wireless image formats and CRC contract](docs/wireless-image-codec.md)
- [Wi-Fi/settings persistence](docs/product-settings49_HE.md)
- [UART/USB diagnostic controls](docs/full-diagnostics57_HE.md)
- [Radio recovery ownership and limits](docs/radio-coordinated-recovery.md)
- [BLE/Cloud validation results and remaining limits](docs/ble-console-20261029.md)
- [Current working rules](AGENTS.md), [engineering constraints and Flash map](docs/engineering-reference.md)
- [Historical agent checkpoints](docs/agents-history-20261116.md), [change history](CHANGELOG.md)

This is a development platform, not a production security configuration.
The demo Cloud transport uses plaintext HTTP; do not transmit secrets or
sensitive captures through it. The shared development signing key and `-nk`
boot-image flow are not a production physical root of trust. Image backpressure
can drop frames, and verbose UART output can overflow its bounded queue;
neither continuous image delivery nor lossless diagnostic logging is guaranteed.
