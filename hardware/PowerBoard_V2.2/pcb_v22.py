"""Monta a PCB da PowerBoard V2.2 (versão A ou B) a partir da netlist. Roda no Python do KiCad 10:

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" pcb_v22.py <netlist> <A|B> <pasta> <nome>

Chamado pelo gerar_v22.py. Coordenadas (u, v) em mm a partir do canto superior esquerdo da placa,
v para baixo, iguais às da PowerBoard V3 do EasyEDA (u = x - 52,578; v = 6,477 - y).
Face simples: o cobre fica todo na B.Cu, só com pads, trilhas e zonas (nada de texto, para a fresa
não perder tempo). Referências, valores e avisos vão na F.SilkS, que sai na folha impressa.
As zonas são preenchidas depois, pelo kicad-cli, com as regras do .kicad_pro e do .kicad_dru.

Versões:
  A: IRFP264N deitado embaixo da placa (pads G-D-S da esquerda para a direita). O fio JP1 leva o
     terra do driver ao source, que fica do outro lado do dreno.
  B: IRFP264N em pé na face de cima, aba para a borda de baixo (pads S-D-G). O source fica do lado
     do driver e o fio JP1 leva o gate.
"""
import os
import re
import sys

import pcbnew

AQUI = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(AQUI, 'FBMD.pretty')
X0, Y0 = 100.0, 60.0          # canto superior esquerdo da placa na folha
W, H = 85.2, 39.5             # mesmo tamanho da V3 (85,217 x 39,497)

# ------------------------------------------------------------------ posições: pad 1 (u, v) e rotação
MKP_U = (53.784, 61.341, 68.897)          # colunas dos MKP da V3 (C6, C14, C15 do EasyEDA)
BANCO_U = (22.352, 37.846, 53.340, 68.834)
POS = {
    # potência: igual à V3
    'J1': (7.493, 14.776, 90),            # XT60: pino 1 (chanfrado, GND) embaixo, +24V em cima
    'C1': (BANCO_U[0], 7.533, 270), 'C2': (BANCO_U[1], 7.533, 270),
    'C3': (BANCO_U[2], 7.533, 270), 'C4': (BANCO_U[3], 7.533, 270),
    'D2': (41.656, 20.447, 0),            # MUR860: catodo à esquerda, aba para cima
    'C8': (MKP_U[0], 19.32, 270), 'C9': (MKP_U[1], 19.32, 270), 'C10': (MKP_U[2], 19.32, 270),
    'J3': (78.232, 29.21, 90),            # primário: pino 1 (dreno) embaixo, +24V em cima
    # driver (onde ficavam o FOD3184, o 7815 e o CN1), afastado do XT60
    'P2': (4.2, 26.0, 270),               # 12V, GND, SIN de cima para baixo
    'C6': (11.2, 26.0, 270),
    'C7': (16.8, 23.2, 0),
    'Q1': (16.8, 26.0, 270),              # C B E de cima para baixo
    'Q2': (21.8, 26.0, 270),
    'R2': (29.8, 28.8, 90),               # gate embaixo, GND em cima
    'D1': (24.38, 33.5, 0),               # catodo no DRV, anodo no gate
    'R1': (21.84, 36.6, 0),
    'JP1': (33.0, 23.6, 0),               # fio por cima, sobre o dreno
}
# IRFP264N: os pads ficam onde estão; o que muda é qual deles é o gate
Q3 = {
    'A': (36.206, 28.321, 0),             # deitado embaixo, corpo para dentro: G à esquerda
    'B': (47.106, 28.321, 180),           # em pé, aba para a borda de baixo: G à direita
}

# furos M3 dos standoffs de nylon (só na placa, fora do esquema). O de cima à esquerda fica entre o
# XT60 e o C1 porque o canto está ocupado pelo XT60.
FUROS = [(15.2, 2.9), (82.3, 2.9), (82.3, 36.6), (2.9, 36.6)]

# rótulo da folha impressa (referência e valor na F.SilkS), quando o meio dos pads não serve:
# ref -> (u, v da referência, u, v do valor); None = esconder (o footprint já traz o texto)
#        valor None = escondido (vai na legenda, porque ao lado da peça ficaria embaixo dos pads)
ROTULO = {r: (u, 4.9, u, 10.0) for r, u in zip(('C1', 'C2', 'C3', 'C4'), BANCO_U)}
ROTULO.update({
    'J1': (7.493, 11.18, 7.493, 18.3),
    'P2': (5.5, 23.2, 1.0, 28.54),       # pinagem na vertical, lida de cima para baixo como os pinos
    'C6': (11.2, 24.6, 11.2, 31.6),
    'D2': (40.3, 16.55, 45.5, 16.55),    # acima do corpo
    'J3': (74.9, 20.3, 79.6, 20.3),
    'JP1': (36.2, 22.75, 43.2, 22.75),   # acima do fio, abaixo do MUR860
    'Q1': (16.8, 32.55, None, None),
    'Q2': (21.8, 32.55, None, None),
    'D1': (28.19, 33.5, None, None),
})
LEGENDA = ('Q1', 'Q2', 'D1')
ROTULO_Q3 = {'A': None, 'B': (41.656, 32.0, 41.656, 33.2)}

# trilhas: (rede, largura, pontos)
TRILHAS = [
    ('+12V', 1.0, [(4.2, 26.0), (11.2, 26.0), (16.8, 26.0), (16.8, 23.2)]),
    ('/GATE_DRV', 1.0, [(4.2, 31.08), (14.0, 31.08), (14.0, 28.54), (16.8, 28.54), (21.8, 28.54)]),
    ('/DRV', 1.2, [(16.8, 31.08), (21.8, 31.08), (21.8, 33.5), (24.38, 33.5)]),
    ('/DRV', 1.2, [(21.8, 33.5), (21.84, 36.6)]),
    ('/GATE', 1.2, [(32.0, 28.8), (32.0, 33.5), (32.0, 36.6)]),
    ('GND', 1.0, [(4.2, 28.54), (11.2, 28.5)]),
]
TRILHAS_V = {
    'A': [
        ('/GATE', 1.2, [(36.206, 28.321), (32.0, 28.8), (29.8, 28.8)]),
        # terra do driver até o JP1, que o leva por cima do dreno até o source
        ('GND', 1.2, [(21.8, 23.2), (21.8, 26.0), (25.0, 26.0), (27.4, 23.6), (33.0, 23.6)]),
    ],
    'B': [
        # gate: do driver até o JP1; do outro lado do fio, até o pad do gate
        ('/GATE', 1.2, [(29.8, 28.8), (32.0, 28.8), (33.0, 26.0), (33.0, 23.6)]),
        ('/GATE', 1.2, [(49.0, 23.6), (47.106, 26.5)]),
        # terra do driver direto ao source, por cima do JP1 e por baixo do R2
        ('GND', 1.2, [(21.8, 23.2), (21.8, 26.0), (25.0, 26.0), (27.4, 21.0), (35.2, 21.0), (36.206, 26.5)]),
    ],
}

# zonas: (rede, prioridade, contorno). O GND cobre a placa toda; o dreno e o +24V passam por cima.
ZONAS = [
    ('GND', 0, [(0, 0), (W, 0), (W, H), (0, H)]),
    ('+24V', 1, [(0.5, 0.5), (84.7, 0.5), (84.7, 26.0), (74.0, 26.0), (74.0, 10.0), (0.5, 10.0)]),
    ('/DRENO', 2, [(40.15, 18.6), (43.15, 18.6), (43.15, 32.0), (50.6, 32.0), (50.6, 26.2), (84.7, 26.2),
                   (84.7, 39.0), (39.2, 39.0), (39.2, 32.0), (40.15, 32.0)]),
]

# textos da serigrafia (F.SilkS): (texto, u, v, altura, ângulo)
SILK = [
    ('+24V', 13.9, 7.6, 1.1, 0),           # pinos do XT60
    ('GND', 13.9, 14.8, 1.1, 0),
    ('+24V', 83.0, 24.13, 1.0, 90),        # pinos do J3
    ('DRENO', 83.0, 29.8, 1.0, 90),
    ('K', 38.3, 20.45, 1.1, 0),            # catodo do MUR860
    ('MKP 400V', 61.3, 16.3, 1.0, 0),
]
SILK_V = {
    'A': [('PowerBoard V2.2A', 13.2, 36.75, 0.95, 0), ('MOSFET embaixo · 2026-11', 13.2, 38.2, 0.75, 0),
          ('G', 36.206, 31.25, 1.1, 0)],
    'B': [('PowerBoard V2.2B', 13.2, 36.75, 0.95, 0), ('MOSFET em pé · 2026-11', 13.2, 38.2, 0.75, 0),
          ('G', 47.106, 31.6, 1.1, 0), ('aba para a borda', 41.656, 34.4, 0.8, 0)],
}


def mm(x):
    return pcbnew.FromMM(x)


def P(u, v):
    return pcbnew.VECTOR2I(mm(X0 + u), mm(Y0 + v))


def le_netlist(caminho):
    t = open(caminho, encoding='utf-8').read()
    comp_txt = t.split('(libparts')[0]
    comps = {}
    for bloco in re.split(r'\(comp\s', comp_txt)[1:]:
        ref = re.search(r'\(ref "([^"]+)"\)', bloco).group(1)
        val = re.search(r'\(value "([^"]*)"\)', bloco).group(1)
        fp = re.search(r'\(footprint "([^"]*)"\)', bloco).group(1)
        ts = re.findall(r'\(tstamps "([^"]+)"\)', bloco)[-1]
        comps[ref] = (val, fp, ts)
    nets = {}
    for m in re.finditer(r'\(net\s+\(code "\d+"\)\s+\(name "([^"]+)"\)(.*?)\n\t\t\)', t, re.S):
        for ref, pin in re.findall(r'\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', m.group(2)):
            nets[(ref, pin)] = m.group(1)
    return comps, nets


def rotulo(fp, ref, onde):
    """Folha impressa: referência e valor (${VALUE} na F.SilkS) na horizontal, um sobre o outro no
    meio dos pads, ou onde `onde` mandar. O campo Value fica escondido."""
    r = fp.Reference()
    fp.Value().SetVisible(False)
    if onde is None and ref in ('Q3',):
        r.SetVisible(False)
        return
    us = [pcbnew.ToMM(p.GetPosition().x) - X0 for p in fp.Pads()]
    vs = [pcbnew.ToMM(p.GetPosition().y) - Y0 for p in fp.Pads()]
    uc, vc = (min(us) + max(us)) / 2, (min(vs) + max(vs)) / 2
    ru, rv, vu, vv = onde or (uc, vc - 0.65, uc, vc + 0.65)
    r.SetLayer(pcbnew.F_SilkS)
    r.SetTextSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
    r.SetTextThickness(mm(0.15))
    r.SetTextAngleDegrees(0)
    r.SetPosition(P(ru, rv))
    for item in list(fp.GraphicalItems()):
        t = item.Cast()
        if isinstance(t, pcbnew.PCB_TEXT) and t.GetText() == '${VALUE}':
            if vu is None:                # vai na legenda (texto de usuário não se esconde: sai da peça)
                fp.Remove(t)
                continue
            t.SetKeepUpright(False)       # senão o KiCad desvira o texto do P2 e a pinagem sai invertida
            t.SetTextAngleDegrees(270 if ref == 'P2' else 0)
            t.SetPosition(P(vu, vv))


def main(net_arq, v, pasta, nome):
    comps, nets = le_netlist(net_arq)
    pos = dict(POS, Q3=Q3[v])
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    ds = board.GetDesignSettings()
    ds.SetAuxOrigin(P(0, H))              # origem de furação e Gerber no canto inferior esquerdo
    ds.SetGridOrigin(P(0, H))

    borda = pcbnew.PCB_SHAPE(board)
    borda.SetShape(pcbnew.SHAPE_T_RECT)
    borda.SetStart(P(0, 0))
    borda.SetEnd(P(W, H))
    borda.SetLayer(pcbnew.Edge_Cuts)
    borda.SetWidth(mm(0.1))
    board.Add(borda)

    redes = {}
    for n in sorted(set(nets.values())):
        ni = pcbnew.NETINFO_ITEM(board, n)
        board.Add(ni)
        redes[n] = ni

    faltam = [r for r in comps if r not in pos]
    assert not faltam, f'sem posição: {faltam}'
    pecas = {}
    for ref, (val, fpid, ts) in sorted(comps.items()):
        lib, nfp = fpid.split(':')
        fp = pcbnew.FootprintLoad(LIB, nfp)
        assert fp is not None, fpid
        fp.SetFPID(pcbnew.LIB_ID(lib, nfp))
        fp.SetReference(ref)
        fp.SetValue(val)
        fp.SetPath(pcbnew.KIID_PATH('/' + ts))
        fp.SetSheetname('/')
        fp.SetSheetfile(nome + '.kicad_sch')
        u, vv, ang = pos[ref]
        fp.SetPosition(P(u, vv))
        fp.SetOrientationDegrees(ang)
        board.Add(fp)
        for pad in fp.Pads():
            rede = nets.get((ref, pad.GetNumber()))
            if rede:
                pad.SetNet(redes[rede])
        rotulo(fp, ref, ROTULO_Q3[v] if ref == 'Q3' else ROTULO.get(ref))
        pecas[ref] = fp

    val = {r: c[0] for r, c in comps.items()}
    legenda = [(f'Q1 {val["Q1"]}  Q2 {val["Q2"]}', 13.2, 34.0, 0.85, 0), (f'D1 {val["D1"]}', 13.2, 35.35, 0.85, 0)]
    for s, u, vv, alt, ang in SILK + SILK_V[v] + legenda:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(pcbnew.VECTOR2I(mm(alt * 0.9), mm(alt)))
        t.SetTextThickness(mm(0.15 if alt < 1.0 else 0.18))
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetPosition(P(u, vv))
        t.SetTextAngleDegrees(ang)
        board.Add(t)

    for i, (u, vv) in enumerate(FUROS, 1):
        fp = pcbnew.FootprintLoad(LIB, 'Furo_M3_CNC')
        fp.SetFPID(pcbnew.LIB_ID('FBMD', 'Furo_M3_CNC'))
        fp.SetReference(f'H{i}')
        fp.SetValue('M3')
        fp.SetBoardOnly(True)
        fp.SetPosition(P(u, vv))
        board.Add(fp)

    for rede, larg, pts in TRILHAS + TRILHAS_V[v]:
        for a, b in zip(pts[:-1], pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(P(*a))
            t.SetEnd(P(*b))
            t.SetWidth(mm(larg))
            t.SetLayer(pcbnew.B_Cu)
            t.SetNet(redes[rede])
            board.Add(t)

    for rede, prio, pts in ZONAS:
        z = pcbnew.ZONE(board)
        z.SetLayer(pcbnew.B_Cu)
        z.SetNet(redes[rede])
        ol = z.Outline()
        ol.NewOutline()
        for u, vv in pts:
            ol.Append(mm(X0 + u), mm(Y0 + vv))
        z.SetAssignedPriority(prio)
        z.SetMinThickness(mm(0.6))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetZoneName(rede.strip('/'))
        board.Add(z)

    saida = os.path.join(pasta, nome + '.kicad_pcb')
    pcbnew.SaveBoard(saida, board)
    # conferência: onde cada pad caiu, em (u, v)
    for ref in ('Q3', 'JP1', 'D2', 'R2'):
        pads = [f'{p.GetNumber()}:{pcbnew.ToMM(p.GetPosition().x) - X0:.2f},{pcbnew.ToMM(p.GetPosition().y) - Y0:.2f}'
                f'[{p.GetNetname()}]' for p in pecas[ref].Pads()]
        print(ref, ' '.join(pads))
    print('salvo', saida)


if __name__ == '__main__':
    main(*sys.argv[1:5])
