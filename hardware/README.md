# Hardware

As placas do flyback musical que valem hoje. As decisões por trás de cada uma estão em
[`docs/hardware-decisoes.md`](../docs/hardware-decisoes.md).

| Placa | Versão em uso | Onde |
|---|---|---|
| Potência | **V2.2**: totem pole, IRFP264N, face simples, para fresadora | [`PowerBoard_V2.2/`](PowerBoard_V2.2/) |
| Controle | V3.6: 2× NE555, LM311, entrada pelo ESP32 (6N136 + BC547) | só o esquema, em `FlybachSchems/V3.6/`, fora deste repositório |

A V2.2 tem duas versões, que mudam só a montagem do MOSFET:

- **A** (`A_mosfet_embaixo/`): a principal. O IRFP264N vai deitado embaixo da placa, com a aba no
  dissipador, que serve de base.
- **B** (`B_mosfet_em_pe/`): a reserva, com o IRFP264N em pé na face de cima.

O que a fresa pede (contorno, furação PTH e NPTH, cobre) está em `<versão>/fabricacao/` e, os
mesmos quatro arquivos, em `<versão>/PowerBoard_V2.2X_fresa.zip`. A serigrafia sai impressa em
cores para colar por cima: `<versão>/PowerBoard_V2.2X_impressao_topo.pdf`. O resto está no
[README da placa](PowerBoard_V2.2/README.md).

## O que fica fora

- **PowerBoard V3** (EasyEDA, com FOD3184 e 7815): substituída pela V2.2, que voltou ao totem
  pole. O Gerber está em `FlybachSchems/PowerBoardV3_EasyEDA/`.
- **Esquemas do Altium** (`FlybachSchems/Musical Flyback - FBMD (V1-V4)/`): versões antigas, sem
  as mudanças feitas depois.
- **Simulações** (`FlybachSimulations/`): os scripts de cada resultado aparecem citados nos
  documentos.

## Regenerar

A V2.2 é gerada por script (`gerar_v22.py` e `pcb_v22.py`): para mudar a placa, mude o script e
rode de novo, em vez de editar no KiCad à mão. Isso pede o KiCad 10 e a pasta do projeto inteira,
porque o gerador usa a biblioteca `FlybachSimulations/lib/kicad_sch.py` e o modelo
`FlybachSchems/FlybachSchems.kicad_pro`, que não estão no git. Para abrir no KiCad ou mandar para a
fresa, esta pasta basta.
