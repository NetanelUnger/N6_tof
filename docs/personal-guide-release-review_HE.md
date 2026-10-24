# ביקורת המדריך האישי ושערי שחרור — למפתחים בלבד

מסמך זה נפרד מהתוכן ללומד. הוא מחליף את דוחות הסדנה הקודמים כמקור
להחלטת פרסום, אך אינו טוען שכבר מוזגו ענפים או ש־main אומת מקצה לקצה.
לא בוצעו במסגרת השכתוב שינויי קושחה, חיבורי חומרה, reset, upload, merge,
push או deployment.

## שינוי הכיוון שאושר בידי המשתמש

המדריך הוא מסלול אישי למי שמוריד main ומפעיל את הדמו במחשב ובחומרה שלו.
אין בו ניהול תחנות, חלוקת תפקידים, גרסאות כרטיס מקומיות, commit hashes,
נתיבי מחשב המפתחים, היסטוריית הרשאות או יומן ניסויים.

חלק ראשון: RPS מאומן ומוכן הוא נקודת הייחוס. חלק שני: בחירת שימוש חדש
בידי המשתמש; כוס ואדם יושב/עומד הם דוגמאות בלבד. האימון נעשה במחשב,
וה־NPU מריץ inference. המקור להורדה אומת הן מ־Git remote והן בפתיחת
המאגר הציבורי: https://github.com/NetanelUnger/N6_tof .

## Review של כל הסעיפים והתיקונים

| סעיף חדש | מה המשתמש יכול לעשות | תוצאת בדיקה / טיפול בכשל |
|---|---|---|
| 00 הורדה | לבחור main, לבצע Download ZIP או Fork ולזהות תיקיית שורש | ארבע תיקיות/קבצים ידועים; טיפול ב־ZIP שלא חולץ ובחומרי ייחוס חסרים. |
| 01 התקנות | להתקין כלים רשמיים ולהריץ 00_SETUP | Python3.11 ו־Setup complete; driver/Tcl/Tk וכלי ST חסרים. |
| 02 חומרה | לזהות שלושת שמות הלוחות, אותות, CN10/CN8, מקור מתח ו־BOOT | ST-LINK מזוהה; אזהרה מפורשת מפני שינוי גשרי מתח והחלפת לוחות. |
| 03 רדיו | לבדוק חבילת NCP ולהחליט בנפרד על עדכון חד־פעמי | CHECK והשלמת שחזור FSBL; אזהרת נעילה בלתי הפיכה לפני אישור UPDATE ST67. |
| 04 factory | להפעיל Stage13 עם ERASE ALL רק להכשרה מלאה | FACTORY PROVISION PASS ואימות USB; אין erase חוזר כתיקון אוטומטי. |
| 05 טרמינל | לבחור פורט, להגדיר Tera Term, לשלוח CLI ולראות MAP | ready/frame מתקדם, Enter חזרה; הבחנה בין UART, CDC, ANSI ו־capture. |
| 06 RPS | לבדוק רקע ושלוש מחוות ללא אימון | runs/errors/class וקלט NPU; טווח/חיתוך/מודל לא תואם. |
| 07 BLE | לבחור מכשיר ולהפעיל שלוש התראות נקובות בשמן | גרסה, תמונה ותוצאה עם frame; ללא Windows Pair. |
| 08 Wi-Fi/שרת | scan/connect עם סיסמה מוסתרת, workspace/+ ו־cloud pair | IP ואז online/PONG/MAP; הרשאות ו־403/409, בלי מחיקה אוטומטית. |
| 09 פרויקט | Create, Add, Retire, Apply input profile | פרויקט ושמות מחלקות נכונים; אין שינוי ל־RPS המקורי. |
| 10 capture | Source usb, Session, Start capture, מחלקה ו־Space | RAW/host preview ו־counts; עצמאות session ולא רק שם חדש. |
| 11 Review/split | Assign/Reject/Unlabeled, Validate/Prepare/audit | gate ו־leak check; חריגת source tensor מפורשת ומוסברת. |
| 12 אימון | Train, Analyze וקריאת confusion matrix | מדדים לכל מחלקה ודיון בטעות, לא הסתפקות ב־PASS. |
| 13 ייצוא/שילוב | STEDGEAI_PATH, Quantize, Generate, Integrate, Status | מודל/חוזה/generated עדכניים; בלי CPU fallback שקט. |
| 14 RAM/HIL | bootstrap מותנה, candidate בגרסה הבאה ו־100-frame HIL | fingerprint/CRC/tensor/scores; גם סצנה לא קבועה. |
| 15 package/update | package-only מה־candidate, חזרה ל־Flash ושליחת החבילה | EOT/boot/version/status; בלי erase, בלי ערבוב חבילות. |

לכל סעיף נכתבו דרישות מוקדמות, פעולות מסודרות, תוצאה צפויה וכשל נפוץ.
הסרנו מהתוכן ללומד את דוחות המהירות, heap, hashes, מצב HTTP של הכרטיס
המקומי, תהליכי UI והרשאות; אלו נשארים בדוחות ההנדסיים הקודמים בלבד.
הסרת מידע אינה הסרת סיכונים: מחיקת NOR, נעילת רדיו, סיסמאות/טוקנים,
HTTP בלתי מוצפן וגבולות בדיקת מודל עדיין מוסברים ליד הפעולה הרלוונטית.

## מקור ההוראות והפקודות

- שמות BAT ו־UI נקראו מהקוד בפועל: ProjectWizard/ClassEditor/CaptureApp,
  קובצי BAT, deploy_firmware, verified_package ו־Factory-Provision.
- שמות הענף/הורדת ZIP/Fork הם הוראות GitHub; אין פעולה שלנו במאגר מרוחק.
- שלב09 בונה/חותם ומבקש BOOTCHAIN; הוא כותב FSBL+Secure בלבד.
- Stage10 תומך `--version`; ב־package-only נדרשת אותה גרסת candidate
  שנקשרה ל־100-frame PASS של Stage11. אין rebuild לפני Send-Xmodem.
- שתי שורות PowerShell קוראות את גרסת header המקור ומחשבות את הבאה;
  הן נוסו כקריאה בלבד והחזירו את אותו מספר שמחזיר מנגנון הגרסה הקיים.
  אין מספר קושחה קבוע בתוכן הלומד.
- כדי לא להסתמך על dot-sourcing של סקריפט שמוגבל במדיניות ברירת מחדל,
  הקריאה לגרסה נעשית ב־Select-String. העברת XMODEM משתמשת בהפעלה
  נפרדת של סקריפט הפרויקט, ללא שינוי מדיניות מערכת גלובלי.
- המשתמש חוזר ל־Flash אחרי שמירת החבילה באמצעות ניתוק מתח ושינוי BOOT,
  לפני שליחה מהאפליקציה הקיימת. כך אין צורך להורות למתחיל לשנות ג'אמפרי
  BOOT בכרטיס חי כדי לשמר RAM. החבילה עדיין מכילה את ה־candidate שנבדק.

## שערים שמונעים טענת release-ready כעת

1. **קוהרנטיות main.** הוראות הלומד מיועדות להפצת main המוכנה למדריך.
   לא מוזג XIP ולא נטען שהמיזוג כבר נעשה. אם ההפצה העתידית היא XIP,
   יש להתאים ולאמת את Stage13/factory, Stage09/bootstrap, Stage10/RAM,
   Stage11/provenance ו־Stage12/package לאותה שרשרת אתחול, ללא החלפת
   execution mode שקטה. ה־XIP המקומי עדיין נפרד ומכיל שינויים מקומיים.
2. **חומרי RPS במאגר להורדה.** Git כיום עוקב אחרי gitkeep בתיקיות
   raw/models/reports; חומרי הלמידה המקומיים אינם מובטחים ב־ZIP/Fork.
   לפני שחרור צריך לכלול או לספק דרך מפורשת ומאומתת להורדת ערכת RPS
   התואמת לקושחה, כולל TFLite וחוזה. אין במדריך כתובת asset מומצאת.
3. **כרטיס חדש.** צריך לבצע פיילוט על ערכה חדשה, לפי גרסת החומרה
   המיועדת, מתהליך הורדה נקי ועד factory boot, USB וארבע מחוות RPS.
   בדיקת קושחה שמותקנת כבר אינה הוכחת factory-fresh.
4. **מיפוי פיזי מלא.** CN10/ST-LINK, CN8/USER, CN9[1-2], BOOT ותפקידי
   האותות נבדקו מול README ומדריך N6 UM3417. אין צילום פיזי מאומת של
   הערכה. צריך להשלים טבלת connector-pin/חוטים, מתחי VDDIO, חיבור שני
   shields והתאמות bridges לפי revision, ולא להניח stack-and-go.
   מיפוי אותות לבדו אינו בדיקת חיבור חשמלי. בפרט JP1/JP2 של הרדיו
   אינם JP1/JP2 של N6. הסעיף אינו מציג שינוי bridges אקראי כהוראה.
5. **נעילת רדיו.** תסריט ST והעטיפה המקומית מזהירים שניתן לנעול מודול
   לא נעול. יש לאשר את התנהגות QConn/efuse ואת השלכות LittleFS לפני
   הכללת עדכון רדיו כחלק מפיילוט חדש. לא הופעלה צריבה במסגרת הכתיבה.
6. **דיוק מסכי Tera Term/חומרה.** ההגדרות מבוססות פרוטוקול וקוד, אך
   צילום Tera Term והשלמת MAP חי בתהליך מדריך חדש עדיין חסרים. אין
   screenshot מזויף. ניסיונות ה־replay הקודמים נשארים בדוח ההנדסי.
7. **UI כללי.** CaptureApp עדיין מכיל בכותרת חלון מחרוזת RPS גם בפרויקט
   אחר. יש לוודא שה־guided_order, שמות המחלקות ו־preview אכן נגזרים
   מפרויקט חדש. הטקסט במדריך מתייחס לפקדים האמיתיים ולא לכותרת הישנה.
8. **כימות ושימוש חדש.** נדרש פיילוט של משימה חדשה מהתחלה: classes/profile,
   כמה sessions עצמאיים, Review, Prepare עם provenance מפורש, Train,
   Quantize, Generate, Integrate, RAM HIL, package-only והתקנה אמיתית.
   פרופיל spatial אינו UI חופשי לעריכת טווחים; יש לאמת שהסצנה נכללת
   בטווח המוגדר או להוסיף תמיכה מוגדרת לפני אימון למשימה שאינה נכללת בו.
9. **HIL של XIP כללי.** הסקריפט המקומי run_xip_model_regression מקובע
   ל־RPS; יש להכלילו לפני טענת אימות למודל חדש ב־XIP. שינוי זה הוא
   בכלי host, לא שינוי נדרש ל־Secure updater. פירוט בדוח המימוש הקודם.
10. **תצוגת מחלקות באתר.** RPS נכון לשלב הדמו. לאחר החלפת משימה,
    המדריך משתמש ב־CLI ובכלי המחשב; תוויות RPS באתר אינן הופכות לשמות
    חדשים אוטומטית. אם רוצים לתמוך בכללי באתר, נדרש חוזה מודל ומיפוי
    class_count ב־rpsProtocol/tofProtocol במקום ארבע מחלקות קבועות.
11. **Wi-Fi/Cloud.** נדרש פיילוט של יצירת workspace, שיוך עצמי, שמירת
    קובץ, PONG ותמונות עם השירות המיועד להפצה; לא בוצעו עכשיו יצירת
    workspace, שיתוף sensor data או שימוש ב־credentials. HTTP demo
    אינו מוצג כ־TLS. יש לאמת שמות UI בגרסת השירות שתפורסם.
12. **התאוששות.** אחרי package-only המשתמש חוזר לאפליקציה השמורה ושולח
    package שנבדק. צריך לאמת את כל הרצף, כולל header/source version
    המתאימים לגרסה בכרטיס ומניעת חבילת execution-mode אחרת. אין טענה
    לשרידות ניתוק מתח בזמן NOR; בדיקה זו לא בוצעה.

## תמונות ותוצרי מסירה

בתוכן הלומד נשארו רק classes-review.png ו־training-report.png. הכיתובים
מציינים שמדובר בדוגמאות מנתונים קיימים, ולא במדידה/אימון חדש של המשתמש.
serial-status.png, תמונת העמוד הישן, וצילומי המדריך הקודם לא מוטמעים
בעותק הלומד החדש, כדי שלא יבליטו גרסת פיתוח או תוכן שבוטל.

HTML המסירה העצמאי כולל רק את המדריך, העיצוב, שתי תמונות הדוגמה
וכלי audit להורדה. הוא אינו כולל דוח מפתחים זה, logs, workspace,
developer filesystem paths או גלריית screenshots של הטיוטה הקודמת.
אותה זהות Library נשמרת: libfile_23e165530de48191ae0bc9d54907cabc.

בדיקות תוכן, build/lint, ניווט, קישורים מקומיים, responsive ותוצר HTML
יירשמו לאחר סיום היישום. הצלחה בבדיקות אלה אינה סוגרת את שערי החומרה
וה־release שברשימה.

## Final local QA — 2026-10-24

- Website build and lint PASS after final numbered-action correction.
- Both /wiki and /wiki/workshop render the personal guide (16 steps).
- Each step has prerequisites, ordered actions, expected result and troubleshooting.
- All internal anchors resolve. Learner prose contains no station wording, pinned
  development revisions, commit hashes or local developer paths.
- Mobile 390x844: document width375, viewport390; no horizontal overflow.
  Desktop1280: document width1265. Real screenshots retained in the audit folder.
- Standalone HTML embeds both genuine screenshots and the read-only split helper;
  browser confirmed both image dimensions (1920 and1265) loaded successfully.
- No hardware, credentials, upload of sensor data, firmware edits, deployment,
  merge or push performed during this editorial rewrite.
- These checks validate documentation and presentation, not the unexecuted release
  acceptance gates listed above. Main is the intended release entry point; this
  report does not claim that XIP changes are merged or factory setup was run.

## Final security and fresh-download audit — 2026-10-24

Read-only scope: scripts/source, Git tracked paths, key file presence/size only,
installed STM32 SigningTool v2.23.0 -h, and official ST UM2543. No private-key
contents read, no keys generated, no CNG import/signing invoked, no hardware.

### Encryption, authentication and key lifecycle

- Tools/build_and_sign.ps1:122 and Package-VerifiedRamCandidate.ps1:25 call
  STM32_SigningTool_CLI with -nk -of 0x80000000 -hv2.3 -align. Vendor help defines
  -nk as empty header without key options. No -prvk/-pubk/-enck/-encdc is used.
  These trusted-named files are development STM32-header images, not proof of
  ROM-authenticated secure boot or encrypted firmware. Do not infer production
  root of trust from Secure/TrustZone or from filename.
- New-FirmwareUpdatePackage.ps1 hashes the entire STM32-header image, signs the
  first60 manifest bytes (including image hash/version/target/size) with Windows
  CNG ECDSA P-256, stores64 signature bytes in a256-byte manifest, then appends
  the original image. No cipher step. Weights integrated into that image are
  covered by its hash/signature, not separately encrypted/signed model assets.
- Secure secure_firmware_update.c verifies manifest before accepting update,
  hashes incoming image, reads back NOR and verifies hash/signature before boot
  metadata publication. FSBL firmware_boot.c checks pending/trial manifests and
  image hashes. Factory version-zero slotA is intentionally accepted by strict
  header/vector bounds checks; New-FactoryBootMetadata.ps1 sets that metadata
  version independently of application display version. This is NOT a fully
  fused vendor-authenticated boot chain. No OTP/provisioning was examined live.
- The104-byte educational private CNG blob is intentionally Git tracked at
  .local-dependencies/keys/firmware-update-p256-private.blob (not read). Public
  verification header Common/Update/firmware_signing_public_key.h is tracked.
  Fresh normal Git/ZIP should therefore include these paths; no generation is
  required for demo. Public/private pair mathematical correspondence was not
  tested in this audit because private contents/import are out of scope.
- New-FirmwareSigningKey.ps1 creates a random ECDsaCng pair, refuses overwrite
  of existing private file, writes private blob and rewrites public C header.
  Backup/retain matching pair; it is not deterministically recreated from model
  data or source. Changing it requires matching Secure+FSBL rebuild/install and
  a deliberate update/rollback trust migration. No automated per-user key
  generation belongs in the ordinary guide; no certificates needed by this path.
- release_manifest.json/factory-manifest.json are provenance/hash records,
  not independently authenticated certificates. Keep exact HIL candidate, model,
  contract and package linked. ECDSA signing can produce different package bytes;
  verify the retained candidate/package, do not promise byte-identical re-signing.
- Sensor N6DF CRC, raw/uint/jpeg encoding and host SHA do not provide secrecy.
  No application-level sensor cipher/key provisioning found in this guide path.
  BLE security configuration is Just Works I/O capability, not a demonstrated
  confidential/authenticated channel guarantee. USB/local files are plaintext;
  Wi-Fi link protection/HTTPS browser leg do not imply encrypted NOR or device
  HTTP leg. Retain Transport security check and non-sensitive test data.
- Official reference: https://www.st.com/resource/en/user_manual/um2543-stm32-signing-tool-software-description-stmicroelectronics.pdf

### Additional blockers found before user test

1. Fresh headless build needs Eclipse workspace registration: build_and_sign
   uses sibling .codex-cubeide-workspace and -build without -import. Guide now
   explicitly imports the three tracked .project projects, no copies, Debug,
   and closes IDE before scripts. This procedure is source-supported, not
   independently tested on a fresh installation in this audit.
2. RAM guard build assumes existing ordinary Debug ELF/BIN/MAP. Guide now
   requires successful initial full build first. HIL air scan also requires
   working host Bluetooth even if data acquisition uses USB.
3. Guarded RAM idle_board requires an already-running CDC application before
   Debug-NonSecureRam resets into DEV. Guide now explicitly says start app in
   Flash, stop streams, select DEV without reset, run loader. Reset first in DEV
   removes CDC and fails preflight. Exact mixed jumper/start sequencing still
   needs the physical release pilot, particularly after any XIP changes.
4. Direct Send-Xmodem does not call Assert-N6InstalledBootChain. Guide now calls
   existing read-only guard immediately before transfer. Missing/stale stage09
   hash record must stop, not bypass. No helper/firmware implementation changed.
5. NEW CRITICAL RELEASE GATE: app_settings.h defaults both WRITES_ENABLED and
   TRANSITION_ENABLED to0; cloud_save_pairing requires AppSettings_SaveCloud OK.
   New pairing cannot be promised by current defaults. Release must provide a
   supported, explicitly scoped settings/pairing path; do not flip flags in docs
   or repeatedly create credentials. Guide troubleshooting now stops on this.
6. Training raw/models/reports remain gitkeep-only while compiled pretrained
   RPS code/weights are tracked. Demo inference is bundled, but promised full
   educational data/model/report materials need a release artifact/source.
7. Existing future-main/XIP integration and physical factory/personal-model
   end-to-end gates above remain open. No claim main is ready today.

### Documentation corrections

Learner guide now explains firmware image versus sensor image; header versus
signature versus encryption; educational key inclusion and safe Test-Path-only
check; no automatic key generation; key lifecycle; first CubeIDE import; live
CDC requirement before RAM load; host BLE and ordinary Debug prerequisites;
manual update boot-chain guard; manifests as provenance; BLE/CRC privacy limits.
No station/revision/audit narration added to learner prose.

### Additional critical state-path mismatch

Tools/N6-DevCommon.ps1 Assert-N6InstalledBootChain currently reads only
training/state/09_secure_bootstrap.json. training/scripts/common.py mark_stage
writes STATE_ROOT under the selected project's training root; Stage09 with
--project my-use-case therefore records projects/my-use-case/state instead.
The proposed manual transfer guard safely stops on absent/stale legacy state,
but cannot be advertised as an already-working end-to-end personal-project
release path on a fresh download. Minimal host-tool release fix: make the guard
accept/resolve selected project's state path, pass that context from installer,
and retain exact FSBL/Secure raw-hash checks; never copy or forge state. No
firmware change is needed for this path-resolution issue. This is separate from
XIP build/HIL adaptation and Cloud writes gate. No such feature fix made here.

### Final focused verification

Final build/lint PASS. Browser confirms16 steps at both original /wiki and
/wiki/workshop; all anchors resolve. Mobile390 width: document375, no pre/details
horizontal overflow. All13 displayed command blocks parse as PowerShell without
execution, and all13 referenced BAT/PS1 paths exist. Standalone packaging checks
three embedded assets and no forbidden learner revision/station/developer paths.
No claim that parsed commands were executed on hardware. Screenshot
signing-keys-guide.png shows the actual expanded explanation and import steps.

## Optional personal signing-key appendix — documentation only

Added a collapsed optional appendix outside the16-step default flow, linked
from the introductory key explanation. It documents New-FirmwareSigningKey.ps1
with explicit PrivateKeyPath outside the repository and PublicHeaderPath in
ignored local output; public-header integration for both FSBL and Secure;
Factory-Provision -BuildOnly; explicit New-FirmwareUpdatePackage -PrivateKeyPath;
backup, no overwrite, unencrypted CNG blob storage protection, and key reuse.
Only command syntax will be parsed; no generation/signing/build-with-key runs.

The default educational private blob is tracked by deliberate .gitignore
exception. Therefore NEVER copy a personal secret into that default path; the
appendix does not do so. Public generated header may be committed, private
remains external. Generator's default educational shared-key comment is
boilerplate, not instruction to share a personal private key.

Important limitation made prominent: build_and_sign, Install-NonSecureUpdate,
and Package-VerifiedRamCandidate still choose default educational key. BuildOnly
can emit a .n6fw signed with that old key even after changing verification header;
that file is not suitable for the new verifier. Explicit packaging supports a
custom key but is not automatically HIL-approved or installed. The example
extracts current source version only for an image built with that same version;
a distinct HIL candidate must retain its own embedded version and binding.
No supported in-place two-key rotation/trust migration exists. Existing devices
must not receive a bootstrap/key replacement as a routine update. No fuses,
ROM secure-boot/AES or ST radio signing-key recipe added. Existing startup,
state-path, pairing and XIP fixes remain outside authorized scope and unchanged.

Optional appendix QA: site build/lint PASS; sixteen displayed code blocks parsed
as PowerShell without execution; fifteen BAT/PS1 referenced paths exist. Original
sixteen main steps retained, appendix closed by default,9 optional actions,
all anchors valid. Both wiki routes include appendix. Mobile390: document375,
no optional code-block overflow. Portable HTML images load1920/1265 and optional
appendix present. Only website source/docs and deliverable changed; no private
key access/generation, firmware build, provisioning, hardware or Git changes.
