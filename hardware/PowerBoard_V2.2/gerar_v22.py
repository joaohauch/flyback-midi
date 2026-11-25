"""Gera a PowerBoard V2.2 (placa de potência, face simples, para fresadora) no KiCad 10, em duas versões.

    python gerar_v22.py          (as duas)
    python gerar_v22.py B        (só uma)

    A_mosfet_embaixo/   IRFP264N deitado EMBAIXO da placa, aba no dissipador que serve de base
    B_mosfet_em_pe/     IRFP264N em pé na face de cima, aba virada para a borda de baixo

É a PowerBoard V2.1 (totem pole) corrigida com as decisões da V3.6, no desenho da PowerBoard V3
do EasyEDA: mesmo tamanho (85,2 x 39,5 mm) e as peças de potência nas mesmas posições.

O cobre (B.Cu) só tem pads, trilhas e zonas, para a fresa não perder tempo com letras. A serigrafia
vai numa folha impressa em cores, em escala 1:1, para colar sobre a face de cima:
<versão>/<nome>_impressao_topo.pdf. Para a fresa: <versão>/fabricacao/ (contorno, furos PTH e NPTH,
cobre) e o mesmo conteúdo em <versão>/<nome>_fresa.zip.

Passos:
  1. FBMD.pretty/ (comum às duas): footprints adaptadas das bibliotecas do KiCad para fresar (pads
     maiores, brocas de 0,8 / 1,0 / 1,2 / 1,6 / 3,2 / 4,5 mm) e as próprias (MKP de dois passos,
     fio JP1, TO-247 deitado embaixo, furo M3).
  2. Para cada versão: esquema, ERC, netlist e PDF; pcb_v22.py no Python do KiCad; kicad-cli para
     preencher as zonas, DRC com paridade de esquema, Gerber, furação, imagens e a impressão.

Tudo que sai daqui é regerado; para mudar a placa, mude este arquivo ou o pcb_v22.py.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))

def _raiz():
    """A pasta do projeto (midi-flyback), subindo até achar FlybachSimulations/lib. Esta pasta vive
    em repo/hardware/PowerBoard_V2.2 desde 25/nov/2026 (antes, em FlybachSchems/PowerBoard_V2.2):
    a biblioteca kicad_sch e o modelo de projeto do KiCad ficam fora do repositório."""
    d = AQUI
    for _ in range(6):
        if os.path.isfile(os.path.join(d, 'FlybachSimulations', 'lib', 'kicad_sch.py')):
            return d
        d = os.path.dirname(d)
    sys.exit('não achei FlybachSimulations/lib/kicad_sch.py subindo a partir de ' + AQUI)


RAIZ = _raiz()
sys.path.insert(0, os.path.join(RAIZ, 'FlybachSimulations', 'lib'))
from kicad_sch import Folha, erc, esc, escrever, ler_sexpr, netlist, pdf, u   # noqa: E402

KICAD = os.environ.get('KICAD_DIR', r'C:\Program Files\KiCad\10.0')
CLI = os.path.join(KICAD, 'bin', 'kicad-cli.exe')
KPY = os.path.join(KICAD, 'bin', 'python.exe')
FPLIB = os.path.join(KICAD, 'share', 'kicad', 'footprints')
LIB = os.path.join(AQUI, 'FBMD.pretty')
G = 2.54
DATA = '2026-11-23'

VERSOES = {
    'A': dict(pasta='A_mosfet_embaixo', nome='PowerBoard_V2.2A', q3='FBMD:TO-247-3_Deitado_Embaixo_CNC',
              titulo='FBMD PowerBoard V2.2A · MOSFET deitado embaixo',
              resumo='IRFP264N deitado EMBAIXO da placa, aba no dissipador que serve de base'),
    'B': dict(pasta='B_mosfet_em_pe', nome='PowerBoard_V2.2B', q3='FBMD:TO-247-3_Vertical_CNC',
              titulo='FBMD PowerBoard V2.2B · MOSFET em pé',
              resumo='IRFP264N em pé na face de cima, aba virada para a borda de baixo'),
}

PE = dict(
    R='FBMD:R_Axial_P10.16_CNC',
    D='FBMD:D_DO-35_P7.62_CNC',
    C='FBMD:C_Disc_P5.00_CNC',
    CE='FBMD:CP_Radial_D6.3_P2.50_CNC',
    CB='FBMD:CP_Radial_D12.5_P5.00_CNC',
    MKP='FBMD:C_MKP_W6_P10_P15_CNC',
    TO92='FBMD:TO-92_Inline_Wide_CNC',
    TO220='FBMD:TO-220-2_Vertical_CNC',
    KK3='FBMD:Molex_KK-254_1x03_CNC',
    MCV2='FBMD:Phoenix_MCV_1x02_P5.08_CNC',
    XT60='FBMD:XT60-M_Vertical_CNC',
    JP='FBMD:Jumper_Fio_16.0mm',
)
JP_COMP = 16.0      # distância entre os furos do fio JP1 (mm)


# =================================================================================== FOOTPRINTS
def _silk_valor(arv):
    """O valor vai na F.SilkS, junto da referência: é o que sai na folha impressa da face de cima.
    O pcb_v22.py põe os dois na horizontal, no meio da peça."""
    arv[:] = [e for e in arv if not (isinstance(e, list) and e[0] == 'fp_text' and e[2] == '"${REFERENCE}"')]
    arv.append(['fp_text', 'user', '"${VALUE}"', ['at', 0, 0, 0], ['layer', '"F.SilkS"'], ['uuid', esc(u())],
                ['effects', ['font', ['size', 0.9, 0.9], ['thickness', 0.14]]]])


def adapta(lib, nome, novo, pads, descr, sem_hachura=None):
    """Copia uma footprint do KiCad com pads e furos para fresar.
    pads = {número ou '*': (forma, (x, y), furo)}.
    sem_hachura = x: tira da F.SilkS as linhas todas à direita de x (a hachura da metade negativa dos
    eletrolíticos, que na folha impressa vira uma mancha branca por cima do valor)."""
    with open(os.path.join(FPLIB, lib + '.pretty', nome + '.kicad_mod'), encoding='utf-8') as fh:
        arv = ler_sexpr(fh.read())
    arv[1] = esc(novo)
    if sem_hachura is not None:
        def hachura(e):
            if not (isinstance(e, list) and e[0] == 'fp_line'):
                return False
            camada = next((s[1] for s in e if isinstance(s, list) and s[0] == 'layer'), '')
            xs = [float(s[1]) for s in e if isinstance(s, list) and s[0] in ('start', 'end')]
            return camada == '"F.SilkS"' and min(xs) > sem_hachura
        arv[:] = [e for e in arv if not hachura(e)]
    for e in arv:
        if not isinstance(e, list):
            continue
        if e[0] == 'descr':
            e[1] = esc(descr)
        elif e[0] == 'property' and e[1] == '"Value"':
            e[2] = esc(novo)
        elif e[0] == 'pad':
            spec = pads.get(e[1].strip('"'), pads.get('*'))
            if not spec:
                continue
            forma, (sx, sy), furo = spec
            e[3] = forma
            for s in e:
                if isinstance(s, list) and s[0] == 'size':
                    s[1:] = [sx, sy]
                elif isinstance(s, list) and s[0] == 'drill':
                    s[1:] = [furo]
            e[:] = [s for s in e if not (isinstance(s, list) and s[0] == 'roundrect_rratio')]
            if forma == 'roundrect':
                e.insert(5, ['roundrect_rratio', 0.15])
    _silk_valor(arv)
    with open(os.path.join(LIB, novo + '.kicad_mod'), 'w', encoding='utf-8') as fh:
        fh.write(escrever(arv) + '\n')


def _linha(a, b, camada, w=0.12, tipo='solid'):
    return f'\t(fp_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width {w}) (type {tipo})) (layer "{camada}"))\n'


def _ret(a, b, camada, w=0.12, tipo='solid'):
    return (f'\t(fp_rect (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width {w}) (type {tipo})) '
            f'(fill no) (layer "{camada}"))\n')


def _circ(c, r, camada, w=0.12, tipo='solid'):
    return (f'\t(fp_circle (center {c[0]} {c[1]}) (end {c[0] + r} {c[1]}) (stroke (width {w}) (type {tipo})) '
            f'(fill no) (layer "{camada}"))\n')


def _texto(txt, at, camada, tam=0.9):
    espelho = ' (justify mirror)' if camada.startswith('B.') else ''   # lido por baixo
    return (f'\t(fp_text user "{txt}" (at {at[0]} {at[1]} 0) (layer "{camada}") '
            f'(effects (font (size {tam} {tam}) (thickness {tam * 0.15:.3f})){espelho}))\n')


def _pad(num, x, y, forma, d, furo, d2=None):
    rr = ' (roundrect_rratio 0.15)' if forma == 'roundrect' else ''
    return (f'\t(pad "{num}" thru_hole {forma} (at {x} {y}) (size {d} {d2 or d}) (drill {furo}) '
            f'(layers "*.Cu" "*.Mask") (remove_unused_layers no){rr})\n')


def _cabeca(nome, descr, ref_at, val_at, attr='through_hole'):
    return (f'(footprint "{nome}"\n\t(version 20260206)\n\t(generator "gerar_v22")\n\t(layer "F.Cu")\n'
            f'\t(descr "{descr}")\n'
            f'\t(property "Reference" "REF**" (at {ref_at[0]} {ref_at[1]} 0) (layer "F.SilkS") '
            f'(effects (font (size 1 1) (thickness 0.15))))\n'
            f'\t(property "Value" "{nome}" (at {val_at[0]} {val_at[1]} 0) (layer "F.Fab") '
            f'(effects (font (size 1 1) (thickness 0.15))))\n'
            f'\t(attr {attr})\n\t(duplicate_pad_numbers_are_jumpers no)\n')


def _grava(nome, s):
    with open(os.path.join(LIB, nome + '.kicad_mod'), 'w', encoding='utf-8') as fh:
        fh.write(s)


def footprint_mkp():
    """MKP de 6 mm de largura com dois furos para a perna do dreno: passo de 10 e de 15 mm.
    Pad 2 (GND) sozinho; os dois pads 1 são do dreno e vão na mesma zona de cobre."""
    nome = 'C_MKP_W6_P10_P15_CNC'
    s = _cabeca(nome, 'MKP 100 nF da PowerBoard: um furo de GND e dois de dreno (passo 10 ou 15 mm), '
                'para os dois lotes de capacitor', (7.5, -4.2), (7.5, 4.2))
    s += _ret((-1.62, -3.12), (16.62, 3.12), 'F.SilkS')
    s += _linha((11.62, -3.12), (11.62, 3.12), 'F.SilkS', 0.12, 'dash')
    s += _ret((-1.5, -3.0), (11.5, 3.0), 'F.Fab', 0.1)
    s += _ret((-1.5, -3.0), (16.5, 3.0), 'F.Fab', 0.1)
    s += _ret((-1.75, -3.25), (16.75, 3.25), 'F.CrtYd', 0.05)
    s += _texto('${VALUE}', (7.5, 0.6), 'F.SilkS')
    s += _pad('2', 0, 0, 'circle', 2.4, 1.0)
    s += _pad('1', 10, 0, 'circle', 2.4, 1.0)
    s += _pad('1', 15, 0, 'circle', 2.4, 1.0)
    s += ('\t(embedded_fonts no)\n'
          '\t(model "${KICAD10_3DMODEL_DIR}/Capacitor_THT.3dshapes/C_Rect_L13.0mm_W6.0mm_P10.00mm_FKS3_FKP3_MKS4.step"'
          ' (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))\n)\n')
    _grava(nome, s)


def footprint_jumper(c=JP_COMP):
    """Fio por cima da placa entre dois furos a c mm (JP1). Os dois pads formam um grupo de jumper:
    o KiCad os considera ligados pelo fio (na versão B, cada um fica numa ilha de cobre do gate)."""
    nome = f'Jumper_Fio_{c:.1f}mm'
    s = _cabeca(nome, f'Fio de jumper por cima da placa, furos a {c:.1f} mm (fio de até 0,8 mm)',
                (c / 2, -2.2), (c / 2, 2.2))
    s += '\t(jumper_pad_groups ("1" "2"))\n'
    s += _linha((1.6, 0), (c - 1.6, 0), 'F.SilkS', 0.4)
    s += _linha((0, 0), (c, 0), 'F.Fab', 0.6)
    s += _ret((-1.5, -1.5), (c + 1.5, 1.5), 'F.CrtYd', 0.05)
    s += _texto('${VALUE}', (c / 2, 1), 'F.SilkS')
    s += _pad('1', 0, 0, 'circle', 2.4, 1.0)
    s += _pad('2', c, 0, 'circle', 2.4, 1.0)
    s += '\t(embedded_fonts no)\n)\n'
    _grava(nome, s)


def footprint_to247_deitado():
    """IRFP264N deitado EMBAIXO da placa (versão A), com a aba no dissipador e as pernas dobradas a 90°
    subindo para os pads. O corpo vai para -y (para dentro da placa) e a face escrita fica virada para
    a placa: assim, vista de cima, a ordem é G-D-S como nos pads. Deitado para +y, G e S trocariam.
    Corpo e furo de fixação: tracejados na F.SilkS (saem na folha impressa) e na B.Fab (vista de baixo).
    Sem B.CrtYd: o corpo fica afastado da placa, apoiado no dissipador. Modelo 3D: o TO-247 em pé
    (o KiCad 10 não traz o deitado) girado para deitar sob a placa; as pernas aparecem retas."""
    nome = 'TO-247-3_Deitado_Embaixo_CNC'
    s = _cabeca(nome, 'TO-247 deitado embaixo da placa, aba no dissipador, pernas dobradas a 90 graus; '
                'corpo para -y. Para +y, G e S trocam', (5.45, 3.6), (5.45, 5.0))
    corpo = ((-2.5, -26.03), (13.4, -5.08))
    for camada, tipo in (('B.Fab', 'solid'), ('F.SilkS', 'dash')):
        s += _ret(*corpo, camada, 0.12, tipo)
        for x in (0, 5.45, 10.9):
            s += _ret((x - 0.6, -5.08), (x + 0.6, -2.4), camada, 0.1, tipo)
        s += _circ((5.45, -19.86), 1.8, camada, 0.1, tipo)
    s += _ret((-1.65, -2.35), (12.55, 2.35), 'F.CrtYd', 0.05)
    s += _texto('${REFERENCE} ${VALUE}', (5.45, 3.3), 'F.SilkS')
    s += _texto('por baixo, deitado', (5.45, 4.5), 'F.SilkS', 0.8)
    s += _texto('aba no dissipador', (5.45, 5.6), 'F.SilkS', 0.8)
    s += _texto('${REFERENCE} ${VALUE}', (5.45, -15.5), 'B.Fab')
    s += _pad('1', 0, 0, 'roundrect', 2.8, 1.6, 4.2)
    s += _pad('2', 5.45, 0, 'oval', 2.8, 1.6, 4.2)
    s += _pad('3', 10.9, 0, 'oval', 2.8, 1.6, 4.2)
    s += ('\t(embedded_fonts no)\n'
          '\t(model "${KICAD10_3DMODEL_DIR}/Package_TO_SOT_THT.3dshapes/TO-247-3_Vertical.step"'
          ' (offset (xyz 0 5.08 -6.3)) (scale (xyz 1 1 1)) (rotate (xyz 90 0 0)))\n)\n')
    _grava(nome, s)


def footprint_furo_m3():
    """Furo de fixação M3 para os standoffs de nylon. O cobre fica a 0,6 mm da borda do furo (no
    dreno, a 1,5 mm, pela classe HV); a cabeça do parafuso está desenhada na F.SilkS."""
    nome = 'Furo_M3_CNC'
    s = (f'(footprint "{nome}"\n\t(version 20260206)\n\t(generator "gerar_v22")\n\t(layer "F.Cu")\n'
         '\t(descr "Furo de fixação M3 (3,2 mm) para standoff de nylon")\n'
         '\t(property "Reference" "H**" (at 0 -3.6 0) (layer "F.SilkS") (hide yes) '
         '(effects (font (size 1 1) (thickness 0.15))))\n'
         f'\t(property "Value" "{nome}" (at 0 3.6 0) (layer "F.Fab") (hide yes) '
         '(effects (font (size 1 1) (thickness 0.15))))\n'
         '\t(attr board_only exclude_from_pos_files exclude_from_bom)\n')
    s += _circ((0, 0), 2.75, 'F.SilkS', 0.12)
    s += _circ((0, 0), 3.0, 'F.CrtYd', 0.05)
    s += ('\t(pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask") '
          '(clearance 0.6))\n\t(embedded_fonts no)\n)\n')
    _grava(nome, s)


def esvazia(pasta):
    """Apaga o conteúdo da pasta, subpastas incluídas. As pastas ficam (o Windows recusa apagar uma
    pasta que o editor ou o Explorer estejam observando)."""
    os.makedirs(pasta, exist_ok=True)
    for nome in os.listdir(pasta):
        alvo = os.path.join(pasta, nome)
        if os.path.isdir(alvo):
            esvazia(alvo)
            try:
                os.rmdir(alvo)
            except OSError:
                pass
        else:
            os.remove(alvo)


def footprints():
    esvazia(LIB)
    R, O, C = 'roundrect', 'oval', 'circle'
    # XT60: pads ovais, 5,6 mm no sentido dos pinos (1,6 mm entre o +24V e o GND) e 7 mm no outro
    adapta('Connector_AMASS', 'AMASS_XT60-M_1x02_P7.20mm_Vertical', 'XT60-M_Vertical_CNC',
           {'1': (R, (5.6, 7.0), 4.5), '2': (O, (5.6, 7.0), 4.5)},
           'XT60 macho na vertical; pino 1 é o do lado chanfrado (negativo)')
    adapta('Capacitor_THT', 'CP_Radial_D12.5mm_P5.00mm', 'CP_Radial_D12.5_P5.00_CNC',
           {'1': (R, (2.8, 2.8), 1.2), '2': (C, (2.8, 2.8), 1.2)}, 'Eletrolítico 12,5 mm, passo 5 mm, para fresar',
           sem_hachura=1.5)
    adapta('Capacitor_THT', 'CP_Radial_D6.3mm_P2.50mm', 'CP_Radial_D6.3_P2.50_CNC',
           {'1': (R, (1.8, 2.4), 0.8), '2': (O, (1.8, 2.4), 0.8)}, 'Eletrolítico 6,3 mm, passo 2,5 mm, para fresar',
           sem_hachura=0.75)
    adapta('Capacitor_THT', 'C_Disc_D5.0mm_W2.5mm_P5.00mm', 'C_Disc_P5.00_CNC',
           {'*': (C, (2.0, 2.0), 0.8)}, 'Cerâmico de disco, passo 5 mm, para fresar')
    adapta('Package_TO_SOT_THT', 'TO-220-2_Vertical', 'TO-220-2_Vertical_CNC',
           {'1': (R, (2.6, 2.6), 1.2), '2': (C, (2.6, 2.6), 1.2)}, 'TO-220 de 2 pinos em pé (MUR860), para fresar')
    adapta('Package_TO_SOT_THT', 'TO-247-3_Vertical', 'TO-247-3_Vertical_CNC',
           {'1': (R, (2.8, 4.2), 1.6), '*': (O, (2.8, 4.2), 1.6)}, 'TO-247 em pé (IRFP264N), para fresar')
    adapta('Package_TO_SOT_THT', 'TO-92_Inline_Wide', 'TO-92_Inline_Wide_CNC',
           {'1': (R, (1.8, 2.4), 0.8), '*': (O, (1.8, 2.4), 0.8)}, 'TO-92 com pernas abertas (2,54 mm), para fresar')
    adapta('Resistor_THT', 'R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal', 'R_Axial_P10.16_CNC',
           {'*': (C, (2.0, 2.0), 0.8)}, 'Resistor 1/4 W deitado, passo 10,16 mm, para fresar')
    adapta('Diode_THT', 'D_DO-35_SOD27_P7.62mm_Horizontal', 'D_DO-35_P7.62_CNC',
           {'1': (R, (2.0, 2.0), 0.8), '2': (C, (2.0, 2.0), 0.8)}, 'Diodo DO-35 deitado, passo 7,62 mm, para fresar')
    adapta('Connector_Molex', 'Molex_KK-254_AE-6410-03A_1x03_P2.54mm_Vertical', 'Molex_KK-254_1x03_CNC',
           {'1': (R, (1.8, 2.6), 1.0), '*': (O, (1.8, 2.6), 1.0)}, 'Molex KK 254 de 3 vias, para fresar')
    adapta('Connector_Phoenix_MC_HighVoltage', 'PhoenixContact_MCV_1,5_2-G-5.08_1x02_P5.08mm_Vertical',
           'Phoenix_MCV_1x02_P5.08_CNC', {'1': (R, (2.6, 3.6), 1.6), '2': (O, (2.6, 3.6), 1.6)},
           'Borne de encaixe 5,08 mm de 2 vias (2EDG / MCV), para fresar')
    footprint_mkp()
    footprint_jumper()
    footprint_to247_deitado()
    footprint_furo_m3()


# =================================================================================== PROJETO
def projeto(pasta, nome):
    """O .kicad_pro (classes de rede e regras para fresar), o .kicad_dru e a fp-lib-table da versão."""
    with open(os.path.join(RAIZ, 'FlybachSchems', 'FlybachSchems.kicad_pro'), encoding='utf-8') as fh:
        d = json.load(fh)
    d['meta']['filename'] = nome + '.kicad_pro'
    base = d['net_settings']['classes'][0]

    def classe(n, folga, trilha, prio):
        c = dict(base)
        c.update(name=n, clearance=folga, track_width=trilha, priority=prio, via_diameter=2.0, via_drill=1.0)
        return c
    d['net_settings']['classes'] = [classe('Default', 0.5, 1.0, 2147483647),
                                    classe('HV', 1.5, 3.0, 0),
                                    classe('Potencia', 0.6, 2.0, 1)]
    d['net_settings']['netclass_patterns'] = [{'netclass': 'HV', 'pattern': '/DRENO'},
                                              {'netclass': 'Potencia', 'pattern': 'GND'},
                                              {'netclass': 'Potencia', 'pattern': '+24V'}]
    ds = d['board']['design_settings']
    ds['rules'].update(min_clearance=0.5, min_track_width=0.8, min_hole_clearance=0.5, min_hole_to_hole=0.5,
                       min_through_hole_diameter=0.8, min_via_annular_width=0.4, min_copper_edge_clearance=0.5,
                       min_text_height=0.8, min_text_thickness=0.1, min_connection=0.6)
    sev = ds.setdefault('rule_severities', {})
    # a serigrafia não é fabricada (vai impressa em papel): sobreposições nela não importam
    for k in ('silk_overlap', 'silk_over_copper', 'silk_edge_clearance', 'lib_footprint_issues',
              'lib_footprint_mismatch', 'text_height', 'text_thickness', 'nonmirrored_text_on_back_layer',
              'solder_mask_bridge'):
        sev[k] = 'ignore'
    d['board']['design_settings'] = ds
    with open(os.path.join(pasta, nome + '.kicad_pro'), 'w', encoding='utf-8') as fh:
        json.dump(d, fh, indent=2, ensure_ascii=False)
    # 24 V e GND correm lado a lado por toda a placa: 1,5 mm entre eles para uma rebarba da fresa ou
    # um respingo de solda não curtar a fonte (só esse par; o resto do GND segue com 0,6 mm)
    with open(os.path.join(pasta, nome + '.kicad_dru'), 'w', encoding='utf-8') as fh:
        fh.write('(version 1)\n'
                 '(rule "24V longe do GND"\n'
                 '\t(constraint clearance (min 1.5mm))\n'
                 "\t(condition \"(A.NetName == '+24V' && B.NetName == 'GND') || "
                 "(A.NetName == 'GND' && B.NetName == '+24V')\"))\n")
    with open(os.path.join(pasta, 'fp-lib-table'), 'w', encoding='utf-8') as fh:
        fh.write('(fp_lib_table\n\t(version 7)\n\t(lib (name "FBMD") (type "KiCad") (uri "${KIPRJMOD}/../FBMD.pretty") '
                 '(options "") (descr "Footprints da PowerBoard V2.2 para fresadora"))\n)\n')


# =================================================================================== ESQUEMA
def p(x, y):
    return (x * G, y * G)


def notas(f, x, y, linhas, titulo=None):
    if titulo:
        f.texto(titulo, p(x, y), 1.8, True)
        y += 1.6
    for l in linhas:
        f.texto(l, p(x, y), 1.27)
        y += 1.0


def bloco(f, x0, y0, x1, y1, titulo):
    f.caixa(p(x0, y0), p(x1, y1))
    f.texto(titulo, p(x0 + 0.6, y0 + 1.4), 1.6, True)


def fios(f, *pts):
    f.fios(*[p(*q) for q in pts])


def em(peca, num, x, y):
    (px, py), _ = peca.ponto(num)
    assert abs(px - x * G) < 0.01 and abs(py - y * G) < 0.01, (peca.ref, num, px / G, py / G, x, y)
    return (x, y)


def alim(f, rede, x, y):
    f.alim(rede, p(x, y))


def rot(f, nome, x, y, dx=1, dy=0):
    f.rotulo(nome, p(x, y), dx, dy)


def esquema(v):
    cfg = VERSOES[v]
    f = Folha(cfg['titulo'], '2.2' + v, DATA, comentarios=(
        'V2.1 (totem pole) + correções da V3.6, no desenho da PowerBoard V3; face simples, fresada',
        'Totem pole em 12 V, IRFP264N, 300 nF no dreno (3 x 100 nF MKP), MUR860, sem TVS',
        cfg['resumo'],
        f'PCB: {cfg["nome"]}.kicad_pcb, gerada por gerar_v22.py'))

    # ---------------- 24 V e banco
    bloco(f, 8, 10, 58, 52, 'Entrada de 24 V e banco')
    j1 = f.peca('Connector_Generic:Conn_01x02', 'J1', 'XT60 24 V', p(12, 23), 180, PE['XT60'])
    fios(f, em(j1, '2', 14, 22), (15, 22), (15, 18), (19, 18), (22, 18), (28, 18), (34, 18), (40, 18), (46, 18))
    fios(f, em(j1, '1', 14, 23), (17, 23), (17, 30), (19, 30), (22, 30), (28, 30), (34, 30), (40, 30), (46, 30))
    f.flag(p(19, 18), 0)
    f.flag(p(19, 30), 180)
    alim(f, '+24V', 46, 18)
    alim(f, 'GND', 46, 30)
    for i, x in enumerate((22, 28, 34, 40), 1):
        c = f.peca('Device:C_Polarized', f'C{i}', '470µ 35V', p(x, 24), 0, PE['CB'])
        fios(f, (x, 18), em(c, '1', x, 22.5))
        fios(f, em(c, '2', x, 25.5), (x, 30))
    notas(f, 9, 36, ['XT60: o pino 1 fica no lado chanfrado, que é o negativo',
                     '(como na V3 do EasyEDA).',
                     'C1 a C4 no mesmo lugar da V3 (lá eram C5, C16, C17, C18).',
                     'Sem cerâmico no banco: o 100 nF da V3 era do 7815, que saiu;',
                     'a 40 kHz ele não muda nada perto de 1880 uF.',
                     'Simulado: de 1 a 8 x 470 uF o arco muda 3 %;',
                     'os quatro dividem a ondulação de corrente.'])

    # ---------------- gate e chave
    bloco(f, 62, 10, 160, 52, 'Acionamento do gate (totem pole em 12 V) e chave')
    f.texto('Chave e dreno', p(122, 13.4), 1.6, True)
    p2 = f.peca('Connector_Generic:Conn_01x03', 'P2', '12V GND SIN', p(68, 24), 180, PE['KK3'], espelho=True)
    fios(f, em(p2, '1', 70, 23), (72, 23), (72, 16), (74, 16), (78, 16), (83, 16), (88, 16), (93, 16))
    f.flag(p(74, 16), 0)
    alim(f, '+12V', 88, 16)
    fios(f, em(p2, '2', 70, 24), (74, 24), (74, 26)); alim(f, 'GND', 74, 26)
    for ref, val, x, pe in (('C6', '47µ 25V', 78, 'CE'), ('C7', '100n', 83, 'C')):
        c = f.peca('Device:C_Polarized' if pe == 'CE' else 'Device:C', ref, val, p(x, 19), 0, PE[pe])
        fios(f, (x, 16), em(c, '1', x, 17.5))
        fios(f, em(c, '2', x, 20.5), (x, 22)); alim(f, 'GND', x, 22)
    q1 = f.peca('Transistor_BJT:BC337', 'Q1', 'BC337', p(92, 24), 0, PE['TO92'])
    q2 = f.peca('Transistor_BJT:BC327', 'Q2', 'BC327', p(92, 34), 0, PE['TO92'], espelho=True)
    fios(f, em(p2, '3', 70, 25), (71, 25), (71, 30), (80, 30), (88, 30))
    rot(f, 'GATE_DRV', 80, 30, 0, -1)
    fios(f, em(q1, '2', 90, 24), (88, 24), (88, 30), (88, 34), em(q2, '2', 90, 34))
    fios(f, em(q1, '1', 93, 22), (93, 16))
    fios(f, em(q1, '3', 93, 26), (93, 29), em(q2, '3', 93, 32))
    r1 = f.peca('Device:R', 'R1', '10Ω', p(98.5, 27), 90, PE['R'])
    d1 = f.peca('Diode:1N4148', 'D1', '1N4148', p(98.5, 31), 0, PE['D'])
    fios(f, (93, 29), (95, 29), (97, 29))
    rot(f, 'DRV', 95, 29, 0, -1)
    fios(f, em(r1, '1', 97, 27), (97, 29), em(d1, '1', 97, 31))
    fios(f, em(r1, '2', 100, 27), (100, 29), em(d1, '2', 100, 31))
    q3 = f.peca('Transistor_FET:Q_NMOS_GDS', 'Q3', 'IRFP264N', p(120, 29), 0, cfg['q3'])
    r2 = f.peca('Device:R', 'R2', '10k', p(104, 32.5), 0, PE['R'])
    fios(f, (104, 29), em(r2, '1', 104, 31))
    fios(f, em(q2, '1', 93, 36), (93, 40))
    fios(f, em(r2, '2', 104, 34), (104, 40))
    if v == 'A':
        # o fio JP1 leva o coletor do Q2 e o R2 (o terra do driver) direto ao source
        fios(f, (100, 29), (102, 29), (104, 29), (114, 29), em(q3, '1', 118, 29))
        rot(f, 'GATE', 114, 29, 0, -1)
        fios(f, (93, 40), (98, 40), (104, 40), (109, 40))
        alim(f, 'GND', 98, 40)
        jp1 = f.peca('Jumper:Jumper_2_Bridged', 'JP1', 'fio por cima', p(111, 40), 0, PE['JP'])
        em(jp1, '1', 109, 40)
        fios(f, em(jp1, '2', 113, 40), (121, 40), (125, 40), (130, 40), (134, 40), (138, 40), (147, 40))
        alim(f, 'GND', 125, 40)
        nota_jp = ['R1 (10 ohm) amortece a ligação, D1 desliga rápido. JP1 é um fio por cima da placa:',
                   'leva o coletor do Q2 e o R2 direto ao source, sem dar a volta por cima do MUR860.',
                   'Serve também de ponto de terra para a garra do osciloscópio.']
    else:
        # com o MOSFET virado, o gate fica do outro lado do dreno: o fio JP1 leva o gate
        fios(f, (100, 29), (102, 29), (104, 29), (107, 29))
        rot(f, 'GATE', 102, 29, 0, -1)
        jp1 = f.peca('Jumper:Jumper_2_Bridged', 'JP1', 'fio do gate', p(109, 29), 0, PE['JP'])
        em(jp1, '1', 107, 29)
        fios(f, em(jp1, '2', 111, 29), (114, 29), em(q3, '1', 118, 29))
        rot(f, 'GATE', 114, 29, 0, -1)
        fios(f, (93, 40), (98, 40), (104, 40), (121, 40), (125, 40), (130, 40), (134, 40), (138, 40), (147, 40))
        alim(f, 'GND', 98, 40)
        nota_jp = ['R1 (10 ohm) amortece a ligação, D1 desliga rápido. Com o MOSFET em pé e a aba',
                   'para a borda, o gate fica do outro lado do dreno: JP1 é o fio por cima que o leva até lá.',
                   'O source fica do lado do driver: o coletor do Q2 volta a ele por trilha direta.']
    fios(f, em(q3, '3', 121, 31), (121, 40))
    # dreno e primário
    j3 = f.peca('Connector_Generic:Conn_01x02', 'J3', 'primário', p(156, 21), 0, PE['MCV2'], espelho=True)
    fios(f, em(q3, '2', 121, 27), (121, 21), (126, 21), (130, 21), (134, 21), (138, 21), (147, 21),
         em(j3, '1', 154, 21))
    rot(f, 'DRENO', 126, 21, 0, -1)
    fios(f, em(j3, '2', 154, 20), (152, 20), (152, 17)); alim(f, '+24V', 152, 17)
    c8 = f.peca('Device:C', 'C8', '100n', p(130, 31), 0, PE['MKP'])
    c9 = f.peca('Device:C', 'C9', '100n', p(134, 31), 0, PE['MKP'])
    c10 = f.peca('Device:C', 'C10', '100n', p(138, 31), 0, PE['MKP'])
    d2 = f.peca('Device:D', 'D2', 'MUR860', p(147, 31), 270, PE['TO220'])
    for peca, x in ((c8, 130), (c9, 134), (c10, 138), (d2, 147)):
        fios(f, (x, 21), em(peca, '1', x, 29.5))
        fios(f, em(peca, '2', x, 32.5), (x, 40))
    notas(f, 63, 44, nota_jp)
    notas(f, 116, 44, ['C8 a C10: 3 x 100 nF de polipropileno (MKP), 400 V DC (250 VAC) = 300 nF.',
                       'Cada um tem dois furos para a perna do dreno: lote de passo 10 ou de 15 mm.',
                       'O C11 (NM) da V3.6 saiu: com o PR5 o dreno já baixa, e 400 nF dão',
                       'a mesma relação de arco por dreno que 300 nF.'])

    notas(f, 8, 58, [
        'Bancada de 21/out/2026 e simulações: docs/hardware-decisoes.md, seção 9, no repositório flyback-midi.',
        'Ponto de trabalho: ~20 us no vale de ~37–39 kHz (dreno ~230 V, -62 V na bobina de 3 espiras). 250 V = -68 V.',
        'Placa de face simples para fresar: cobre só embaixo, sem texto; ligações por cima viram fio (JP1).',
        f'Serigrafia: folha colorida em escala 1:1 para colar na face de cima: fabricacao/{cfg["nome"]}_impressao_topo.pdf.',
        f'Versão {v}: {cfg["resumo"]}.'], 'Notas')
    return f


# =================================================================================== SAÍDAS
def cli(*args):
    r = subprocess.run([CLI, *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode not in (0, 5):   # 5 = DRC com violações, quando pedido
        print(r.stdout, r.stderr)
    return r


COR_FUNDO, COR_PAD, COR_FURO, COR_SILK, COR_BORDA = '#0E5A32', '#D8B04A', '#161616', '#FFFFFF', '#06200F'


def impressao(pcb, pasta, nome, titulo):
    """A face de cima como numa placa de verdade (máscara verde, serigrafia branca, pads dourados e
    furos), em escala 1:1, seis cópias numa A4: imprimir em 100 % e colar sobre a placa.
    Sai também a prévia em PNG de uma cópia."""
    import pymupdf
    tmp = os.path.join(pasta, '_svg')
    esvazia(tmp)
    cli('pcb', 'export', 'svg', '-o', tmp + os.sep, '-l', 'F.Cu,F.SilkS,Edge.Cuts', '--mode-multi',
        '--page-size-mode', '2', '--exclude-drawing-sheet', '--drill-shape-opt', '2', '--black-and-white',
        '--subtract-soldermask', pcb)
    partes, larg, alt, vb = [], None, None, None
    for camada, cor, furo in (('F_Cu', COR_PAD, COR_FURO), ('F_Silkscreen', COR_SILK, None),
                              ('Edge_Cuts', COR_BORDA, None)):
        with open(os.path.join(tmp, f'{nome}-{camada}.svg'), encoding='utf-8') as fh:
            txt = fh.read()
        m = re.search(r'width="([\d.]+)mm" height="([\d.]+)mm" viewBox="([^"]+)"', txt)
        larg, alt, vb = float(m.group(1)), float(m.group(2)), m.group(3)
        corpo = txt[txt.index('>', txt.index('<svg')) + 1: txt.rindex('</svg>')]
        corpo = re.sub(r'<title>.*?</title>|<desc>.*?</desc>', '', corpo, flags=re.S)
        corpo = corpo.replace('#000000', cor)
        if furo:
            corpo = corpo.replace('#FFFFFF', furo)
        partes.append(corpo)
    shutil.rmtree(tmp)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{larg}mm" height="{alt}mm" viewBox="{vb}">'
           f'<rect x="0" y="0" width="{larg}" height="{alt}" rx="0.6" fill="{COR_FUNDO}"/>'
           + ''.join(partes) + '</svg>')
    placa = pymupdf.open('pdf', pymupdf.open(stream=svg.encode('utf-8'), filetype='svg').convert_to_pdf())
    pw, ph = placa[0].rect.width, placa[0].rect.height
    mm = 72 / 25.4
    folha = pymupdf.open()
    pg = folha.new_page(width=210 * mm, height=297 * mm)
    x0, y0, gx, gy = (210 * mm - 2 * pw) / 3, 40 * mm, (210 * mm - 2 * pw) / 3, 14 * mm
    for i in range(3):
        for j in range(2):
            x, y = x0 + j * (pw + gx), y0 + i * (ph + gy)
            pg.show_pdf_page(pymupdf.Rect(x, y, x + pw, y + ph), placa, 0)
            pg.draw_rect(pymupdf.Rect(x - 1.5 * mm, y - 1.5 * mm, x + pw + 1.5 * mm, y + ph + 1.5 * mm),
                         color=(0.6, 0.6, 0.6), width=0.3, dashes='[2 2] 0')
    pg.insert_text((x0, 18 * mm), titulo + ' · face de cima', fontsize=13)
    pg.insert_text((x0, 25 * mm), 'Imprimir em 100 % (tamanho real, sem "ajustar à página"). '
                   'Cada cópia: 85,2 x 39,5 mm.', fontsize=9)
    pg.insert_text((x0, 30 * mm), 'Recortar na linha da borda e colar sobre a face de cima; as pernas '
                   'furam o papel nos furos pretos.', fontsize=9)
    yb = y0 + 3 * ph + 2 * gy + 16 * mm
    pg.draw_line((x0, yb), (x0 + 50 * mm, yb), color=(0, 0, 0), width=0.8)
    for k in range(6):
        pg.draw_line((x0 + 10 * k * mm, yb - 2 * mm), (x0 + 10 * k * mm, yb), color=(0, 0, 0), width=0.5)
    pg.insert_text((x0 + 52 * mm, yb + 1 * mm), '50 mm: confira com uma régua depois de imprimir', fontsize=9)
    folha.save(os.path.join(pasta, nome + '_impressao_topo.pdf'))
    placa[0].get_pixmap(dpi=500).save(os.path.join(pasta, nome + '_impressao_topo.png'))


def previa_cobre(pasta, nome):
    """PNG do cobre visto por baixo, recortado na placa."""
    import pymupdf
    from PIL import Image, ImageOps
    doc = pymupdf.open(os.path.join(pasta, nome + '_cobre_visto_de_baixo.pdf'))
    pix = doc[0].get_pixmap(dpi=300)
    im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    bb = ImageOps.invert(im.convert('L')).getbbox()
    im.crop((bb[0] - 30, bb[1] - 30, bb[2] + 30, bb[3] + 30)).save(os.path.join(pasta, nome + '_cobre.png'))


def saidas(pasta, nome, titulo, pcb):
    """fabricacao/ fica só com o que a fresa pede: contorno (Edge), furação PTH e NPTH e o cobre
    (só B.Cu: a placa é de face simples). Ao lado dela, <nome>_fresa.zip com esses quatro arquivos,
    pronto para enviar. Impressão, vista de baixo e imagens ficam na pasta da versão."""
    fab = os.path.join(pasta, 'fabricacao')
    esvazia(fab)
    cli('pcb', 'export', 'gerbers', '-o', fab + os.sep, '-l', 'B.Cu,Edge.Cuts', '--use-drill-file-origin',
        '--no-protel-ext', pcb)
    cli('pcb', 'export', 'drill', '-o', fab + os.sep, '--format', 'excellon', '--excellon-units', 'mm',
        '--excellon-zeros-format', 'decimal', '--drill-origin', 'plot', '--excellon-separate-th', pcb)
    for f in os.listdir(fab):
        if f.endswith('.gbrjob'):              # o kicad-cli sempre gera; a fresa não usa
            os.remove(os.path.join(fab, f))
    with zipfile.ZipFile(os.path.join(pasta, nome + '_fresa.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(fab)):
            z.write(os.path.join(fab, f), f)
    # visto por baixo, com o contorno do que fica embaixo da placa (B.Fab)
    cli('pcb', 'export', 'pdf', '-o', os.path.join(pasta, nome + '_cobre_visto_de_baixo.pdf'), '-l',
        'B.Cu,B.Fab,Edge.Cuts', '--mode-single', '--mirror', pcb)
    for lado in ('top', 'bottom'):
        cli('pcb', 'render', '-o', os.path.join(pasta, f'{nome}_3d_{lado}.png'), '--side', lado, '--width', '1600',
            '--height', '900', '--quality', 'high', '--background', 'opaque', '--zoom', '1.4', pcb)
    cli('pcb', 'render', '-o', os.path.join(pasta, f'{nome}_3d_perspectiva.png'), '--rotate', '-55,0,0',
        '--zoom', '1.6', '--width', '1600', '--height', '1000', '--quality', 'high', '--background', 'opaque', pcb)
    impressao(pcb, pasta, nome, titulo)
    previa_cobre(pasta, nome)


def gera(v):
    cfg = VERSOES[v]
    pasta = os.path.join(AQUI, cfg['pasta'])
    nome = cfg['nome']
    esvazia(pasta)
    projeto(pasta, nome)
    sch = esquema(v).salvar(os.path.join(pasta, nome + '.kicad_sch'))
    _, rep = erc(sch)
    pdf(sch)
    net, _ = netlist(sch)
    print(f'{nome}: ERC {rep.count("; error")} erros, {rep.count("; warning")} avisos')
    r = subprocess.run([KPY, os.path.join(AQUI, 'pcb_v22.py'), net, v, pasta, nome], capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    print(r.stdout[-1500:])
    if r.returncode:
        print(r.stderr[-3000:])
    projeto(pasta, nome)    # depois da placa: o SaveBoard do pcbnew regrava o .kicad_pro com as regras padrão
    pcb = os.path.join(pasta, nome + '.kicad_pcb')
    rel = os.path.join(pasta, nome + '_drc.rpt')
    cli('pcb', 'drc', '--refill-zones', '--save-board', '--schematic-parity', '--severity-all', '-o', rel, pcb)
    txt = open(rel, encoding='utf-8', errors='replace').read()
    print(f'{nome}: DRC {txt.count("; error")} erros, {txt.count("; warning")} avisos, '
          f'{re.search(r"Found (\d+) unconnected", txt).group(1)} pads desligados')
    saidas(pasta, nome, cfg['titulo'], pcb)


if __name__ == '__main__':
    footprints()
    for v in (sys.argv[1:] or ['A', 'B']):
        gera(v.upper())
