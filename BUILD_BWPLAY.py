#!/usr/bin/env python3
from pathlib import Path

ORG = 0x0100
BDOS = 0x0005
DAC_PORT = 0x50
BUFFER = 0x1000
STACK_TOP = 0x0FF0
BMC_RATE = 2500
DELAY1_COUNT = 48
DELAY2_COUNT = 42

OUT = Path('/mnt/data/Bondwell_BMC_Smooth10K')


class Builder:
    def __init__(self, org: int = ORG):
        self.org = org
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fix16: list[tuple[int, str]] = []
        self.fix8: list[tuple[int, str]] = []

    @property
    def pc(self) -> int:
        return self.org + len(self.code)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f'duplicate label: {name}')
        self.labels[name] = self.pc

    def b(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def w(self, value: int) -> None:
        self.b(value, value >> 8)

    def addr(self, label: str) -> None:
        position = len(self.code)
        self.w(0)
        self.fix16.append((position, label))

    def op_addr(self, opcode: int, label: str) -> None:
        self.b(opcode)
        self.addr(label)

    def jr(self, opcode: int, label: str) -> None:
        self.b(opcode)
        position = len(self.code)
        self.b(0)
        self.fix8.append((position, label))

    def resolve(self) -> bytes:
        for position, label in self.fix16:
            address = self.labels[label]
            self.code[position] = address & 0xFF
            self.code[position + 1] = (address >> 8) & 0xFF

        for position, label in self.fix8:
            target = self.labels[label]
            next_address = self.org + position + 1
            displacement = target - next_address
            if not -128 <= displacement <= 127:
                raise ValueError(f'JR to {label} is out of range: {displacement}')
            self.code[position] = displacement & 0xFF

        return bytes(self.code)


b = Builder()


def call_abs(address: int) -> None:
    b.b(0xCD)
    b.w(address)


def call_label(label: str) -> None:
    b.op_addr(0xCD, label)


def jp(label: str) -> None:
    b.op_addr(0xC3, label)


def jp_z(label: str) -> None:
    b.op_addr(0xCA, label)


def jp_nz(label: str) -> None:
    b.op_addr(0xC2, label)


def jp_c(label: str) -> None:
    b.op_addr(0xDA, label)


def jp_nc(label: str) -> None:
    b.op_addr(0xD2, label)


def ld_de_label(label: str) -> None:
    b.b(0x11)
    b.addr(label)


def ld_hl_label(label: str) -> None:
    b.b(0x21)
    b.addr(label)


def ld_a_mem_label(label: str) -> None:
    b.b(0x3A)
    b.addr(label)


def ld_mem_a_label(label: str) -> None:
    b.b(0x32)
    b.addr(label)


def ld_hl_mem_label(label: str) -> None:
    b.b(0x2A)
    b.addr(label)


def ld_mem_hl_label(label: str) -> None:
    b.b(0x22)
    b.addr(label)


def bdos(function: int) -> None:
    b.b(0x0E, function)  # LD C,function
    call_abs(BDOS)


def print_label(label: str) -> None:
    ld_de_label(label)
    bdos(9)


# ---------------------------------------------------------------------------
# Main program
# ---------------------------------------------------------------------------
b.label('START')
b.b(0x31); b.w(STACK_TOP)                  # LD SP,STACK_TOP
print_label('MSG_TITLE')
print_label('MSG_PROMPT')
ld_de_label('INPUT_BUFFER')
bdos(10)                                   # buffered console input
print_label('MSG_CRLF')

ld_a_mem_label('INPUT_COUNT')
b.b(0xB7)                                  # OR A
b.op_addr(0xCA, 'EXIT_TO_CPM')              # JP Z (blank line exits)

call_label('INIT_FCB')
call_label('PARSE_FILENAME')
jp_c('BAD_NAME')

print_label('MSG_LOADING')
ld_de_label('FCB')
bdos(15)                                   # open file
b.b(0x3C)                                  # INC A: FFH -> 00H
jp_z('OPEN_ERROR')

b.b(0x21); b.w(BUFFER)                     # LD HL,BUFFER

b.label('LOAD_LOOP')
# Ensure the next 128-byte DMA record remains below the BDOS entry point.
b.b(0xE5)                                  # PUSH HL
b.b(0x01); b.w(0x0080)                     # LD BC,128
b.b(0x09)                                  # ADD HL,BC
b.b(0xED, 0x5B, 0x06, 0x00)               # LD DE,(0006H)
b.b(0xB7)                                  # OR A (clear carry)
b.b(0xED, 0x52)                            # SBC HL,DE
b.b(0xE1)                                  # POP HL
jp_nc('FILE_TOO_LARGE')

# Set DMA address to HL.
b.b(0xE5)                                  # PUSH HL
b.b(0x54, 0x5D)                            # LD D,H / LD E,L
bdos(26)
b.b(0xE1)                                  # POP HL

# Read one sequential CP/M record.
b.b(0xE5)                                  # PUSH HL
ld_de_label('FCB')
bdos(20)
b.b(0xE1)                                  # POP HL
b.b(0xB7)                                  # OR A
b.jr(0x20, 'LOAD_DONE')                    # JR NZ,LOAD_DONE
b.b(0x11); b.w(0x0080)                     # LD DE,128
b.b(0x19)                                  # ADD HL,DE
jp('LOAD_LOOP')

b.label('LOAD_DONE')
ld_mem_hl_label('LOAD_END')
ld_de_label('FCB')
bdos(16)                                   # close

# Check signature BWA4.
b.b(0x21); b.w(BUFFER)                     # LD HL,BUFFER
for character in b'BWA4':
    b.b(0x7E, 0xFE, character)             # LD A,(HL) / CP character
    jp_nz('BAD_FILE')
    b.b(0x23)                              # INC HL

# Rate must be 2500 source samples/second.
b.b(0x2A); b.w(BUFFER + 4)                 # LD HL,(BUFFER+4)
b.b(0x11); b.w(BMC_RATE)                   # LD DE,2500
b.b(0xB7, 0xED, 0x52)                     # OR A / SBC HL,DE
jp_nz('UNSUPPORTED_FILE')

# Packed payload byte count must be non-zero.
b.b(0x2A); b.w(BUFFER + 6)                 # LD HL,(payload count)
b.b(0x7C, 0xB5)                            # LD A,H / OR L
jp_z('BAD_FILE')

# The total small/large delta values must match this fixed-cycle player.
b.b(0x3A); b.w(BUFFER + 10)                # LD A,(small total delta)
b.b(0xFE, 0x06)
jp_nz('UNSUPPORTED_FILE')
b.b(0x3A); b.w(BUFFER + 11)                # LD A,(large total delta)
b.b(0xFE, 0x22)
jp_nz('UNSUPPORTED_FILE')

# Confirm BUFFER+16+payload_count does not exceed the records actually read.
b.b(0x2A); b.w(BUFFER + 6)                 # LD HL,(payload count)
b.b(0x11); b.w(BUFFER + 16)                # LD DE,BUFFER+16
b.b(0x19)                                  # ADD HL,DE
b.b(0xED, 0x5B)                            # LD DE,(LOAD_END)
b.addr('LOAD_END')
b.b(0xB7, 0xED, 0x52)                     # OR A / SBC HL,DE
b.jr(0x38, 'PAYLOAD_OK')                   # JR C
b.jr(0x28, 'PAYLOAD_OK')                   # JR Z
jp('BAD_FILE')

b.label('PAYLOAD_OK')
print_label('MSG_PLAY')

# Move packed byte count to alternate BC.
b.b(0x2A); b.w(BUFFER + 6)                 # LD HL,(payload count)
b.b(0x4D, 0x44)                            # LD C,L / LD B,H
b.b(0xD9)                                  # EXX

# Playback state: main HL is the payload pointer and E is the DAC level.
b.b(0x21); b.w(BUFFER + 16)                # LD HL,first payload byte
b.b(0x3A); b.w(BUFFER + 9)                 # LD A,(initial level)
b.b(0x5F)                                  # LD E,A
b.b(0xF3)                                  # DI

b.label('NEXT_BYTE')
b.b(0x4E, 0x23, 0x06, 0x04)              # LD C,(HL); INC HL; LD B,4

b.label('CODE_LOOP')
# Extract the next two-bit code from bits 7-6, then shift the packed byte.
b.b(0x79, 0xE6, 0xC0, 0x07, 0x07)        # LD A,C; AND C0H; RLCA; RLCA
b.b(0xCB, 0x21, 0xCB, 0x21)              # SLA C; SLA C

# Bit 1 is direction. Bit 0 selects small/large within that direction:
# 00=-34, 01=-6, 10=+6, 11=+34 per source sample.
b.b(0xCB, 0x4F)                            # BIT 1,A
b.jr(0x20, 'CODE_UP')                      # JR NZ,CODE_UP
b.b(0xCB, 0x47)                            # BIT 0,A
b.jr(0x20, 'SMALL_DOWN')                   # JR NZ,SMALL_DOWN
jp('LARGE_DOWN')

b.label('CODE_UP')
b.b(0xCB, 0x47)                            # BIT 0,A
jp_nz('LARGE_UP')                         # JP NZ,LARGE_UP
jp('SMALL_UP')

# Each source sample is rendered as four evenly spaced DAC outputs. This
# first-order interpolation moves the first DAC stair-step image to about 10 kHz.
b.label('LARGE_DOWN')
b.b(0x7B, 0xD6, 0x08, 0xD3, DAC_PORT)     # LD A,E; SUB 8; OUT
b.b(0x16, 23)
b.label('LD_DLY1')
b.b(0x15)
b.jr(0x20, 'LD_DLY1')
b.b(0x00, 0x00, 0x00)                     # 3 NOPs: 400-cycle spacing
b.b(0xD6, 0x09, 0xD3, DAC_PORT)           # SUB 9; OUT
b.b(0x16, 23)
b.label('LD_DLY2')
b.b(0x15)
b.jr(0x20, 'LD_DLY2')
b.b(0x00, 0x00, 0x00)
b.b(0xD6, 0x08, 0xD3, DAC_PORT)           # SUB 8; OUT
b.b(0x16, 23)
b.label('LD_DLY3')
b.b(0x15)
b.jr(0x20, 'LD_DLY3')
b.b(0x00, 0x00, 0x00)
b.b(0xD6, 0x09, 0xD3, DAC_PORT, 0x5F)     # SUB 9; OUT; LD E,A
b.b(0x16, 16)
b.label('LD_DLY4')
b.b(0x15)
b.jr(0x20, 'LD_DLY4')
b.b(0x00)                                  # final interval compensation
jp('AFTER_SAMPLE')

b.label('SMALL_DOWN')
b.b(0x7B, 0xD6, 0x01, 0xD3, DAC_PORT)     # LD A,E; SUB 1; OUT
b.b(0x16, 23)
b.label('SD_DLY1')
b.b(0x15)
b.jr(0x20, 'SD_DLY1')
b.b(0x00, 0x00, 0x00)
b.b(0xD6, 0x02, 0xD3, DAC_PORT)           # SUB 2; OUT
b.b(0x16, 23)
b.label('SD_DLY2')
b.b(0x15)
b.jr(0x20, 'SD_DLY2')
b.b(0x00, 0x00, 0x00)
b.b(0xD6, 0x01, 0xD3, DAC_PORT)           # SUB 1; OUT
b.b(0x16, 23)
b.label('SD_DLY3')
b.b(0x15)
b.jr(0x20, 'SD_DLY3')
b.b(0x00, 0x00, 0x00)
b.b(0xD6, 0x02, 0xD3, DAC_PORT, 0x5F)     # SUB 2; OUT; LD E,A
b.b(0x16, 16)
b.label('SD_DLY4')
b.b(0x15)
b.jr(0x20, 'SD_DLY4')
b.b(0x00)
jp('AFTER_SAMPLE')

b.label('SMALL_UP')
b.b(0x7B, 0xC6, 0x01, 0xD3, DAC_PORT)     # LD A,E; ADD 1; OUT
b.b(0x16, 23)
b.label('SU_DLY1')
b.b(0x15)
b.jr(0x20, 'SU_DLY1')
b.b(0x00, 0x00, 0x00)
b.b(0xC6, 0x02, 0xD3, DAC_PORT)           # ADD 2; OUT
b.b(0x16, 23)
b.label('SU_DLY2')
b.b(0x15)
b.jr(0x20, 'SU_DLY2')
b.b(0x00, 0x00, 0x00)
b.b(0xC6, 0x01, 0xD3, DAC_PORT)           # ADD 1; OUT
b.b(0x16, 23)
b.label('SU_DLY3')
b.b(0x15)
b.jr(0x20, 'SU_DLY3')
b.b(0x00, 0x00, 0x00)
b.b(0xC6, 0x02, 0xD3, DAC_PORT, 0x5F)     # ADD 2; OUT; LD E,A
b.b(0x16, 16)
b.label('SU_DLY4')
b.b(0x15)
b.jr(0x20, 'SU_DLY4')
b.b(0x00)
jp('AFTER_SAMPLE')

b.label('LARGE_UP')
b.b(0x7B, 0xC6, 0x08, 0xD3, DAC_PORT)     # LD A,E; ADD 8; OUT
b.b(0x16, 23)
b.label('LU_DLY1')
b.b(0x15)
b.jr(0x20, 'LU_DLY1')
b.b(0x00, 0x00, 0x00)
b.b(0xC6, 0x09, 0xD3, DAC_PORT)           # ADD 9; OUT
b.b(0x16, 23)
b.label('LU_DLY2')
b.b(0x15)
b.jr(0x20, 'LU_DLY2')
b.b(0x00, 0x00, 0x00)
b.b(0xC6, 0x08, 0xD3, DAC_PORT)           # ADD 8; OUT
b.b(0x16, 23)
b.label('LU_DLY3')
b.b(0x15)
b.jr(0x20, 'LU_DLY3')
b.b(0x00, 0x00, 0x00)
b.b(0xC6, 0x09, 0xD3, DAC_PORT, 0x5F)     # ADD 9; OUT; LD E,A
b.b(0x16, 16)
b.label('LU_DLY4')
b.b(0x15)
b.jr(0x20, 'LU_DLY4')
b.b(0x00)
jp('AFTER_SAMPLE')

b.label('AFTER_SAMPLE')
b.b(0x05)                                  # DEC B
jp_nz('CODE_LOOP')                         # JP NZ,CODE_LOOP

# Decrement packed byte count in alternate BC.
b.b(0xD9, 0x0B, 0x78, 0xB1, 0xD9)       # EXX; DEC BC; LD A,B; OR C; EXX
jp_nz('NEXT_BYTE')                         # JP NZ

b.b(0xFB)                                  # EI
b.b(0x3E, 0x80, 0xD3, DAC_PORT)           # centre DAC
print_label('MSG_DONE')
jp('EXIT_TO_CPM')

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
b.label('BAD_NAME')
print_label('MSG_BAD_NAME')
jp('EXIT_TO_CPM')

b.label('OPEN_ERROR')
print_label('MSG_OPEN_ERROR')
jp('EXIT_TO_CPM')

b.label('FILE_TOO_LARGE')
ld_de_label('FCB')
bdos(16)
print_label('MSG_TOO_LARGE')
jp('EXIT_TO_CPM')

b.label('BAD_FILE')
print_label('MSG_BAD_FILE')
jp('EXIT_TO_CPM')

b.label('UNSUPPORTED_FILE')
print_label('MSG_UNSUPPORTED')
jp('EXIT_TO_CPM')

b.label('EXIT_TO_CPM')
b.b(0xC3, 0x00, 0x00)                     # JP 0000H

# ---------------------------------------------------------------------------
# Initialise the FCB to drive 0, space-filled filename/extension, zero metadata.
# ---------------------------------------------------------------------------
b.label('INIT_FCB')
ld_hl_label('FCB')
b.b(0x06, 36)                              # LD B,36
b.b(0xAF)                                  # XOR A
b.label('CLEAR_FCB_LOOP')
b.b(0x77, 0x23)                            # LD (HL),A / INC HL
b.jr(0x10, 'CLEAR_FCB_LOOP')               # DJNZ
ld_hl_label('FCB_NAME')
b.b(0x06, 11, 0x3E, 0x20)                 # LD B,11 / LD A,' '
b.label('SPACE_FCB_LOOP')
b.b(0x77, 0x23)
b.jr(0x10, 'SPACE_FCB_LOOP')
b.b(0xC9)

# ---------------------------------------------------------------------------
# Parse [drive:]filename[.extension] from INPUT_BUFFER into FCB.
# Missing extension defaults to BMC. Returns carry set on invalid input.
# ---------------------------------------------------------------------------
b.label('PARSE_FILENAME')
ld_a_mem_label('INPUT_COUNT')
b.b(0x47)                                  # LD B,A
ld_hl_label('INPUT_TEXT')

# Optional drive prefix A: through P:.
b.b(0x78, 0xFE, 0x02)                     # LD A,B / CP 2
b.jr(0x38, 'NO_DRIVE')                     # JR C
b.b(0x23, 0x7E, 0x2B, 0xFE, ord(':'))    # INC HL; LD A,(HL); DEC HL; CP ':'
b.jr(0x20, 'NO_DRIVE')                     # JR NZ
b.b(0x7E)                                  # LD A,(HL)
call_label('UPCASE')
b.b(0xFE, ord('A'))
jp_c('PARSE_FAIL')
b.b(0xFE, ord('P') + 1)
jp_nc('PARSE_FAIL')
b.b(0xD6, ord('A') - 1)                   # SUB 40H -> A:=1
ld_mem_a_label('FCB')
b.b(0x23, 0x23, 0x05, 0x05)              # INC HL twice / DEC B twice

b.label('NO_DRIVE')
ld_de_label('FCB_NAME')
b.b(0x0E, 0x00)                            # LD C,0 name length

b.label('NAME_LOOP')
b.b(0x78, 0xB7)                            # LD A,B / OR A
b.jr(0x28, 'NO_EXTENSION')                 # JR Z
b.b(0x7E, 0xFE, ord('.'))                 # LD A,(HL) / CP '.'
b.jr(0x28, 'START_EXTENSION')
b.b(0x79, 0xFE, 0x08)                     # LD A,C / CP 8
jp_nc('PARSE_FAIL')
b.b(0x7E)
call_label('UPCASE')
call_label('VALID_CHAR')
jp_c('PARSE_FAIL')
b.b(0x12, 0x13, 0x23, 0x05, 0x0C)       # LD (DE),A; INC DE/HL; DEC B; INC C
b.jr(0x18, 'NAME_LOOP')

b.label('START_EXTENSION')
b.b(0x79, 0xB7)                            # LD A,C / OR A
jp_z('PARSE_FAIL')
b.b(0x23, 0x05)                            # INC HL / DEC B
ld_de_label('FCB_EXT')
b.b(0x0E, 0x00)                            # LD C,0 extension length

b.label('EXTENSION_LOOP')
b.b(0x78, 0xB7)                            # LD A,B / OR A
b.jr(0x28, 'EXTENSION_DONE')
b.b(0x79, 0xFE, 0x03)                     # LD A,C / CP 3
jp_nc('PARSE_FAIL')
b.b(0x7E)
call_label('UPCASE')
call_label('VALID_CHAR')
jp_c('PARSE_FAIL')
b.b(0x12, 0x13, 0x23, 0x05, 0x0C)
b.jr(0x18, 'EXTENSION_LOOP')

b.label('EXTENSION_DONE')
b.b(0x79, 0xB7)                            # LD A,C / OR A
b.jr(0x28, 'SET_DEFAULT_EXTENSION')        # empty extension after dot -> BMC
b.b(0xB7, 0xC9)                            # OR A (clear carry) / RET

b.label('NO_EXTENSION')
b.b(0x79, 0xB7)                            # name length non-zero?
jp_z('PARSE_FAIL')

b.label('SET_DEFAULT_EXTENSION')
ld_hl_label('DEFAULT_EXTENSION')
ld_de_label('FCB_EXT')
b.b(0x01); b.w(3)                          # LD BC,3
b.b(0xED, 0xB0)                            # LDIR
b.b(0xB7, 0xC9)                            # OR A / RET

b.label('PARSE_FAIL')
b.b(0x37, 0xC9)                            # SCF / RET

# Convert ASCII lowercase A to uppercase; preserve other characters.
b.label('UPCASE')
b.b(0xFE, ord('a'), 0xD8)                 # CP 'a' / RET C
b.b(0xFE, ord('z') + 1, 0xD0)             # CP 'z'+1 / RET NC
b.b(0xD6, 0x20, 0xC9)                     # SUB 20H / RET

# Accept visible CP/M filename characters except separators and wildcards.
b.label('VALID_CHAR')
b.b(0xFE, 0x21)
b.jr(0x38, 'INVALID_CHAR')                 # below '!'
b.b(0xFE, 0x7F)
b.jr(0x30, 'INVALID_CHAR')                 # DEL or higher
for character in ':*?./\\[]<>;=,':
    b.b(0xFE, ord(character))
    b.jr(0x28, 'INVALID_CHAR')
b.b(0xB7, 0xC9)                            # OR A / RET, carry clear
b.label('INVALID_CHAR')
b.b(0x37, 0xC9)                            # SCF / RET

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
b.label('MSG_TITLE')
b.b(*b'Bondwell 12/14 MC1408 smooth 10 kHz BMC player - port 50H\r\n$')
b.label('MSG_PROMPT')
b.b(*b'File to play (.BMC assumed): $')
b.label('MSG_CRLF')
b.b(*b'\r\n$')
b.label('MSG_LOADING')
b.b(*b'Loading file into memory...\r\n$')
b.label('MSG_PLAY')
b.b(*b'Playing; keyboard disabled until audio finishes.\r\n$')
b.label('MSG_DONE')
b.b(*b'\r\nPlayback complete.\r\n$')
b.label('MSG_BAD_NAME')
b.b(*b'Invalid CP/M filename. Use NAME, NAME.BMC or A:NAME.BMC.\r\n$')
b.label('MSG_OPEN_ERROR')
b.b(*b'Cannot open that file.\r\n$')
b.label('MSG_TOO_LARGE')
b.b(*b'File is too large for available CP/M memory.\r\n$')
b.label('MSG_BAD_FILE')
b.b(*b'Invalid, empty or truncated BWA4 file.\r\n$')
b.label('MSG_UNSUPPORTED')
b.b(*b'Unsupported BMC format. This player requires BWA4 2500 Hz / 10 kHz DAC smooth audio.\r\n$')

b.label('DEFAULT_EXTENSION')
b.b(*b'BMC')

b.label('LOAD_END')
b.w(0)

b.label('INPUT_BUFFER')
b.b(16, 0)                                # maximum input and returned count
b.label('INPUT_COUNT')                     # alias points to second byte
# Correct alias to INPUT_BUFFER+1 after all labels are available.
b.labels['INPUT_COUNT'] = b.labels['INPUT_BUFFER'] + 1
b.label('INPUT_TEXT')
# Correct alias to INPUT_BUFFER+2.
b.labels['INPUT_TEXT'] = b.labels['INPUT_BUFFER'] + 2
b.b(*([0] * 17))                          # input characters plus terminator room

b.label('FCB')
b.b(0)
b.label('FCB_NAME')
b.b(*b'        ')
b.label('FCB_EXT')
b.b(*b'   ')
b.b(*([0] * 24))                          # remainder of 36-byte FCB

binary = b.resolve()
(OUT / 'BWPLAY.COM').write_bytes(binary)

map_lines = [f'{address:04X} {name}' for name, address in sorted(b.labels.items(), key=lambda item: (item[1], item[0]))]
(OUT / 'BWPLAY.MAP').write_text('\n'.join(map_lines) + '\n')

print(f'BWPLAY.COM bytes={len(binary)} start={ORG:04X} end={ORG + len(binary):04X}')
print('\n'.join(map_lines))
