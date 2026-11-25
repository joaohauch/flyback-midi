"""Monitor serial que NÃO reinicia o ESP ao abrir a porta.

    python firmware/monitor_serial.py COM5

Abre com DTR e RTS desligados: nas placas com reset automático (o S3 DevKit com CH343, a maioria
dos ESP32 com CP210x) o monitor comum puxa o EN ao abrir e o ESP reinicia — o "tempo ligado"
zera e o motivo do reinício vira "energia ligada", e não dá mais para saber por que a serial
caiu. Digite as linhas do protocolo (?, X, N 0 0 440…) e Enter; Ctrl+C sai. Só um programa usa
a porta por vez: feche este antes de conectar pelo site.
"""
import sys
import threading

try:
    import serial
except ImportError:
    sys.exit('falta o pyserial:  pip install pyserial')

porta = sys.argv[1] if len(sys.argv) > 1 else 'COM5'
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

s = serial.Serial()
s.port, s.baudrate, s.timeout = porta, baud, 0.1
s.dtr = False                                    # antes do open: a porta já abre sem puxar o EN
s.rts = False
s.open()
print(f'{porta} a {baud}, sem reiniciar o ESP. Digite ? e Enter. Ctrl+C sai.')


def le():
    while s.is_open:
        try:
            d = s.read(256)
        except serial.SerialException:
            print('\n*** a porta caiu (USB desconectado?) ***')
            return
        if d:
            sys.stdout.write(d.decode('utf-8', 'replace'))
            sys.stdout.flush()


threading.Thread(target=le, daemon=True).start()
try:
    for linha in sys.stdin:
        s.write((linha.strip() + '\n').encode())
except KeyboardInterrupt:
    pass
finally:
    s.close()
