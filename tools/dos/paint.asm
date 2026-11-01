; MUSEUM PAINT - tiny mouse test for the DOSBox room of the Point and Click Museum (CC0)
; Left button: draw · Right button or Space: next colour · C: clear · Esc: exit
; Build: nasm -f bin paint.asm -o PAINT.COM
        org 100h
start:  mov ax, 0013h           ; 320x200, 256 colours
        int 10h
        xor ax, ax              ; reset mouse driver
        int 33h
        or ax, ax
        jz nomouse
        call clear
        mov ax, 7               ; horizontal range 0..639
        xor cx, cx
        mov dx, 639
        int 33h
        mov ax, 8               ; vertical range 16..199 (keep the title bar)
        mov cx, 16
        mov dx, 199
        int 33h
        mov ax, 1               ; show cursor
        int 33h
main:   mov ah, 1               ; key waiting?
        int 16h
        jz .mouse
        xor ah, ah
        int 16h
        cmp al, 27
        je quit
        cmp al, ' '
        je .next
        or al, 20h
        cmp al, 'c'
        jne .mouse
        mov ax, 2
        int 33h
        call clear
        mov ax, 1
        int 33h
.mouse: mov ax, 3               ; bx=buttons cx=x dx=y
        int 33h
        test bx, 1
        jz .right
        call plot
        jmp main
.right: test bx, 2
        jz main
        call nextcol
.wait:  mov ax, 3               ; wait until the right button is released
        int 33h
        test bx, 2
        jnz .wait
        jmp main
.next:  call nextcol
        jmp main

nextcol:inc byte [color]        ; next colour (1..15) and redraw the swatch
        cmp byte [color], 16
        jb .ok
        mov byte [color], 1
.ok:    call swatch
        ret

plot:   shr cx, 1               ; virtual x 0..639 -> 0..319
        cmp cx, 318
        ja .done
        cmp dx, 198
        ja .done
        push cx
        push dx
        mov ax, 2               ; hide cursor while drawing
        int 33h
        pop dx
        pop cx
        mov ax, 0A000h
        mov es, ax
        mov ax, 320
        mul dx                  ; ax = y*320 (dx clobbered)
        add ax, cx
        mov di, ax
        mov al, [color]
        mov [es:di], al
        mov [es:di+1], al
        mov [es:di+320], al
        mov [es:di+321], al
        mov ax, 1
        int 33h
.done:  ret

clear:  mov ax, 0A000h          ; fill the canvas, draw the title bar
        mov es, ax
        xor di, di
        mov cx, 320*16
        mov al, 1
        rep stosb
        mov cx, 320*184
        mov al, 15
        rep stosb
        mov ah, 02h             ; cursor to row 0, col 1
        xor bh, bh
        mov dx, 0001h
        int 10h
        mov si, title
.c:     lodsb
        or al, al
        jz .s
        mov ah, 0Eh
        mov bl, 14
        int 10h
        jmp .c
.s:     call swatch
        ret

swatch: mov ax, 0A000h          ; current colour in the top-right corner
        mov es, ax
        mov di, 320*3+300
        mov al, [color]
        mov dx, 10
.row:   mov cx, 16
        rep stosb
        add di, 320-16
        dec dx
        jnz .row
        ret

nomouse:mov ax, 0003h
        int 10h
        mov dx, nomsg
        mov ah, 09h
        int 21h
        xor ah, ah
        int 16h
        jmp exit
quit:   mov ax, 0003h
        int 10h
exit:   mov ax, 4C00h
        int 21h

color   db 4
title   db 'MUSEUM PAINT L:draw R/Space:colour', 0
nomsg   db 'No mouse driver found.', 13, 10, '$'
