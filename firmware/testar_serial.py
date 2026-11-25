"""Confere o firmware do ESP32 pela serial, sem o site.

    pip install pyserial
    python firmware/testar_serial.py COM5
    python firmware/testar_serial.py COM5 --canais 2 --baud 115200

Espera o "flyback-esp32 pronto" do boot (abrir a porta reinicia muitas placas), pergunta o
estado com "?", toca um lá de 1 s em cada canal, uma escala curta no canal 1, o envelope (a mesma
nota longa reta, decaindo e com força menor) e um tom contínuo de 3 s pelo "D" (o do gerador de
tom), e termina com "X" (silêncio). O envelope só funciona no firmware de nov/2026 em diante — o
"?" do começo diz a versão; no antigo, as três notas soam iguais. Com o osciloscópio no GPIO de
cada canal: parado em BAIXO no silêncio (placa V3.6, lógica direta), onda quadrada de 50% na nota. Feche este script antes de conectar pelo site: só um
programa usa a porta por vez.
"""
import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit('falta o pyserial:  pip install pyserial')

ESCALA = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25]   # dó a dó


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('porta', help='COM5, /dev/ttyUSB0…')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--canais', type=int, default=2)
    a = ap.parse_args()

    # Abre sem ligar o DTR e o RTS e reinicia com um pulso só no RTS. Nas placas com conversor USB
    # (CH343, CP210x) os dois vão ao GPIO 0 e ao EN, e abrir do jeito padrão do pyserial chegou a
    # reiniciar o S3 em modo de gravação ("waiting for download") e, de outra vez, a apertar o BOOT
    # (o tom de teste ligou). Com o GPIO 0 solto o boot é sempre o normal. Na USB nativa do ESP
    # (VID 303A) o RTS reinicia o chip e derruba a porta: lá não mexe, e o teste segue sem o boot.
    from serial.tools import list_ports
    nativa = any(p.device == a.porta and p.vid == 0x303A for p in list_ports.comports())
    s = serial.Serial()
    s.port, s.baudrate, s.timeout = a.porta, a.baud, 0.1
    s.dtr = False
    s.rts = False
    s.open()
    if not nativa:
        s.rts = True
        time.sleep(0.1)
        s.rts = False

    def le(seg):
        fim, out = time.time() + seg, b''
        while time.time() < fim:
            out += s.read(256)
        texto = out.decode('utf-8', 'replace').strip()
        if texto:
            print('  ← ' + texto.replace('\n', '\n  ← '))
        return texto

    def manda(linha):
        print('  → ' + linha)
        s.write((linha + '\n').encode())

    print('esperando o boot…')
    boot = le(2.5)
    if 'flyback-esp32 pronto' not in boot:
        print('  (não veio o "pronto": a placa pode não ter reiniciado ao abrir a porta; seguindo)')

    manda('?'); le(0.5)
    manda('X')
    for c in range(a.canais):
        print(f'canal {c + 1}: lá de 1 s')
        manda('R'); manda(f'N {c} 0 440.00'); manda(f'F {c} 1000')
        le(1.6)
    print('canal 1: escala de dó a dó, 300 ms por nota')
    manda('R')
    for i, f in enumerate(ESCALA):
        manda(f'N 0 {i * 300} {f:.2f}')
    manda(f'F 0 {len(ESCALA) * 300}')
    le(len(ESCALA) * 0.3 + 0.5)
    print('canal 1: envelope — três lás de 2 s: reto, decaindo ("corda") e reto com força 30%')
    print('  no osciloscópio, a largura do pulso: 50% parada; caindo até ~4% no fim; ~10% parada')
    manda('E 0 4 0 1000 6'); manda('R'); manda('N 0 0 220.00'); manda('F 0 2000')
    le(2.4)
    manda('E 0 4 900 0 6'); manda('R'); manda('N 0 0 220.00'); manda('F 0 2000')
    le(2.4)
    manda('E 0 4 0 1000 6'); manda('R'); manda('N 0 0 220.00 300'); manda('F 0 2000')
    le(2.4)
    print('canal 1: tom contínuo de 220 Hz por 3 s, com o "D" renovado a cada 0,5 s')
    for _ in range(6):
        manda('D 0 500 220.00'); le(0.5)
    print('sem renovar: o ESP tem de apagar sozinho em 2 s')
    le(2.5)
    manda('X'); manda('?'); le(0.5)
    s.close()
    print('pronto. Se ouviu (ou viu no osciloscópio) cada canal e a escala, o firmware está bom.')


if __name__ == '__main__':
    main()
