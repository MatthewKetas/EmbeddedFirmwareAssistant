import { HardwareWorkspace, SvdPeripheral, ModelConfig } from '../types/hardware';

export const INITIAL_MODELS: ModelConfig[] = [
  { id: 'qwen2.5-coder:32b', name: 'qwen2.5-coder:32b', provider: 'ollama', contextLength: '32k', isLocal: true },
  { id: 'deepseek-coder-v2:16b', name: 'deepseek-coder-v2:16b', provider: 'ollama', contextLength: '64k', isLocal: true },
  { id: 'codellama:34b', name: 'codellama:34b-instruct', provider: 'ollama', contextLength: '16k', isLocal: true },
  { id: 'python-rag-agent', name: 'python-backend-agent', provider: 'python_bridge', contextLength: '128k', isLocal: true },
  { id: 'gemini-2.5-flash', name: 'gemini-2.5-flash', provider: 'gemini', contextLength: '1M', isLocal: false },
];

export const INITIAL_WORKSPACES: HardwareWorkspace[] = [
  {
    id: 'stm32h7',
    name: 'STM32H7 / CM7',
    core: 'Arm Cortex-M7 @ 480MHz',
    badge: 'DS12110',
    iconType: 'chip',
    datasheets: ['RM0433 Rev 7 (Reference Manual)', 'DS12110 Rev 8 (Datasheet)', 'ES0392 (Errata Sheet)'],
    sessions: [
      {
        id: 'session-ltdc-dma2d',
        title: 'DMA2D & LTDC Config',
        workspaceId: 'stm32h7',
        targetMcu: 'STM32H743ZI',
        timestamp: '10:42 AM',
        messages: [
          {
            id: 'msg-1',
            sender: 'user',
            timestamp: '10:42 AM',
            content: 'How do I initialize the LTDC display controller clock on `STM32H743ZI` using `PLL3R`, and what are the register bitfield offsets for `LTDC->SSCR` and `LTDC->BPCR` for an 800x480 RGB565 panel? Please quote exact datasheet page numbers.'
          },
          {
            id: 'msg-2',
            sender: 'assistant',
            timestamp: '10:43 AM',
            citations: [
              {
                id: 'cite-1',
                title: 'STM32H743ZI Reference Manual RM0433',
                docCode: 'RM0433 Rev 7 · Sec 34.7.1, p. 1942',
                section: 'Section 34.7.1: LTDC Synchronization & Timing',
                page: 1942,
                type: 'reference_manual',
                verified: true,
                snippet: 'The synchronous timing parameter register (LTDC_SSCR) configures the horizontal and vertical synchronization width. HSW[11:0] occupies bits [27:16] and VSH[10:0] occupies bits [10:0]. Note: values loaded must be (Width - 1).'
              },
              {
                id: 'cite-2',
                title: 'STM32H742xI/G STM32H743xI/G Datasheet',
                docCode: 'DS12110 Rev 8 · p. 118 (Clock Tree)',
                section: 'Table 44 / Figure 18: Clock Tree Distribution',
                page: 118,
                type: 'datasheet',
                verified: true,
                snippet: 'The LCD-TFT (LTDC) clock domain source is selectable between PLL3R (default high-precision pixel clock) and PLL1Q via the RCC_D1CCIPR register. Bitfield CKPERSEL / LTDCSEL enables jitter-free fractional synthesis.'
              },
              {
                id: 'cite-3',
                title: 'STM32H742/743/753 Errata sheet',
                docCode: 'Errata ES0392 § 2.2.14 verified',
                section: 'Section 2.2.14: LTDC display flicker on high PLL3 jitter',
                page: 34,
                type: 'errata',
                verified: true,
                statusText: 'Errata ES0392 § 2.2.14 verified',
                snippet: 'When PLL3 operates with DIVN < 16, pixel clock jitter may exceed 150ps resulting in scanline displacement on capacitive panels. Workaround: Maintain PLL3 DIVN >= 160 with HSE pre-divider = 5.'
              }
            ],
            content: 'To clock the LTDC on the STM32H743ZI, PLL3R is routed via the RCC clock configuration register (RCC_D1CCIPR, DS12110 p. 118). For an 800x480 TFT LCD running at 60Hz (~33.3 MHz pixel clock requirement with HSE = 25 MHz), configure PLL3 divider parameters and calculate the horizontal & vertical timing periods according to the reference manual:',
            codeSnippets: [
              {
                filename: 'stm32h7_ltdc_init.c',
                language: 'c',
                code: `// 1. Select PLL3R as LTDC clock source (RM0433 p. 347, RCC_D1CCIPR)
RCC->D1CCIPR &= ~RCC_D1CCIPR_CKPERSEL;
RCC->D1CCIPR |= (0x02 << RCC_D1CCIPR_CKPERSEL_Pos);

// 2. Configure PLL3 for ~33.3 MHz pixel clock (HSE=25MHz: /5 * 160 / 24 = 33.33MHz)
RCC->PLLCKSELR |= RCC_PLLCKSELR_PLLSRC_HSE;
RCC->PLL3DIVR = (5 - 1)   << RCC_PLL3DIVR_DIVM3_Pos
              | (160 - 1) << RCC_PLL3DIVR_DIVN3_Pos
              | (24 - 1)  << RCC_PLL3DIVR_DIVR3_Pos;
RCC->PLLCFGR  |= RCC_PLLCFGR_DIVR3EN;
RCC->CR       |= RCC_CR_PLL3ON;
while (!(RCC->CR & RCC_CR_PLL3RDY));

// 3. Timing Parameters: 800x480 @ 60Hz Panel (RM0433 Sec 34.7.1, p. 1942)
#define HSW  40   /* Horizontal Sync Width */
#define VSH  9    /* Vertical Sync Height */
#define HBP  40   /* Horizontal Back Porch */
#define VBP  29   /* Vertical Back Porch */

// LTDC Synchronous Sync Configuration Register (LTDC_SSCR) -> 0x00270008
LTDC->SSCR = ((HSW - 1) << 16) | (VSH - 1);

// LTDC Back Porch Configuration Register (LTDC_BPCR) -> 0x004F0025
LTDC->BPCR = ((HSW + HBP - 1) << 16) | (VSH + VBP - 1);`
              }
            ],
            registerBreakdown: [
              {
                register: 'LTDC_SSCR',
                description: 'Bit 27:16 = HSW - 1 (Horizontal Sync Width - 40 - 1 = 39 = 0x27), Bit 10:0 = VSH - 1 (Vertical Sync Height - 9 - 1 = 8 = 0x08). Resulting hex: 0x00270008'
              },
              {
                register: 'LTDC_BPCR',
                description: 'Bit 27:16 = AHBP (Accumulated Horizontal Back Porch: HSW + HBP - 1 = 40 + 40 - 1 = 79 = 0x4F), Bit 10:0 = AVBP (Accumulated Vertical Back Porch: VSH + VBP - 1 = 9 + 29 - 1 = 37 = 0x25). Resulting hex: 0x004F0025'
              },
              {
                register: 'LTDC_AWCR',
                description: 'Bit 27:16 = AAW (Accumulated Active Width: 79 + 800 = 879 = 0x36F), Bit 10:0 = AAVH (Accumulated Active Height: 37 + 480 = 517 = 0x205).'
              },
              {
                register: 'LTDC_TWCR',
                description: 'Bit 27:16 = TOTALW (Total Width - 1: 879 + 40 HFP = 919 = 0x397), Bit 10:0 = TOTALH (Total Height - 1: 517 + 13 VFP = 530 = 0x212).'
              }
            ]
          }
        ]
      },
      {
        id: 'session-freertos-lptim',
        title: 'FreeRTOS Tickless LPTIM',
        workspaceId: 'stm32h7',
        targetMcu: 'STM32H743ZI',
        timestamp: 'Yesterday',
        messages: [
          {
            id: 'fr-1',
            sender: 'user',
            timestamp: 'Yesterday 3:15 PM',
            content: 'How should I configure LPTIM1 as the low-power tickless idle timer in FreeRTOS on STM32H7 while in Stop 2 mode?'
          },
          {
            id: 'fr-2',
            sender: 'assistant',
            timestamp: 'Yesterday 3:16 PM',
            citations: [
              {
                id: 'cite-lptim-1',
                title: 'STM32H7 Reference Manual RM0433',
                docCode: 'RM0433 Rev 7 · Sec 41.4.3, p. 2480',
                section: 'Section 41.4.3: LPTIM Asynchronous clock & Wakeup',
                page: 2480,
                type: 'reference_manual',
                verified: true,
                snippet: 'LPTIM1 is clocked from LSE (32.768 kHz) and can wake the Cortex-M7 core from Stop 0, Stop 1, and Stop 2 modes via EXTI line 52.'
              }
            ],
            content: 'To implement tickless idle with LPTIM1, select the LSE 32.768 kHz oscillator in RCC->D2CCIP2R. When entering idle, calculate the expected sleep ticks, program LPTIM1->ARR and enable the Compare Match interrupt before executing the `__WFI()` instruction.',
            codeSnippets: [
              {
                filename: 'FreeRTOS_lptim_tickless.c',
                language: 'c',
                code: `void vPortSuppressTicksAndSleep(TickType_t xExpectedIdleTime) {
  uint32_t ulReloadValue = (xExpectedIdleTime * 32768) / configTICK_RATE_HZ;
  LPTIM1->CR &= ~LPTIM_CR_ENABLE;
  LPTIM1->ARR = ulReloadValue - 1;
  LPTIM1->IER |= LPTIM_IER_ARRMIE;
  LPTIM1->CR |= LPTIM_CR_ENABLE | LPTIM_CR_SNGSTRT;
  __DSB();
  __WFI();
  __ISB();
}`
              }
            ]
          }
        ]
      },
      {
        id: 'session-rm0433-errata',
        title: 'RM0433 Reg Map & Errata',
        workspaceId: 'stm32h7',
        targetMcu: 'STM32H743ZI',
        timestamp: 'Oct 3',
        messages: [
          {
            id: 'rm-1',
            sender: 'user',
            timestamp: 'Oct 3 11:00 AM',
            content: 'What are the known silicon errata regarding AXI SRAM concurrent access by MDMA and Cortex-M7 cache coherency?'
          },
          {
            id: 'rm-2',
            sender: 'assistant',
            timestamp: 'Oct 3 11:02 AM',
            citations: [
              {
                id: 'cite-axi-1',
                title: 'STM32H7 Errata sheet ES0392',
                docCode: 'Errata ES0392 § 2.1.8',
                section: 'Section 2.1.8: MDMA burst access corrupted on AXI matrix contention',
                page: 19,
                type: 'errata',
                verified: true,
                statusText: 'Errata ES0392 § 2.1.8 verified',
                snippet: 'When D1 AXI matrix receives burst increments from MDMA while CM7 reads through DCache, speculative prefetches can stall the arbitration arbiter.'
              }
            ],
            content: 'Ensure all MDMA buffers in AXI SRAM (0x24000000) are configured via MPU as non-cacheable (`MPU_ACCESS_NOT_CACHEABLE` and `MPU_ACCESS_SHAREABLE`) to avoid cache invalidation overhead and matrix stalls.',
            codeSnippets: []
          }
        ]
      }
    ]
  },
  {
    id: 'esp32s3',
    name: 'ESP32-S3 Xtensa',
    core: 'Dual-Core Xtensa LX7 @ 240MHz',
    badge: 'TRM v1.4',
    iconType: 'cpu',
    datasheets: ['ESP32-S3 Technical Reference Manual v1.4', 'ESP32-S3 Datasheet v1.2'],
    sessions: [
      {
        id: 'session-esp32-usb',
        title: 'USB-OTG CDC + Partition',
        workspaceId: 'esp32s3',
        targetMcu: 'ESP32-S3-WROOM-1',
        timestamp: 'Sep 29',
        messages: [
          {
            id: 'esp-1',
            sender: 'user',
            timestamp: 'Sep 29 4:20 PM',
            content: 'How do I initialize the internal USB-OTG peripheral for TinyUSB CDC without conflicting with the hardware USB-Serial-JTAG bridge?'
          },
          {
            id: 'esp-2',
            sender: 'assistant',
            timestamp: 'Sep 29 4:21 PM',
            citations: [
              {
                id: 'cite-esp-usb-1',
                title: 'ESP32-S3 TRM v1.4',
                docCode: 'TRM v1.4 · Ch 29 USB-OTG, p. 812',
                section: 'Section 29.3: USB PHY Routing & GPIO matrix',
                page: 812,
                type: 'reference_manual',
                verified: true,
                snippet: 'GPIO19 (D-) and GPIO20 (D+) can be routed either to USB_SERIAL_JTAG or USB_OTG via USB_WRAP_REG.'
              }
            ],
            content: 'Set `USB_WRAP_OTG_PHY_SEL` to 1 in the `USB_WRAP_OTG_CONF_REG` register to route the built-in USB PHY directly to the USB OTG controller instead of the hardware USB-Serial-JTAG engine.',
            codeSnippets: [
              {
                filename: 'esp32s3_usb_phy.c',
                language: 'c',
                code: `// Enable internal PHY for USB OTG
CLEAR_PERI_REG_MASK(USB_WRAP_OTG_CONF_REG, USB_WRAP_USB_PAD_ENABLE);
SET_PERI_REG_MASK(USB_WRAP_OTG_CONF_REG, USB_WRAP_PHY_SEL);
// Initialize TinyUSB stack
tinyusb_config_t const tusb_cfg = {
    .device_descriptor = NULL,
    .string_descriptor = NULL,
    .external_phy = false,
};
ESP_ERROR_CHECK(tinyusb_driver_install(&tusb_cfg));`
              }
            ]
          }
        ]
      }
    ]
  },
  {
    id: 'nrf52840',
    name: 'Nordic nRF52840',
    core: 'Arm Cortex-M4F @ 64MHz',
    badge: 'PS v1.3',
    iconType: 'radio',
    datasheets: ['nRF52840 Product Specification v1.3', 'S140 SoftDevice v7.2.0 Specification'],
    sessions: [
      {
        id: 'session-nrf-ble',
        title: 'BLE SoftDevice RAM Start',
        workspaceId: 'nrf52840',
        targetMcu: 'nRF52840-QIAA',
        timestamp: 'Sep 25',
        messages: [
          {
            id: 'nrf-1',
            sender: 'user',
            timestamp: 'Sep 25 1:10 PM',
            content: 'How do I calculate the required APP_RAM_BASE for Nordic S140 SoftDevice with 4 concurrent central links and ATT MTU = 247?'
          },
          {
            id: 'nrf-2',
            sender: 'assistant',
            timestamp: 'Sep 25 1:12 PM',
            citations: [
              {
                id: 'cite-nrf-sd-1',
                title: 'Nordic S140 SoftDevice Specification',
                docCode: 'SDS v7.2.0 · Table 12, p. 48',
                section: 'Memory Resource Requirements',
                page: 48,
                type: 'reference_manual',
                verified: true,
                snippet: 'Base S140 RAM footprint is 0x1400 (5120 bytes) + link buffer allocation: (Max_MTU + 32) * link_count.'
              }
            ],
            content: 'Run `sd_ble_enable(&ram_start)` with a provisional memory address. If the buffer is insufficient, the SoftDevice returns `NRF_ERROR_NO_MEM` and populates `ram_start` with the exact required memory address.',
            codeSnippets: [
              {
                filename: 'nrf_ble_ram_calc.c',
                language: 'c',
                code: `uint32_t ram_start = 0x20002A98;
uint32_t err_code = sd_ble_enable(&ram_start);
if (err_code == NRF_ERROR_NO_MEM) {
    // ram_start is now updated with the exact minimum address needed
    NRF_LOG_WARNING("SoftDevice requires RAM start: 0x%08X", ram_start);
}`
              }
            ]
          }
        ]
      }
    ]
  },
  {
    id: 'tms320f28379d',
    name: 'TI TMS320F28379D',
    core: 'Dual C28x DSP @ 200MHz',
    badge: 'C2000',
    iconType: 'dsp',
    datasheets: ['TMS320F2837xD Technical Reference Manual SPRUHM8I', 'TMS320F28379D Datasheet SPRS880O'],
    sessions: [
      {
        id: 'session-ti-epwm',
        title: 'ePWM Dead-Band Sync',
        workspaceId: 'tms320f28379d',
        targetMcu: 'TMS320F28379D',
        timestamp: 'Sep 18',
        messages: [
          {
            id: 'ti-1',
            sender: 'user',
            timestamp: 'Sep 18 9:45 AM',
            content: 'What is the dead-band configuration register setup in ePWM1 for complementary active-high complementary PWM (AHC)?'
          },
          {
            id: 'ti-2',
            sender: 'assistant',
            timestamp: 'Sep 18 9:47 AM',
            citations: [
              {
                id: 'cite-ti-epwm-1',
                title: 'SPRUHM8I Technical Reference Manual',
                docCode: 'TRM SPRUHM8I · Sec 15.6, p. 1824',
                section: 'Section 15.6: Dead-Band Submodule (DB)',
                page: 1824,
                type: 'reference_manual',
                verified: true,
                snippet: 'DBCTL register controls polarity, input selection, and output mode. Bit OUT_MODE = 3 (both rising and falling edge delays enabled).'
              }
            ],
            content: 'Set `EPwm1Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;` and `EPwm1Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;`. Program `DBRED` and `DBFED` with the clock tick dead-band period.',
            codeSnippets: [
              {
                filename: 'ti_c2000_epwm_db.c',
                language: 'c',
                code: `EPwm1Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE; // 0x3
EPwm1Regs.DBCTL.bit.POLSEL   = DB_ACTV_HIC;     // 0x2 (Active High Complementary)
EPwm1Regs.DBCTL.bit.IN_MODE  = DBA_ALL;         // 0x0 (EPWMxA is input for both edges)
EPwm1Regs.DBRED.bit.DBRED    = 100;             // 100 * TBCLK = 1.0 us dead-time
EPwm1Regs.DBFED.bit.DBFED    = 100;`
              }
            ]
          }
        ]
      }
    ]
  }
];

export const MOCK_SVD_PERIPHERALS: SvdPeripheral[] = [
  {
    name: 'LTDC',
    baseAddress: '0x50001000',
    description: 'LCD-TFT Display Controller',
    registers: [
      {
        name: 'LTDC_SSCR',
        offset: '0x0008',
        size: 32,
        description: 'LTDC Synchronization Size Configuration Register',
        resetValue: '0x00000000',
        fields: [
          { name: 'HSW', bitStart: 16, bitEnd: 27, access: 'RW', resetValue: 0, description: 'Horizontal Synchronization Width (in units of pixel clock - 1)' },
          { name: 'VSH', bitStart: 0, bitEnd: 10, access: 'RW', resetValue: 0, description: 'Vertical Synchronization Height (in units of horizontal lines - 1)' }
        ]
      },
      {
        name: 'LTDC_BPCR',
        offset: '0x000C',
        size: 32,
        description: 'LTDC Back Porch Configuration Register',
        resetValue: '0x00000000',
        fields: [
          { name: 'AHBP', bitStart: 16, bitEnd: 27, access: 'RW', resetValue: 0, description: 'Accumulated Horizontal Back Porch (HSW + HBP - 1)' },
          { name: 'AVBP', bitStart: 0, bitEnd: 10, access: 'RW', resetValue: 0, description: 'Accumulated Vertical Back Porch (VSH + VBP - 1)' }
        ]
      },
      {
        name: 'LTDC_AWCR',
        offset: '0x0010',
        size: 32,
        description: 'LTDC Active Width Configuration Register',
        resetValue: '0x00000000',
        fields: [
          { name: 'AAW', bitStart: 16, bitEnd: 27, access: 'RW', resetValue: 0, description: 'Accumulated Active Width (AHBP + Active Width)' },
          { name: 'AAH', bitStart: 0, bitEnd: 10, access: 'RW', resetValue: 0, description: 'Accumulated Active Height (AVBP + Active Height)' }
        ]
      },
      {
        name: 'LTDC_TWCR',
        offset: '0x0014',
        size: 32,
        description: 'LTDC Total Width Configuration Register',
        resetValue: '0x00000000',
        fields: [
          { name: 'TOTALW', bitStart: 16, bitEnd: 27, access: 'RW', resetValue: 0, description: 'Total Width (AAW + HFP)' },
          { name: 'TOTALH', bitStart: 0, bitEnd: 10, access: 'RW', resetValue: 0, description: 'Total Height (AAH + VFP)' }
        ]
      },
      {
        name: 'LTDC_GCR',
        offset: '0x0018',
        size: 32,
        description: 'LTDC Global Control Register',
        resetValue: '0x00002220',
        fields: [
          { name: 'LTDCEN', bitStart: 0, bitEnd: 0, access: 'RW', resetValue: 0, description: 'LCD-TFT controller enable bit' },
          { name: 'DBW', bitStart: 4, bitEnd: 6, access: 'RW', resetValue: 2, description: 'Dither Blue Width' },
          { name: 'DGW', bitStart: 8, bitEnd: 10, access: 'RW', resetValue: 2, description: 'Dither Green Width' },
          { name: 'DRW', bitStart: 12, bitEnd: 14, access: 'RW', resetValue: 2, description: 'Dither Red Width' },
          { name: 'DEN', bitStart: 16, bitEnd: 16, access: 'RW', resetValue: 0, description: 'Dither Enable' },
          { name: 'PCPOL', bitStart: 28, bitEnd: 28, access: 'RW', resetValue: 0, description: 'Pixel Clock Polarity' },
          { name: 'DEPOL', bitStart: 29, bitEnd: 29, access: 'RW', resetValue: 0, description: 'Data Enable Polarity' },
          { name: 'VSPOL', bitStart: 30, bitEnd: 30, access: 'RW', resetValue: 0, description: 'Vertical Synchronization Polarity' },
          { name: 'HSPOL', bitStart: 31, bitEnd: 31, access: 'RW', resetValue: 0, description: 'Horizontal Synchronization Polarity' }
        ]
      }
    ]
  },
  {
    name: 'RCC',
    baseAddress: '0x58024400',
    description: 'Reset and Clock Control',
    registers: [
      {
        name: 'RCC_D1CCIPR',
        offset: '0x004C',
        size: 32,
        description: 'RCC Domain 1 Kernel Clock Configuration Register',
        resetValue: '0x00000000',
        fields: [
          { name: 'FMCSEL', bitStart: 0, bitEnd: 1, access: 'RW', resetValue: 0, description: 'FMC kernel clock source selection' },
          { name: 'QSPISEL', bitStart: 4, bitEnd: 5, access: 'RW', resetValue: 0, description: 'QUADSPI kernel clock source selection' },
          { name: 'CKPERSEL', bitStart: 16, bitEnd: 17, access: 'RW', resetValue: 0, description: 'Peripherals clock source (00: HSI, 01: CSI, 10: HSE, 11: PLL3R for LTDC)' }
        ]
      },
      {
        name: 'RCC_PLL3DIVR',
        offset: '0x0038',
        size: 32,
        description: 'RCC PLL3 Dividers Configuration Register',
        resetValue: '0x01010280',
        fields: [
          { name: 'DIVM3', bitStart: 0, bitEnd: 5, access: 'RW', resetValue: 32, description: 'Prescaler for PLL3 (1 to 63)' },
          { name: 'DIVN3', bitStart: 8, bitEnd: 16, access: 'RW', resetValue: 128, description: 'Multiplication factor for PLL3 VCO (4 to 512)' },
          { name: 'DIVP3', bitStart: 16, bitEnd: 22, access: 'RW', resetValue: 2, description: 'PLL3 DIVP division factor' },
          { name: 'DIVQ3', bitStart: 24, bitEnd: 30, access: 'RW', resetValue: 2, description: 'PLL3 DIVQ division factor' },
          { name: 'DIVR3', bitStart: 24, bitEnd: 30, access: 'RW', resetValue: 2, description: 'PLL3 DIVR division factor (for LTDC pixel clock)' }
        ]
      }
    ]
  }
];
