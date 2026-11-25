# PowerBoard V2.2: placa de potência fresada (face simples)

É a PowerBoard V2.1 (totem pole) com as correções da V3.6, montada no desenho da PowerBoard V3 do EasyEDA:

- o tamanho é o mesmo, 85,2 × 39,5 mm;
- as peças de potência estão nas mesmas posições;
- saíram o FOD3184, o 7815 e os capacitores de 15 V;
- o gate é acionado pelo totem pole BC337/BC327, alimentado com os 12 V que vêm da placa de controle.

O nome é V2.2 porque já existe uma `PowerBoardV2_1.schdoc` no Altium: é o totem pole com zener, 22 Ω e IRFP260N.

## Duas versões

| Pasta | IRFP264N | Para quê |
|---|---|---|
| `A_mosfet_embaixo/` (V2.2A) | Deitado **embaixo** da placa, com a aba no dissipador que serve de base do conjunto | A ideia principal |
| `B_mosfet_em_pe/` (V2.2B) | Em pé na face de cima, com a aba virada para a borda de baixo | Reserva, se a A não der certo |

Muda pouco entre as duas:

- **O mesmo:** tamanho, todas as outras peças e quase todo o cobre.
- **Pads do IRFP264N:** ficam no mesmo lugar, mas trocam o gate e o source de lado. Na A a ordem é G-D-S da esquerda para a direita; na B, S-D-G.
- **Fio JP1:** sempre passa por cima do dreno, mas leva coisas diferentes:
  - na **A**, o terra do driver até o source, que fica do outro lado do dreno;
  - na **B**, o gate até o MOSFET. O source fica do lado do driver e é ligado por trilha.

## Arquivos

| Arquivo | O que é |
|---|---|
| `gerar_v22.py` | Gera as duas versões: `python gerar_v22.py` (ou só uma: `python gerar_v22.py B`). |
| `pcb_v22.py` | Posições, trilhas, zonas e textos. Roda no Python do KiCad; o `gerar_v22.py` chama. |
| `FBMD.pretty/` | Footprints para fresar, comuns às duas versões. |
| `<versão>/PowerBoard_V2.2X.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, `.kicad_dru` | Projeto do KiCad 10. ERC e DRC sem erros, DRC com paridade de esquema. O `.kicad_dru` põe 1,5 mm entre +24V e GND. |
| `<versão>/*_impressao_topo.png`, `*_cobre.png`, `*_3d_*.png` | Prévias. |

Para mudar a placa, edite o `gerar_v22.py` (esquema e footprints) ou o `pcb_v22.py` (layout) e rode de novo. Mexer no KiCad à mão também funciona, mas a próxima geração sobrescreve.

Gerar de novo pede o KiCad 10 e a pasta do projeto inteira, não só o repositório: o `gerar_v22.py` usa a biblioteca `FlybachSimulations/lib/kicad_sch.py` e o modelo `FlybachSchems/FlybachSchems.kicad_pro`, que ficam fora do git, e os acha subindo pastas a partir de onde está. Para só abrir no KiCad ou mandar para a fresa, esta pasta basta.

Em `<versão>/fabricacao/` fica só o que a fresa pede, todos com a origem (0, 0) no canto inferior esquerdo da placa. Os mesmos quatro arquivos estão em `<versão>/PowerBoard_V2.2X_fresa.zip`, pronto para enviar:

- `*-B_Cu.gbr`: o cobre, só com pads, trilhas e áreas, sem texto (menos tempo de fresa). É o único cobre, porque a placa é de face simples. Fica embaixo, mas o arquivo está desenhado visto de cima, como todo Gerber.
- `*-Edge_Cuts.gbr`: o contorno.
- `*-PTH.drl`: os furos das peças (Excellon, em mm).
- `*-NPTH.drl`: os 4 furos M3 de fixação.

Na pasta da versão ficam também:

- `*_impressao_topo.pdf`: a serigrafia em cores, para colar por cima (próxima seção).
- `*_cobre_visto_de_baixo.pdf`: o cobre espelhado, como fica na placa. Na A, mostra também o contorno do MOSFET deitado.

## Serigrafia impressa

O `*_impressao_topo.pdf` desenha a face de cima como numa placa industrial: máscara verde, serigrafia branca, pads dourados e furos pretos. Traz a referência e o valor de cada peça e as marcas de polaridade. São seis cópias em tamanho real numa folha A4, para quatro placas e duas de reserva.

1. Imprima em **100 %** (tamanho real, sem "ajustar à página") e confira a régua de 50 mm com uma régua de verdade.
2. Recorte na linha da borda e cole sobre a face de cima, com cola em bastão ou fita dupla-face fina, alinhando pelos furos.
3. Fure o papel nos furos pretos com uma agulha, ou deixe as próprias pernas furarem. Uma fita transparente por cima protege o papel do fluxo de solda.

Os valores de Q1, Q2 e D1 estão na legenda do canto de baixo à esquerda; ao lado de cada peça não cabiam.

## No FlatCAM

1. **Espelhar.** Abra o cobre, o contorno e os furos. Espelhe os três juntos no eixo Y, com a ferramenta *2-Sided PCB* e o contorno como caixa de referência. O cobre é cortado com a placa virada para baixo.
2. **Isolação.** A folga é de 1,5 mm em volta do dreno e entre o +24V e o GND; no resto, de 0,5 mm ou mais. Com poucas passadas, sobra uma tira de cobre solta no meio das folgas de 1,5 mm. Use passadas suficientes para limpar 1,5 mm, ou rode *NCC* nessas regiões.
3. **Furos.** São 51 furos em seis diâmetros:

   | Broca | Furos | Peças |
   |---|---|---|
   | 0,8 mm | 16 | resistores, diodo, BC, C7, 47 µF |
   | 1,0 mm | 14 | MKP, P2, JP1 |
   | 1,2 mm | 10 | eletrolíticos do banco, MUR860 |
   | 1,6 mm | 5 | IRFP264N, borne do primário |
   | 3,2 mm | 4 | H1 a H4, fixação nos standoffs (M3) |
   | 4,5 mm | 2 | XT60 |

   Os furos de 3,2 e 4,5 mm podem ser fresados com uma fresa menor.

## Montagem (as duas versões)

- **XT60:** o lado chanfrado é o GND, como na V3.
- **P2:** Molex KK de 3 vias, com 12V, GND e SIN nessa ordem, de cima para baixo. É a mesma ordem do J3 do controle.
- **J3:** borne de encaixe de 5,08 mm (2EDG), onde vai o primário. O pino de cima é +24V e o de baixo é o dreno.
- **C8 a C10:** cada um tem dois furos para a perna do dreno, um para o lote de passo 10 mm e outro para o de 15 mm.
- **JP1:** fio rígido por cima da placa, entre os dois furos a 16 mm. Na versão A, também serve para prender a garra do osciloscópio.
- **Pad quadrado é o pino 1:** o + dos eletrolíticos, o catodo dos diodos, o gate do MOSFET e o coletor dos BC.
- **Furos H1 a H4 (M3):** para os standoffs de nylon. O de cima à esquerda fica entre o XT60 e o C1, porque o canto é do XT60. O H3, embaixo à direita, fica no cobre do dreno: o cobre está a 1,5 mm do furo, mas use parafuso de nylon ali.
- **MUR860:** em pé, com a aba para o lado do banco, como na V3.
- **Aba do IRFP264N = dreno:** chega a ~230–250 V em pulsos. Ponha uma isolação entre a aba e o dissipador (mica ou silicone, com bucha isolante no parafuso). Sem ela, o dissipador vira dreno.

### Versão A: MOSFET embaixo

Para os pinos caírem certo nos pads:

- o corpo deita **para dentro da placa**, embaixo do MUR860 e do C2;
- a face escrita fica virada para a placa e a aba vai no dissipador;
- as pernas saem para o lado da borda de baixo e sobem dobradas a 90° para os furos;
- assim a ordem é G-D-S como nos pads. Deitado para fora da placa, G e S trocariam.

O "G" da serigrafia marca o gate. A montagem pede ainda:

- **Fixação:** o furo do MOSFET fica embaixo do C2. Prenda pelo lado do dissipador (parafuso por baixo, porca do lado do MOSFET) ou com uma presilha.
- **Standoffs:** de ~10 mm. Cabem o MOSFET (5 mm), a isolação e as pontas das soldas da placa; as pernas do TO-247 (~20 mm) dão para a dobra.

### Versão B: MOSFET em pé

- **Posição:** o IRFP264N fica em pé, com a aba virada para a borda de baixo. O gate fica à direita, do lado dos MKP, e está marcado com "G" na serigrafia.
- **Dissipador:** vai preso na aba, do lado da borda. Ele passa por cima da parte de baixo da placa e pode sair para fora dela.
  - Se for mais largo que ~17 mm, fica por cima do D1 e do R1: deixe-o suspenso, sem encostar na placa.
- **Fio JP1:** leva o gate por cima do dreno. Deixe-o curto e rente à placa.

## Lista de peças

| Ref | Peça |
|---|---|
| C1 a C4 | 470 µF 35 V, 12,5 mm, passo 5 mm |
| C6 | 47 µF 25 V, 6,3 mm, passo 2,5 mm |
| C7 | 100 nF cerâmico, passo 5 mm |
| C8 a C10 | 100 nF MKP, 400 V DC (250/275 VAC) |
| D1 | 1N4148 |
| D2 | MUR860 |
| J1 | XT60 macho para PCB |
| J3 | borne de encaixe 5,08 mm, 2 vias (2EDG) |
| JP1 | fio rígido de até 0,8 mm |
| P2 | Molex KK 254, 3 vias |
| Q1, Q2 | BC337, BC327 |
| Q3 | IRFP264N |
| R1 | 10 Ω, 1/4 W |
| R2 | 10 kΩ, 1/4 W |
| H1 a H4 | standoffs e parafusos M3 de nylon |

## O que mudou da V3 do EasyEDA

- **Driver.** Saiu o driver isolado: FOD3184, 7815, CN1, R3, os capacitores de 15 V e o jumper que levava os 24 V ao 7815. Entrou o totem pole, alimentado pelos 12 V do controle.
- **Gate.** 10 Ω em paralelo com o 1N4148 (antes 22 Ω), e 10 kΩ para o GND.
- **Cerâmico do 24 V.** Não há mais. O 100 nF da V3 era o da entrada do 7815; a 40 kHz, ao lado de 1880 µF, ele não muda nada. Por isso não existe C5: as referências seguem as da V3.6, sem o C5 e sem o C11.
- **C11.** O C11 da V3.6 (quarto MKP, não montado) não entrou: não cabe sem apertar o driver, e com o PR5 o dreno já baixa.
- **+24V e GND.** A folga entre os dois é de 1,5 mm (antes 0,6 mm). Eles correm lado a lado pela placa toda, e uma rebarba da fresa ou um respingo de solda curtaria a fonte. Os pads do XT60 são ovais, para dar 1,6 mm entre os pinos.
- **Furos.** 1,6 mm no TO-247 e no borne; antes eram rasgos de 1,0 × 1,8 mm e furos de 1,7 mm. Entraram quatro furos M3 para os standoffs; a V3 não tinha.
- **Texto no cobre.** Não há: a serigrafia vai impressa e colada por cima.
- **XT60.** Na V3.6, o J1.1 era o +24V. Aqui o pino 1 é o GND, que é o lado chanfrado do XT60.

O Gerber original da V3 está em `FlybachSchems/PowerBoardV3_EasyEDA/`, fora do repositório: é a versão com o FOD3184, que não vai ser fabricada agora.
