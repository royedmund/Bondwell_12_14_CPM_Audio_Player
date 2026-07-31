; -----------------------------------------------------------------------------
; BWPLAY.ASM - smooth BMC audio player for the Bondwell 12/14
; -----------------------------------------------------------------------------
; CPU:       Z80, approximately 4 MHz
; OS:        CP/M 2.2 or CP/M 3.0
; DAC:       MC1408 decoded at I/O addresses 50H-5FH
; Port used: 50H
;
; This version replaces the earlier one-bit, 2000 Hz delta stream with BWA4:
;
;   * 2500 source samples per second
;   * four 2-bit differential samples packed into each byte
;   * deltas -34, -6, +6 and +34
;   * four DAC writes per source sample (10000 writes/second)
;
; The four quarter-step writes provide a smoother ramp between reconstructed
; samples.  This substantially reduces the audible sampling images and the
; large fixed-step granular noise of the original BWDM player.
;
; The complete file is loaded before playback.  Enter NAME, NAME.BMC or a
; drive-qualified name such as B:NAME.BMC.  BMC is assumed when the extension
; is omitted.
; -----------------------------------------------------------------------------

        ORG     0100H

BDOS            EQU     0005H
DACPORT         EQU     050H
BUFFER          EQU     1000H
STACKTOP        EQU     0FF0H
BMC_RATE        EQU     2500

BDOS_PRINT      EQU     9
BDOS_READLINE   EQU     10
BDOS_OPEN       EQU     15
BDOS_CLOSE      EQU     16
BDOS_READSEQ    EQU     20
BDOS_SETDMA     EQU     26

START:
        LD      SP,STACKTOP

        LD      DE,MSG_TITLE
        LD      C,BDOS_PRINT
        CALL    BDOS

        LD      DE,MSG_PROMPT
        LD      C,BDOS_PRINT
        CALL    BDOS

        LD      DE,INPUT_BUFFER
        LD      C,BDOS_READLINE
        CALL    BDOS

        LD      DE,MSG_CRLF
        LD      C,BDOS_PRINT
        CALL    BDOS

        LD      A,(INPUT_COUNT)
        OR      A
        JP      Z,EXIT_TO_CPM

        CALL    INIT_FCB
        CALL    PARSE_FILENAME
        JP      C,BAD_NAME

        LD      DE,MSG_LOADING
        LD      C,BDOS_PRINT
        CALL    BDOS

        LD      DE,FCB
        LD      C,BDOS_OPEN
        CALL    BDOS
        INC     A
        JP      Z,OPEN_ERROR

        LD      HL,BUFFER

LOAD_LOOP:
        ; Keep the next 128-byte DMA record below the CP/M BDOS address.
        PUSH    HL
        LD      BC,0080H
        ADD     HL,BC
        LD      DE,(0006H)
        OR      A
        SBC     HL,DE
        POP     HL
        JP      NC,FILE_TOO_LARGE

        PUSH    HL
        LD      D,H
        LD      E,L
        LD      C,BDOS_SETDMA
        CALL    BDOS
        POP     HL

        PUSH    HL
        LD      DE,FCB
        LD      C,BDOS_READSEQ
        CALL    BDOS
        POP     HL

        OR      A
        JR      NZ,LOAD_DONE
        LD      DE,0080H
        ADD     HL,DE
        JP      LOAD_LOOP

LOAD_DONE:
        LD      (LOAD_END),HL

        LD      DE,FCB
        LD      C,BDOS_CLOSE
        CALL    BDOS

        ; Verify BWA4 signature.
        LD      HL,BUFFER
        LD      A,(HL)
        CP      'B'
        JP      NZ,BAD_FILE
        INC     HL
        LD      A,(HL)
        CP      'W'
        JP      NZ,BAD_FILE
        INC     HL
        LD      A,(HL)
        CP      'A'
        JP      NZ,BAD_FILE
        INC     HL
        LD      A,(HL)
        CP      '4'
        JP      NZ,BAD_FILE

        ; This fixed-cycle loop expects 2500 source samples per second.
        LD      HL,(BUFFER+4)
        LD      DE,BMC_RATE
        OR      A
        SBC     HL,DE
        JP      NZ,UNSUPPORTED_FILE

        ; Payload count must be non-zero.
        LD      HL,(BUFFER+6)
        LD      A,H
        OR      L
        JP      Z,BAD_FILE

        ; This player uses fixed total delta values of 6 and 34.
        LD      A,(BUFFER+10)
        CP      6
        JP      NZ,UNSUPPORTED_FILE
        LD      A,(BUFFER+11)
        CP      34
        JP      NZ,UNSUPPORTED_FILE

        ; Verify that the payload described by the header was loaded.
        LD      HL,(BUFFER+6)
        LD      DE,BUFFER+16
        ADD     HL,DE
        LD      DE,(LOAD_END)
        OR      A
        SBC     HL,DE
        JR      C,PAYLOAD_OK
        JR      Z,PAYLOAD_OK
        JP      BAD_FILE

PAYLOAD_OK:
        LD      DE,MSG_PLAY
        LD      C,BDOS_PRINT
        CALL    BDOS

        ; Preserve payload byte count in alternate BC.
        LD      HL,(BUFFER+6)
        LD      C,L
        LD      B,H
        EXX

        LD      HL,BUFFER+16
        LD      A,(BUFFER+9)
        LD      E,A                       ; current reconstructed DAC level

        DI

NEXT_BYTE:
        LD      C,(HL)
        INC     HL
        LD      B,4                       ; four two-bit codes per byte

CODE_LOOP:
        ; Extract bits 7-6 into A and shift the next code into position.
        LD      A,C
        AND     0C0H
        RLCA
        RLCA
        SLA     C
        SLA     C

        ; 00=-34, 01=-6, 10=+6, 11=+34.
        BIT     1,A
        JR      NZ,CODE_UP
        BIT     0,A
        JR      NZ,SMALL_DOWN
        JP      LARGE_DOWN

CODE_UP:
        BIT     0,A
        JR      NZ,LARGE_UP
        JP      SMALL_UP

LARGE_DOWN:
        LD      A,E
        SUB     8
        OUT     (DACPORT),A
        LD      D,23
LD_DLY1:
        DEC     D
        JR      NZ,LD_DLY1
        NOP
        NOP
        NOP
        SUB     9
        OUT     (DACPORT),A
        LD      D,23
LD_DLY2:
        DEC     D
        JR      NZ,LD_DLY2
        NOP
        NOP
        NOP
        SUB     8
        OUT     (DACPORT),A
        LD      D,23
LD_DLY3:
        DEC     D
        JR      NZ,LD_DLY3
        NOP
        NOP
        NOP
        SUB     9
        OUT     (DACPORT),A
        LD      E,A
        LD      D,16
LD_DLY4:
        DEC     D
        JR      NZ,LD_DLY4
        NOP
        JP      AFTER_SAMPLE

SMALL_DOWN:
        LD      A,E
        SUB     1
        OUT     (DACPORT),A
        LD      D,23
SD_DLY1:
        DEC     D
        JR      NZ,SD_DLY1
        NOP
        NOP
        NOP
        SUB     2
        OUT     (DACPORT),A
        LD      D,23
SD_DLY2:
        DEC     D
        JR      NZ,SD_DLY2
        NOP
        NOP
        NOP
        SUB     1
        OUT     (DACPORT),A
        LD      D,23
SD_DLY3:
        DEC     D
        JR      NZ,SD_DLY3
        NOP
        NOP
        NOP
        SUB     2
        OUT     (DACPORT),A
        LD      E,A
        LD      D,16
SD_DLY4:
        DEC     D
        JR      NZ,SD_DLY4
        NOP
        JP      AFTER_SAMPLE

SMALL_UP:
        LD      A,E
        ADD     A,1
        OUT     (DACPORT),A
        LD      D,23
SU_DLY1:
        DEC     D
        JR      NZ,SU_DLY1
        NOP
        NOP
        NOP
        ADD     A,2
        OUT     (DACPORT),A
        LD      D,23
SU_DLY2:
        DEC     D
        JR      NZ,SU_DLY2
        NOP
        NOP
        NOP
        ADD     A,1
        OUT     (DACPORT),A
        LD      D,23
SU_DLY3:
        DEC     D
        JR      NZ,SU_DLY3
        NOP
        NOP
        NOP
        ADD     A,2
        OUT     (DACPORT),A
        LD      E,A
        LD      D,16
SU_DLY4:
        DEC     D
        JR      NZ,SU_DLY4
        NOP
        JP      AFTER_SAMPLE

LARGE_UP:
        LD      A,E
        ADD     A,8
        OUT     (DACPORT),A
        LD      D,23
LU_DLY1:
        DEC     D
        JR      NZ,LU_DLY1
        NOP
        NOP
        NOP
        ADD     A,9
        OUT     (DACPORT),A
        LD      D,23
LU_DLY2:
        DEC     D
        JR      NZ,LU_DLY2
        NOP
        NOP
        NOP
        ADD     A,8
        OUT     (DACPORT),A
        LD      D,23
LU_DLY3:
        DEC     D
        JR      NZ,LU_DLY3
        NOP
        NOP
        NOP
        ADD     A,9
        OUT     (DACPORT),A
        LD      E,A
        LD      D,16
LU_DLY4:
        DEC     D
        JR      NZ,LU_DLY4
        NOP
        JP      AFTER_SAMPLE

AFTER_SAMPLE:
        DEC     B
        JP      NZ,CODE_LOOP

        EXX
        DEC     BC
        LD      A,B
        OR      C
        EXX
        JP      NZ,NEXT_BYTE

        EI
        LD      A,080H
        OUT     (DACPORT),A

        LD      DE,MSG_DONE
        LD      C,BDOS_PRINT
        CALL    BDOS
        JP      EXIT_TO_CPM

BAD_NAME:
        LD      DE,MSG_BAD_NAME
        LD      C,BDOS_PRINT
        CALL    BDOS
        JP      EXIT_TO_CPM

OPEN_ERROR:
        LD      DE,MSG_OPEN_ERROR
        LD      C,BDOS_PRINT
        CALL    BDOS
        JP      EXIT_TO_CPM

FILE_TOO_LARGE:
        LD      DE,FCB
        LD      C,BDOS_CLOSE
        CALL    BDOS
        LD      DE,MSG_TOO_LARGE
        LD      C,BDOS_PRINT
        CALL    BDOS
        JP      EXIT_TO_CPM

BAD_FILE:
        LD      DE,MSG_BAD_FILE
        LD      C,BDOS_PRINT
        CALL    BDOS
        JP      EXIT_TO_CPM

UNSUPPORTED_FILE:
        LD      DE,MSG_UNSUPPORTED
        LD      C,BDOS_PRINT
        CALL    BDOS
        JP      EXIT_TO_CPM

EXIT_TO_CPM:
        JP      0000H

; -----------------------------------------------------------------------------
; FCB initialisation and CP/M filename parser
; -----------------------------------------------------------------------------
INIT_FCB:
        LD      HL,FCB
        LD      B,36
        XOR     A
CLEAR_FCB_LOOP:
        LD      (HL),A
        INC     HL
        DJNZ    CLEAR_FCB_LOOP

        LD      HL,FCB_NAME
        LD      B,11
        LD      A,' '
SPACE_FCB_LOOP:
        LD      (HL),A
        INC     HL
        DJNZ    SPACE_FCB_LOOP
        RET

PARSE_FILENAME:
        LD      A,(INPUT_COUNT)
        LD      B,A
        LD      HL,INPUT_TEXT

        ; Optional drive prefix A: through P:.
        LD      A,B
        CP      2
        JR      C,NO_DRIVE
        INC     HL
        LD      A,(HL)
        DEC     HL
        CP      ':'
        JR      NZ,NO_DRIVE
        LD      A,(HL)
        CALL    UPCASE
        CP      'A'
        JP      C,PARSE_FAIL
        CP      'P'+1
        JP      NC,PARSE_FAIL
        SUB     'A'-1
        LD      (FCB),A
        INC     HL
        INC     HL
        DEC     B
        DEC     B

NO_DRIVE:
        LD      DE,FCB_NAME
        LD      C,0

NAME_LOOP:
        LD      A,B
        OR      A
        JR      Z,NO_EXTENSION
        LD      A,(HL)
        CP      '.'
        JR      Z,START_EXTENSION
        LD      A,C
        CP      8
        JP      NC,PARSE_FAIL
        LD      A,(HL)
        CALL    UPCASE
        CALL    VALID_CHAR
        JP      C,PARSE_FAIL
        LD      (DE),A
        INC     DE
        INC     HL
        DEC     B
        INC     C
        JR      NAME_LOOP

START_EXTENSION:
        LD      A,C
        OR      A
        JP      Z,PARSE_FAIL
        INC     HL
        DEC     B
        LD      DE,FCB_EXT
        LD      C,0

EXTENSION_LOOP:
        LD      A,B
        OR      A
        JR      Z,EXTENSION_DONE
        LD      A,C
        CP      3
        JP      NC,PARSE_FAIL
        LD      A,(HL)
        CALL    UPCASE
        CALL    VALID_CHAR
        JP      C,PARSE_FAIL
        LD      (DE),A
        INC     DE
        INC     HL
        DEC     B
        INC     C
        JR      EXTENSION_LOOP

EXTENSION_DONE:
        LD      A,C
        OR      A
        JR      Z,SET_DEFAULT_EXTENSION
        OR      A
        RET

NO_EXTENSION:
        LD      A,C
        OR      A
        JP      Z,PARSE_FAIL

SET_DEFAULT_EXTENSION:
        LD      HL,DEFAULT_EXTENSION
        LD      DE,FCB_EXT
        LD      BC,3
        LDIR
        OR      A
        RET

PARSE_FAIL:
        SCF
        RET

UPCASE:
        CP      'a'
        RET     C
        CP      'z'+1
        RET     NC
        SUB     20H
        RET

VALID_CHAR:
        CP      21H
        JR      C,INVALID_CHAR
        CP      7FH
        JR      NC,INVALID_CHAR
        CP      ':'
        JR      Z,INVALID_CHAR
        CP      '*'
        JR      Z,INVALID_CHAR
        CP      '?'
        JR      Z,INVALID_CHAR
        CP      '.'
        JR      Z,INVALID_CHAR
        CP      '/'
        JR      Z,INVALID_CHAR
        CP      '\'
        JR      Z,INVALID_CHAR
        CP      '['
        JR      Z,INVALID_CHAR
        CP      ']'
        JR      Z,INVALID_CHAR
        CP      '<'
        JR      Z,INVALID_CHAR
        CP      '>'
        JR      Z,INVALID_CHAR
        CP      ';'
        JR      Z,INVALID_CHAR
        CP      '='
        JR      Z,INVALID_CHAR
        CP      ','
        JR      Z,INVALID_CHAR
        OR      A
        RET

INVALID_CHAR:
        SCF
        RET

; -----------------------------------------------------------------------------
; Data
; -----------------------------------------------------------------------------
MSG_TITLE:
        DB      'Bondwell 12/14 MC1408 smooth 10 kHz BMC player - port 50H',13,10,'$'
MSG_PROMPT:
        DB      'File to play (.BMC assumed): $'
MSG_CRLF:
        DB      13,10,'$'
MSG_LOADING:
        DB      'Loading file into memory...',13,10,'$'
MSG_PLAY:
        DB      'Playing; keyboard disabled until audio finishes.',13,10,'$'
MSG_DONE:
        DB      13,10,'Playback complete.',13,10,'$'
MSG_BAD_NAME:
        DB      'Invalid CP/M filename. Use NAME, NAME.BMC or A:NAME.BMC.',13,10,'$'
MSG_OPEN_ERROR:
        DB      'Cannot open that file.',13,10,'$'
MSG_TOO_LARGE:
        DB      'File is too large for available CP/M memory.',13,10,'$'
MSG_BAD_FILE:
        DB      'Invalid, empty or truncated BWA4 file.',13,10,'$'
MSG_UNSUPPORTED:
        DB      'Unsupported BMC format. This player requires BWA4 2500 Hz / 10 kHz DAC smooth audio.',13,10,'$'

DEFAULT_EXTENSION:
        DB      'BMC'

LOAD_END:
        DW      0

INPUT_BUFFER:
        DB      16
INPUT_COUNT:
        DB      0
INPUT_TEXT:
        DS      17

FCB:
        DB      0
FCB_NAME:
        DB      '        '
FCB_EXT:
        DB      '   '
        DS      24

        END     START
