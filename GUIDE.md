# Building the STM32N657 ToF and USB CDC Project from Scratch

This guide explains how to reproduce the beginning of this project and how the
generated STM32CubeMX application was turned into the working firmware in this
repository.

It is written as a learning guide, not as a claim that one CubeMX click produces
the complete application. CubeMX creates the board, clock, security, peripheral,
and middleware skeleton. The VL53L9CX port, asynchronous acquisition pipeline,
USB transport architecture, boot corrections, diagnostics, image signing, and
programming workflow are additional engineering work performed after code
generation.

For the exact implementation and its history, read [README.md](README.md).
For the rules that protect the working hardware checkpoint, read
[AGENTS.md](AGENTS.md).

## 1. What this guide builds

The target system consists of:

- A NUCLEO-N657X0-Q board with an STM32N657X0H3Q.
- An X-NUCLEO-53L9A1 expansion board carrying the VL53L9CX Time-of-Flight
  sensor.
- A multi-image external-Flash boot flow:
  BootROM -> FSBL -> Secure application -> Non-Secure application.
- TrustZone isolation between the Secure and Non-Secure worlds.
- I3C1 with DMA and an interrupt from the VL53L9CX.
- ThreadX tasks for sensor acquisition and frame processing.
- USBX CDC ACM through the board's user USB Type-C connector.
- A 54 x 42 ANSI color depth map and a small command interface over USB CDC.
- Independent diagnostic output through the ST-LINK Virtual COM Port.

The completed application has been tested on real hardware at a 100 ms sensor
period. Acquisition and processing overlap, and the complete terminal map is
sent through a callback-driven, statically allocated USB transport.

## 2. Software and documentation to download

Download the packages from ST's official pages. Keep the original archives
outside the source tree or under a Git-ignored local-dependency directory.

| Item | Why it is needed | Official link |
|---|---|---|
| STM32CubeMX | Board and peripheral configuration, multi-context project generation | [STM32CubeMX](https://www.st.com/en/development-tools/stm32cubemx.html) |
| STM32CubeIDE | Editing, building, debugging, and inspecting generated projects | [STM32CubeIDE](https://www.st.com/en/development-tools/stm32cubeide.html) |
| STM32CubeProgrammer | External-Flash programming and verification | [STM32CubeProgrammer](https://www.st.com/en/development-tools/stm32cubeprog.html) |
| STM32CubeN6 | STM32N6 HAL, BSP, ThreadX, USBX, USB-PD, examples, and external-memory support | [STM32CubeN6](https://www.st.com/en/embedded-software/stm32cuben6.html) |
| X-CUBE-53L9A1 | VL53L9CX driver, platform example, transform library, and supporting middleware | [X-CUBE-53L9A1](https://www.st.com/en/embedded-software/x-cube-53l9a1.html) |
| NUCLEO-N657X0-Q page | Board documentation, schematics, manuals, and resources | [NUCLEO-N657X0-Q](https://www.st.com/en/evaluation-tools/nucleo-n657x0-q.html) |
| X-NUCLEO-53L9A1 page | Sensor expansion-board documentation and resources | [X-NUCLEO-53L9A1](https://www.st.com/en/evaluation-tools/x-nucleo-53l9a1.html) |

Two manuals are especially useful:

- [Getting started with STM32CubeN6 (UM3249)](https://www.st.com/resource/en/user_manual/um3249-getting-started-with-stm32cuben6-for-stm32n6-series-stmicroelectronics.pdf)
- [STM32CubeMX user manual (UM1718)](https://www.st.com/resource/en/user_manual/dm00104712-stm32cubemx-for-stm32-configuration-and-initialization-c-code-generation-stmicroelectronics.pdf)

The working repository was generated and validated with:

- STM32CubeMX 6.18.0.
- STM32Cube firmware package for STM32N6 V1.4.0.
- STM32CubeIDE 2.2.0.
- X-CUBE-53L9A1 V1.0.0.
- STM32CubeProgrammer and signing tools 2.23.0.

Newer releases may generate different code. That is not necessarily wrong, but
it means that file-level differences and the post-generation audit in this
guide become important. Keep [N6.ioc](N6.ioc) as the known-working
configuration reference.

## 3. Understand the STM32N6 boot structure first

The STM32N657 application in this repository is not one ordinary executable.
The project contains four CubeMX contexts:

1. **FSBL** — initializes the external memory path and loads the application
   images.
2. **AppliSecure** — configures TrustZone, RIF, RISAF, and the handover to the
   Non-Secure application.
3. **AppliNonSecure** — runs ThreadX, the sensor pipeline, USBX, USB-PD, the
   terminal, and the application logic.
4. **ExtMemLoader** — lets STM32CubeProgrammer access the board's external NOR.

The programmed image layout used here is:

| Image | External NOR address |
|---|---:|
| FSBL | `0x70000000` |
| Secure application | `0x70100000` |
| Non-Secure application | `0x70180000` |

The conceptual boot sequence is:

```text
Reset
  |
  v
STM32 BootROM
  |
  v
FSBL in external NOR
  |-- initialize and map XSPI2 NOR
  |-- load the Secure image
  `-- copy the Non-Secure image to its execution RAM
          |
          v
Secure application
  |-- configure TrustZone/RIF/RISAF
  |-- preserve the Non-Secure vector values
  `-- release the required resources to Non-Secure
          |
          v
Non-Secure Reset_Handler
  |
  v
HAL + ThreadX + ToF + USBX application
```

This explains why programming only the Non-Secure binary is not sufficient and
why a normal source edit can require rebuilding and signing more than one
context.

## 4. Phase A — create the CubeMX board project

The exact labels in the user interface can change slightly between CubeMX
releases. The important outcome is the configuration, not the spelling of a
particular dialog.

### 4.1 Select the board

1. Start STM32CubeMX.
2. Choose **Start My Project from Board** or **Board Selector**.
3. Search for `NUCLEO-N657X0-Q`.
4. Select the board and start the project.
5. When CubeMX asks whether it should initialize the board peripherals in their
   default modes, answer **Yes**.
6. Accept the offered board support for the LEDs and the board USB path.

Starting from the board is valuable because the USB Type-C path is more than
two data pins. The Nucleo design also uses UCPD1 and TCPP0203 for connector
detection and protection.

### 4.2 Enable the complete secure project structure

Select the TrustZone-capable Secure/Non-Secure project and enable all offered
project contexts:

- FSBL.
- Secure application.
- Non-Secure application.
- External-memory loader.

In the working IOC this is represented by:

```text
ProjectManager.ProjectStructure =
  FSBL:FSBL:true;
  AppS:AppS:true;
  AppNS:AppNS:true;
  ExtMemLoader:ExtMemLoader:false;
```

Also select:

- **STM32CubeIDE** as the target toolchain.
- **Keep User Code when re-generating**.

The resulting repository should contain separate `FSBL`, `AppliSecure`, and
`AppliNonSecure` projects plus the external-memory support generated for the
board.

### 4.3 Generate and build the untouched board project once

Before adding the sensor:

1. Generate code.
2. Import/open all generated projects in STM32CubeIDE.
3. Build the untouched project.
4. Confirm that CubeMX has generated the expected contexts.

This creates a clean baseline. If the baseline does not build, adding a sensor
driver will only hide the original problem under more code.

## 5. Phase B — configure the sensor interface in CubeMX

The X-NUCLEO-53L9A1 is used through I3C1. The following assignments match the
working hardware:

| Function | MCU pin | CubeMX mode | Context |
|---|---|---|---|
| `TOF_SDA` | PC1 | I3C1 SDA, Controller | AppliNonSecure |
| `TOF_SCL` | PH9 | I3C1 SCL, Controller | AppliNonSecure |
| `TOF_XSHUT` | PD8 | GPIO output, initial High | AppliNonSecure |
| `TOF_INT` | PD9 | GPIO EXTI, falling edge, no pull | AppliNonSecure |

Use the labels shown in the table. They make generated code and later
diagnostics much easier to read.

### 5.1 I3C1

Enable I3C1 in Controller mode and assign PC1/PH9. The validated bus settings
are:

- Push-pull I3C frequency: 12.5 MHz.
- Open-drain frequency: 2.5 MHz.
- I3C1 kernel clock: 200 MHz.
- SDA hold time: 1.5.

The working IOC currently produces:

```text
I3C timing register 0 = 0x00470707
I3C timing register 1 = 0x102800C6
```

Do not blindly paste timing-register values into a project with a different
kernel clock. Configure the desired frequencies in CubeMX and compare the
result with [N6.ioc](N6.ioc).

### 5.2 GPDMA1

Create these GPDMA1 requests:

| DMA channel | Request |
|---|---|
| Channel 0 | I3C1 Transfer Control |
| Channel 1 | I3C1 RX |
| Channel 2 | I3C1 TX |

Enable the interrupts for all three DMA channels in the Non-Secure context.
Also enable:

- I3C1 event interrupt.
- I3C1 error interrupt.

The DMA channels make the steady-state frame transfer asynchronous. The task
starts the operation and waits for an event that a HAL callback posts; it does
not continuously poll the peripheral.

### 5.3 PD9 sensor interrupt and TrustZone ownership

Configure PD9 as:

- External interrupt on the falling edge.
- No pull-up or pull-down.
- Owned by AppliNonSecure.

Also assign PC1, PH9, and PD8 to AppliNonSecure in the GPIO/RIF context
configuration.

There is one N6-specific detail that CubeMX did not completely solve for this
integration: Secure code must explicitly make EXTI line 9 Non-Secure and route
the interrupt target to the Non-Secure world. The preserved Secure USER block
contains the equivalent of:

```c
HAL_EXTI_ConfigLineAttributes(EXTI_LINE_9,
                              EXTI_LINE_NSEC | EXTI_LINE_NPRIV);
NVIC_SetTargetState(EXTI9_IRQn);
```

Without this handoff, the sensor can initialize yet the acquisition task can
wait forever for the first frame interrupt.

## 6. Phase C — configure ThreadX

Enable Azure RTOS ThreadX for the Non-Secure application. CubeMX initially
creates a main application thread and a byte pool.

The final working project uses:

- A 192 KiB application byte pool.
- A 96 KiB processing-task stack.
- A 16 KiB acquisition-task stack.
- Processing priority 10.
- Acquisition priority 7.

In ThreadX, a numerically smaller priority is more urgent. Acquisition therefore
preempts processing when the next sensor frame is ready. This is intentional:
losing a little rendering time is better than delaying the next I3C DMA
transaction.

Do not interpret these stack sizes as a recommendation for every application.
They are conservative values selected after observing deep transform-library
call chains and real stack-overflow faults. Once the system is stable, ThreadX
stack analysis can be used to establish a smaller measured limit.

## 7. Phase D — configure USB CDC in CubeMX

The working design uses the board's user USB Type-C connector and USBX CDC ACM.
It also uses the Type-C cable-detection path generated for the board.

### 7.1 Peripheral configuration

Configure:

- USB1 OTG HS as **Device HS** with the embedded PHY.
- USB1 DP and DM in the Non-Secure context.
- UCPD1 CC1 and CC2 as sink signals in the Non-Secure context.
- USB-PD/Type-C support for port 0.
- The board's TCPP0203 support path, including its generated I2C2, ADC12, GPIO,
  and UCPD dependencies.

The board-selection flow normally supplies much of this. Do not remove an
apparently unrelated TCPP, ADC, or UCPD item until you understand its role in
Type-C attachment detection.

### 7.2 USBX middleware

Enable:

- USBX Core System.
- USB Device Core Stack for HS1.
- USB Device Controller for HS1.
- CDC ACM class for HS1.

The validated values are:

| Setting | Value |
|---|---:|
| USBX application memory pool | 32 KiB |
| USBX system memory | 6 KiB |
| Maximum control request data | 512 bytes |
| CDC data endpoint | EP1 |
| CDC command endpoint | EP2 |
| CDC transmission disable | 0 |
| Automatic zero-length packet | Enabled |
| Product string | `STM32N6 VL53L9CX ToF` |
| Serial string | `N6TOF001` |

`CDC transmission disable = 0` is important. It enables the USBX callback
transmission API used by the asynchronous TX worker.

### 7.3 USB clock

USB needs an accurate 48 MHz source. In the validated configuration:

- The board HSE is configured as a 48 MHz digital bypass clock.
- USBPHY1 uses HSE divided by two where required by the PHY configuration.
- OTG HS1 uses the HSE-derived clock selected by the IOC.

After every Generate Code operation, check that the FSBL clock configuration
still uses the digital-bypass HSE. A generated `HSE_OFF` setting can allow much
of the application to boot while making USB enumeration impossible.

## 8. Generate Code and interpret the warnings

Generate the project after the CubeMX settings are complete. Warnings seen
during this project included:

- CubeMX changing a GPIO to an external-interrupt mode so the selected EXTI can
  work.
- Free pins that are not assigned to a security context.

These messages are not automatically fatal. Read the output window, confirm
that the four sensor pins and the USB pins have the intended owners, and then
allow generation.

At this point CubeMX has produced a useful skeleton, but it has not yet
produced a working 54 x 42 ToF terminal application.

## 9. Phase E — import the VL53L9CX software

Extract `STM32CubeExpansion_53L9A1_V1.0.0` from X-CUBE-53L9A1.

The driver package contains a reference application for a different STM32
family. Treat it as a hardware-driver and algorithm reference, not as a file
tree that can be copied over the N6 project without review.

The relevant source sets were imported into these locations:

```text
AppliNonSecure/
|-- Drivers/BSP/Components/vl53l9/
|-- Utilities/vl53l9-common/
|-- Middlewares/ST/media-object/
`-- Middlewares/ST/vl53l9-transform-c/
```

Keep the original ST license files with the imported source.

Add the corresponding include paths and source folders to the
AppliNonSecure CubeIDE project. A good practice is to build immediately after
each imported layer:

1. Component driver headers and sources.
2. Common platform/interface sources.
3. Media-object middleware.
4. Transform library.

This makes missing includes, incorrect CPU-family headers, and build-option
problems much easier to isolate.

## 10. Phase F — port the driver platform layer to STM32N6

The package's reference platform targeted another STM32. The following work was
required for STM32N657:

- Replace the reference-family HAL includes and handles with STM32N6 types.
- Map shutdown and interrupt GPIOs to PD8 and PD9.
- Map sensor transfers to the generated I3C1 handle.
- Use the generated GPDMA1 I3C channels.
- Bridge GPIO, I3C, and DMA completion callbacks to ThreadX event flags.
- Preserve useful HAL error and state values for diagnostics.
- Keep initialization operations simple and blocking where appropriate.
- Use asynchronous transfers for the repeated frame-acquisition path.

### 10.1 A critical asynchronous-lifetime rule

DMA and interrupt APIs return before the hardware operation is complete.
Therefore every object that the HAL will inspect later must still exist later.

The original reference implementation created some I3C descriptors, control
structures, status bytes, and address buffers as local stack variables. That is
unsafe after converting the call to an asynchronous transfer: the function
returns and the stack storage may be overwritten while DMA is still using it.

The working port keeps the complete asynchronous I3C operation context in
persistent storage. This includes:

- I3C transfer descriptors.
- Transfer-control structures.
- Target-address and status bytes.
- Register-address bytes.
- Operation state and diagnostics.

This is a general embedded rule:

> A buffer or descriptor passed to asynchronous hardware must live until the
> completion callback proves that the hardware no longer owns it.

### 10.2 Combined register transfers

For a register read, the write descriptor and read descriptor form one combined
I3C frame. They must be added together in one frame construction operation.

Adding the first descriptor and then making a second frame-construction call for
the second descriptor can reset the previously prepared frame. The result may
look like an intermittent DMA or protocol failure even though the wiring is
unchanged.

### 10.3 Event acknowledgement

The imported event-acknowledgement switch required a missing `break` after the
IBI case. Without it, the code could fall through into the next case and perform
the wrong acknowledgement. This was corrected in the imported platform code.

These changes are outside CubeMX USER CODE because the imported driver itself
is not generated by CubeMX. Keep them as a reviewed port; do not overwrite the
files with a fresh copy of the reference example.

## 11. Phase G — prove one frame before building a pipeline

Bring up the sensor in small milestones:

1. Drive XSHUT and initialize the sensor.
2. Read the device identity or complete the vendor initialization sequence.
3. Configure native 54 x 42 output.
4. Configure a 100 ms autonomous stream.
5. Observe one falling edge on PD9.
6. Start one complete I3C DMA frame transfer.
7. Wait on a ThreadX event posted by the HAL completion callback.
8. Acknowledge the sensor frame.
9. Run the transform and parse the metadata.
10. Print a small numeric summary before attempting the full ANSI map.

Logging stage boundaries is extremely useful. The first successful sequence
should look conceptually like:

```text
sensor event
DMA started
DMA completed
frame acknowledged
transform completed
metadata parsed
```

If it stops between two messages, investigate that boundary rather than
changing unrelated board jumpers.

## 12. Phase H — split acquisition and processing

The first implementation used one task for every operation. That was useful for
bring-up, but transform and terminal rendering can take long enough to delay the
next sensor read.

The working pipeline uses two tasks:

### 12.1 Acquisition task

- Priority 7.
- Waits for the PD9 sensor event.
- Obtains a free raw-frame slot.
- Starts I3C DMA into that slot.
- Waits for the completion event.
- Acknowledges the frame.
- Publishes the completed slot to the processing queue.

### 12.2 Processing task

- Priority 10.
- Waits for a completed raw-frame slot.
- Runs the VL53L9 transform.
- Parses status and metadata.
- Renders a terminal map.
- Queues the map for USB transmission.
- Returns the raw slot to the free queue.

### 12.3 Static raw-frame storage

The project uses three statically allocated raw slots, each 14,842 bytes.
Queues contain slot references, not complete frame copies.

```text
free-slot queue
      |
      v
acquisition task --I3C DMA--> raw slot
      |
      v
ready-slot queue
      |
      v
processing task --> transform/render --> release slot
```

There is no frame allocation in the steady-state sensor path. If processing
falls behind, the design can drop the oldest unclaimed work according to the
documented policy instead of blocking acquisition indefinitely or corrupting an
in-flight slot.

## 13. Phase I — build USB from the official N6 example outward

Before combining USB and the sensor, build and program ST's official example:

```text
STM32Cube_FW_N6_V1.4.0/
  Projects/NUCLEO-N657X0-Q/Applications/USBX/Ux_Device_CDC_ACM
```

Confirm that Windows creates a new COM port. The number is assigned by the host,
so do not hard-code an expectation such as COM7 or COM8.

This separate test answers a valuable question: can this board, cable, host,
connector, clock setup, and official firmware enumerate successfully? If yes,
compare the integrated project with the example instead of guessing at the
hardware.

The following N6-specific details from the official example were needed in the
integrated project:

- Enable VDDA, VDDIO2 through VDDIO5, and VDDUSB early in the FSBL.
- Select and enable the USB1 clock and PHY clock explicitly.
- Perform the USB HS controller/core/PHY reset and release sequence in the PCD
  MSP initialization.
- Clear and prepare the PCD handle before a new attach/start sequence.
- Configure endpoint FIFOs after `HAL_PCD_Init()`:
  - RX FIFO: `0x200` words.
  - EP0 TX FIFO: `0x10` words.
  - EP1 TX FIFO: `0x100` words.
  - EP2 TX FIFO: `0x20` words.
- Start the device only after a real Type-C cable-attach notification.

The EP1 FIFO size matters. A device can enumerate successfully and still fail
on the first large CDC write if the data endpoint FIFO is too small.

## 14. Phase J — use an asynchronous, statically allocated CDC transport

The final USB application is intentionally divided into control and data-plane
tasks.

### 14.1 USB lifecycle manager

The priority-8 manager owns:

- Attach and detach handling.
- USBX/PCD start and stop decisions.
- Session numbering.
- Worker start and stop.
- Transfer-timeout and recovery requests.
- Periodic health reporting.

### 14.2 TX worker

The priority-9 TX worker:

1. Receives a pointer to a static TX slot from its queue.
2. Submits `write_with_callback`.
3. Waits on a completion semaphore.
4. Checks completion status and the active session.
5. Releases the slot only when ownership is safe.
6. Starts the next queued transfer.

Only this worker submits bulk-IN transfers. Producers never call USBX directly.

### 14.3 RX worker

USBX owns bulk-OUT reception in callback mode. The receive callback copies the
data into a fixed RX slot and queues the slot reference. The RX worker validates
the session and delivers command bytes to the CLI outside callback context.

### 14.4 Static transport storage

The working configuration uses:

| Direction/use | Static storage |
|---|---|
| Short control/log TX | 8 slots x 768 bytes |
| Terminal-map TX | 2 slots x 48 KiB |
| RX | 16 slots x 512 bytes |

No heap or byte-pool allocation occurs for steady-state CDC packets. Queues
carry pointers to these slots. Each slot has an ownership state and session tag,
which prevents a late callback from an old USB connection from releasing memory
owned by a new connection.

If USB is unavailable, producers do not place stale data into an unbounded
backlog. The send request returns a controlled unavailable/full result, updates
a diagnostic counter, and lets the producer continue according to policy.

## 15. Phase K — add independent diagnostics

USB is one of the systems being developed, so it cannot be the only debug
channel.

The project adds a small USART1 logger on PE5/PE6 through the on-board ST-LINK
Virtual COM Port at 115200 baud. It records:

- FSBL entry and external-NOR mapping.
- Signed-image headers and vector values.
- Secure isolation and Non-Secure handover.
- Non-Secure startup stages.
- Peripheral and ThreadX initialization.
- Sensor frame stages and counters.
- USB attach, PCD, USBX, CDC, timeout, and recovery events.
- Secure and Non-Secure fault registers.

This channel remains useful when the user USB connector has not enumerated.
Keep normal high-rate frame data on USB and keep the ST-LINK logger focused on
state changes, faults, and rate-limited health messages.

## 16. Phase L — Secure handover and external-Flash boot additions

The multi-context skeleton required several manual corrections and diagnostic
additions:

- FSBL initializes XSPI2 and maps external NOR.
- The image-size calculation understands the signed image-header format used by
  the current signing tool.
- Secure code reads and caches the Non-Secure MSP and Reset_Handler before
  changing memory isolation.
- Secure code releases the required GPIOs, peripherals, and interrupts to the
  Non-Secure application.
- The handover uses the preserved Non-Secure vector values.
- Early startup traces show whether control reached each context.

These changes explain why it is important to test boot in layers:

1. FSBL log appears.
2. Secure log appears.
3. Non-Secure `Reset_Handler` log appears.
4. Non-Secure `main()` log appears.
5. ThreadX tasks start.

Do not start sensor debugging until the complete boot chain is proven.

## 17. Build, sign, and program

The repository includes two helper scripts:

- [Tools/build_and_sign.ps1](Tools/build_and_sign.ps1)
- [Tools/program_flash.ps1](Tools/program_flash.ps1)

### 17.1 Build and sign

From the directory above `project`, run:

```powershell
powershell.exe -ExecutionPolicy Bypass `
  -File .\project\Tools\build_and_sign.ps1
```

The script clean-builds the required contexts and creates trusted images under
`FlashImages`.

The current development signing flow uses the signing tool's `-nk` option. This
is suitable for local bring-up where no production key is provisioned. It is
not a production secure-boot policy. A deployable product needs an explicit key
provisioning, verification, anti-rollback, recovery, and lifecycle design.

### 17.2 Put the board in programming mode

For the tested board setup:

- BOOT0 jumper: 1-2.
- BOOT1 jumper: 2-3.

Reset the board, then run:

```powershell
powershell.exe -ExecutionPolicy Bypass `
  -File .\project\Tools\program_flash.ps1
```

The script writes and verifies:

```text
FSBL       -> 0x70000000
Secure     -> 0x70100000
NonSecure  -> 0x70180000
```

It intentionally does not perform a full external-Flash erase.

### 17.3 Return to boot mode

After successful programming:

- BOOT0 jumper: 1-2.
- BOOT1 jumper: 1-2.

Reset the board. Open the ST-LINK Virtual COM Port at 115200 baud before reset
if you want to see the entire boot trace.

## 18. A recommended reproduction order

Trying to integrate everything in one step creates too many possible failure
sources. Use these checkpoints:

### Checkpoint 1 — generated board project

- All contexts build.
- LEDs or another board-default function prove that the base project executes.

### Checkpoint 2 — external-Flash boot

- FSBL, Secure, and Non-Secure images are signed and programmed.
- The UART trace proves the complete boot sequence after reset.

### Checkpoint 3 — blocking sensor initialization

- The VL53L9CX initializes.
- A simple identity/status read succeeds.

### Checkpoint 4 — one asynchronous frame

- PD9 produces the expected falling-edge interrupt.
- I3C DMA starts and completes once.
- The frame transform succeeds.

### Checkpoint 5 — continuous acquisition

- Autonomous 100 ms frames run.
- Acquisition and processing have separate tasks.
- Raw-slot ownership remains valid under load.

### Checkpoint 6 — official USB example

- ST's N6 CDC example enumerates by itself.
- A terminal can open the host-assigned COM port.

### Checkpoint 7 — integrated USB

- Type-C attach starts USBX.
- CDC activates.
- A delayed plain-text test message is received.
- A short queued message is received.
- A full terminal map is received.

### Checkpoint 8 — recovery tests

- Unplug and reconnect USB.
- Close and reopen the terminal.
- Reset with the user USB cable already connected.
- Reset and connect it several seconds later.
- Verify that old-session packets are not reused.

## 19. Post-Generate Code audit

CubeMX regeneration is allowed and expected, but it must be followed by a
review. `Keep User Code` protects only recognized USER blocks; it does not
protect every generated, startup, middleware, or imported file.

After every Generate Code operation, check:

- FSBL still uses a 48 MHz digital-bypass HSE.
- FSBL still enables the HAL modules required for BSEC and XSPI.
- Shared STM32N6 HAL directories still contain the union of modules required by
  all contexts.
- Non-Secure CubeIDE includes the STM32N6 Nucleo BSP path.
- The independent UART HAL sources remain linked.
- Non-Secure C and C++ optimization remains `-O3`.
- PD9 is falling-edge EXTI9 and belongs to AppliNonSecure.
- Secure still marks EXTI line 9 and its NVIC target Non-Secure.
- I3C1 event/error and GPDMA channel 0/1/2 interrupts remain enabled.
- USBX CDC callback transmission remains enabled.
- The USBX internal class thread has a priority that cannot be starved by the
  sensor processing task.
- The USBX device manager has a 16 KiB stack.
- The USB-PD cable-detection task uses the project 8 KiB stack mapping rather
  than a generated 1 KiB default.
- The USB-PD pool remains 16 KiB and the USBX pool remains 32 KiB.
- The USB PHY reset/release code remains in the PCD MSP USER block.
- The endpoint FIFO sizes remain configured after `HAL_PCD_Init()`.
- The FSBL signed-image-size override remains intact.
- Imported VL53L9CX platform files have not been replaced by the unported
  reference versions.

The build script deliberately checks several of these invariants. Do not bypass
a guard simply to obtain a binary; investigate why the generated project no
longer matches the working configuration.

## 20. Failure guide

| Symptom | First places to inspect |
|---|---|
| FSBL logs appear but Secure does not | Signed Secure image, external-NOR address, image header, FSBL copy/load result |
| Secure logs appear but Non-Secure does not | Cached vector values, RISAF/RIF regions, Non-Secure MSP and Reset_Handler, handover attributes |
| Sensor initializes but first frame times out | PD9 routing, EXTI9 target state, falling-edge mode, GPIO ownership |
| I3C DMA start returns an error | Descriptor construction, combined-transfer frame, persistent object lifetime, DMA channel state |
| DMA completes but transform fails | Raw buffer size/alignment, complete transfer length, frame acknowledgement order, transform input metadata |
| A few frames work and then DMA fails | Raw-slot ownership, release queue, in-flight descriptor lifetime, stale event flags |
| A COM port never appears | HSE/USB clock, VDDUSB, PHY reset sequence, TCPP0203/UCPD attach, cable and connector |
| COM appears but first bulk write never completes | EP1 TX FIFO size, CDC callback mode, USBX internal thread priority |
| USB works until the sensor is busy | Thread priorities, CPU starvation, callback-to-worker handoff, queue ownership |
| Fault frame contains `0xEFEFEFEF` | ThreadX stack overflow or use of a stack pattern as an invalid return context |
| `CFSR_NS = 0x00100000` | Usage fault caused during the Non-Secure execution path; resolve the captured PC/LR against the ELF |

For a captured Non-Secure address:

```powershell
arm-none-eabi-addr2line.exe -a -f -C `
  -e .\project\AppliNonSecure\Debug\N6_AppliNonSecure.elf `
  0xADDRESS
```

## 21. What CubeMX generated and what was added manually

This distinction is important when learning the project.

### CubeMX is responsible for

- The board-level project skeleton.
- FSBL, Secure, Non-Secure, and loader context structure.
- Pin multiplexing and context selections recorded in `N6.ioc`.
- RCC and peripheral initialization skeletons.
- I3C1, GPDMA1, UCPD1, USB OTG HS, ThreadX, USBX, and USB-PD integration
  skeletons.
- Interrupt handlers and HAL callback entry points.
- CubeIDE project files and most middleware configuration files.

### Manual integration is responsible for

- Importing and licensing the VL53L9CX driver and transform middleware.
- Porting the sensor platform from the reference MCU to STM32N6.
- Persistent asynchronous I3C descriptors and buffers.
- Correct combined I3C register transfers and event acknowledgement.
- ThreadX event bridging from GPIO/I3C/DMA callbacks.
- Separate acquisition and processing tasks.
- Three fixed raw-frame slots and their ownership queues.
- The ANSI depth-map renderer.
- The USB lifecycle manager and independent RX/TX workers.
- Static CDC packet slots, session tagging, flow control, timeouts, and
  recovery.
- The official-example-derived N6 PHY and endpoint-FIFO setup.
- The independent ST-LINK logger and fault reports.
- Secure handover corrections and EXTI Non-Secure routing.
- FSBL image-header handling.
- Build, signing, and external-Flash programming scripts.

Some manual changes live in USER blocks. Others must live outside USER blocks
because they modify imported drivers, startup code, or generated glue that has
no suitable protected section. Those files are listed in detail in
[README.md](README.md) and [AGENTS.md](AGENTS.md).

## 22. Final learning checklist

Before calling a reconstruction successful, you should be able to explain:

- Why the application needs four contexts.
- Why the Non-Secure image is not simply executed from the same address at
  which it is stored.
- Why TrustZone ownership applies to GPIOs, peripherals, EXTI lines, and NVIC
  targets.
- Why asynchronous DMA descriptors cannot be local stack variables.
- Why interrupt callbacks should signal tasks instead of performing transforms
  or terminal rendering.
- Why acquisition has a more urgent ThreadX priority than processing.
- Why static frame slots avoid unpredictable allocation time.
- Why a USB device can enumerate but still fail on the first data transfer.
- Why Type-C attachment, USB-PD support, the PHY, USBX, and CDC are separate
  layers.
- Why a second diagnostic channel is essential while developing USB.
- Why every CubeMX Generate Code operation must be audited.
- Why a development image signed without a production key is not a complete
  secure-boot product.

If those points are clear, you have learned the most reusable engineering ideas
in this project rather than only copying its files.

