# Bancada: gravar e testar o firmware no ESP32

Roteiro para o computador que tem o ESP32 no USB — feito para ser seguido pelo Claude Code
dessa máquina (peça: "siga docs/bancada-esp32.md") ou à mão. O firmware foi escrito em outro
computador, sem placa e **sem compilar**: o passo 2 é a primeira compilação dele, e erro ali é
esperado e deve ser corrigido no próprio `firmware/flyback-esp32/flyback-esp32.ino`.

Ao terminar, anote o resultado em **Resultados**, no fim deste arquivo, e faça commit e push:
é assim que a sessão do outro computador fica sabendo o que aconteceu.

**Mudou em 11/out:** o teste passou a ser na placa **V3.6** (lógica direta). O firmware veio com
`LOGICA_INVERTIDA = false` e ganhou a mensagem `D` (tom contínuo), e o gerador de tom (`tom.html`)
ganhou o modo "ESP32 pela serial". Se este repositório foi clonado antes, rode `git pull` antes
do passo 2.

**Mudou em nov/2026:** envelope e força das notas no arco (mensagem `E` e o quarto campo do
`N`), pela fração aberta de cada período. O `testar_serial.py` ganhou o teste de envelope. Resumo
em `docs/atualizacoes.md`. **Grave o firmware de novo** depois do `git pull`.

**Mudou em 25/nov:** conexão também pelo **Bluetooth** (BLE), no computador e no Chrome do Android,
além da USB — o seletor fica ao lado do Conectar, no player e no gerador de tom. Na bancada a placa
passou a ser o **ESP32-S3** (N16R8), que precisa de `CDCOnBoot=cdc` para a serial sair pela USB
nativa (passo 2). O botão BOOT só vale apertado por 80 ms, e a página e o `testar_serial.py`
reiniciam o ESP sem o modo de gravação ao abrir a porta do CH343. **Grave o firmware de novo.**

**Mudou de novo em 16 e 21/out** — o resumo de tudo, com o porquê, está em
`docs/atualizacoes.md`. No firmware: motivo do último reinício no `?`, pinos da flash recusados e o
teste pelo botão BOOT, sem computador. No gerador de tom: placa e pino escolhidos na página, e só o
canal 1 configurado. **Grave o firmware de novo** depois do `git pull`.

## O teste de agora

- **Placa:** ESP32-S3 DevKit N16R8 (16 MB de flash, 8 MB de PSRAM, duas entradas USB: a nativa,
  `USB-Serial/JTAG`, VID 303A, e a do conversor CH343), desde 25/nov. Antes, o ESP32 comum ("ESP32
  Dev Module"; o "S1" de `hardware-decisoes.md`). O S3 só tem 4 canais (4 timers do LEDC) e só
  Bluetooth LE — que é o que o navegador usa.
- **Flybacks:** 2, placas de controle **V3.6** — a NOTA entra pelo optoacoplador 6N136 e
  passa pelo Q1 até o RESET do 555 monoestável (U13). As duas inversões se anulam: lógica
  **direta**, GPIO em ALTO libera o arco; BAIXO, solto, em boot ou ESP desligado, o arco fica
  cortado. É o `LOGICA_INVERTIDA = false` do firmware, que já vem assim.
- **Áudio não serve:** a entrada da V3.6 é lógica, e o P2 do computador não a aciona. Tudo passa
  pelo ESP: o player e o gerador de tom.
- **Pinos:** o circuito está no **GPIO 4** (canal 1). Os padrões do firmware para o ESP32 comum
  são 18, 19, 21, 22, 23 e 25; quem manda é a página (`P`), e o GPIO 4 é também o pino do teste
  pelo botão BOOT.
- **Firmware:** o v1, que liga e desliga o arco na frequência da nota, mais o `D` do gerador de
  tom: tom contínuo com a fração aberta de cada período (500 ‰ = onda quadrada, o volume
  máximo), que apaga sozinho 2 s depois do último `D`; e o teste pelo botão BOOT (440 Hz no GPIO
  4). Desde nov/2026, também o envelope e a força de cada nota, pela fração aberta (`E` e o
  quarto campo do `N`). O envelope pelo pino ENV (`docs/envelope-v5.md`) é para a placa V5, que
  ainda não existe; não faz parte deste teste.

Contexto para quem não conhece o projeto: `CLAUDE.md` (seção "Saída serial") e
`docs/protocolo-serial.md`, que descreve as mensagens e, no fim, o firmware.

## Segurança antes de tudo

Na V3.6 **falta de sinal corta o arco**: com o ESP em boot, travado, desligado ou com o cabo
solto, o LED do 6N136 fica apagado e o 555 parado. O que liga o arco é o GPIO em ALTO.

- Os passos 1 a 6 são **sem a placa de potência ligada** — o ESP sozinho, ou com o osciloscópio
  ou um LED (com resistor) nos GPIO 18 e 19.
- Mesmo assim: ligue a potência com o ESP já rodando e desligue antes de tirar o USB. Um firmware
  com `LOGICA_INVERTIDA = true` gravado por engano deixaria os GPIO em ALTO parados, com o arco
  ligado direto — confira a linha "lógica direta" no passo 5 antes de ligar a potência.
- Não é preciso pull-up nos GPIO de nota (era para a V3.5). O R5 da placa fica.

## 1. Ferramentas

Windows:

```
winget install ArduinoSA.CLI
arduino-cli config init
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32
pip install pyserial
```

(Depois do `winget`, abra um terminal novo para o `arduino-cli` entrar no PATH. O pacote do
ESP32 baixa algumas centenas de MB.)

Se o ESP não aparecer como porta COM no passo 3, falta o driver do conversor USB da placa:
CP210x (Silicon Labs) ou CH340 (WCH), conforme o chip ao lado do conector.

## 2. Compilar

ESP32-S3 — `CDCOnBoot=cdc` é obrigatório: sem ele a serial vai para a UART0 e nada sai pela USB
nativa (o firmware avisa na compilação):

```
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/flyback-esp32
```

ESP32 comum:

```
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/flyback-esp32
```

Com o Bluetooth o programa cresce: 629 KB no S3 e 1,1 MB no ESP32 comum (84% da partição padrão
de 1,25 MB), com o pacote 3.3.12. Compila também com o pacote 2.0.17 (o do PlatformIO).

Se der erro, corrija no `.ino` e compile de novo. Pontos mais prováveis, porque dependem da versão
do pacote: os nomes do `driver/ledc.h` (`LEDC_AUTO_CLK`, `ledc_timer_config_t`,
`ledc_channel_config_t`), a macro `SOC_LEDC_SUPPORT_HS_MODE` e o `Serial.printf`. Anote em
Resultados a versão do pacote (`arduino-cli core list`) e o que precisou mudar.

## 3. Achar a porta

```
arduino-cli board list
```

## 4. Gravar

```
arduino-cli upload -p COM5 --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/flyback-esp32
```

(No ESP32 comum, `--fqbn esp32:esp32:esp32`.) Trocando `COM5` pela porta do passo 3. No S3 grava
por qualquer das duas entradas USB, e o firmware ouve as duas. Se aparecer "Failed to connect", segure o botão BOOT da
placa enquanto o upload começa.

## 5. Testar pela serial, sem o site

```
python firmware/testar_serial.py COM5
```

Esperado:

- `← flyback-esp32 pronto · nov/2026 · envelope · lógica direta (ALTO libera o arco) · 6 canais · reinício: ...`
  (sem o `nov/2026 · envelope`, a placa está com o firmware antigo: grave de novo)
- a resposta do `?` com `lógica direta`, os pinos `18 19 21 22 23 25`, `ligado há N s` e
  `último reinício: ...`
- no osciloscópio (ou no LED): GPIO 18 e 19 **em BAIXO parados**; onda quadrada de 440 Hz e 50%
  por 1 s em cada um, um de cada vez; depois a escala no 18; depois três notas de 220 Hz e 2 s no
  18 — pulso parado em 50%, pulso estreitando até ~4% ("corda") e pulso parado em ~10% (força
  30%); depois 220 Hz no 18 por uns 3 s
  (o `D` renovado) e, sem renovar, **BAIXO de novo em até 2 s** — é o desligamento automático do
  tom contínuo; no fim, BAIXO.

O script fecha a porta ao terminar. Só um programa usa a porta por vez: feche monitor serial,
Arduino IDE ou o próprio script antes do passo 7.

## 6. Conferir à mão (opcional)

Num monitor serial a 115200 (`arduino-cli monitor -p COM5 -c baudrate=115200`), as linhas do
protocolo funcionam digitadas: `R`, `N 0 0 440.00`, `F 0 2000`, `X`, `?`. Envelope: `E 0 4 900 0 6`
e depois `R`, `N 0 0 220.00`, `F 0 2000`; força: `N 0 0 220.00 300`.

## 7. Pelo site

1. Chrome ou Edge, em https://joaohauch.github.io/flyback-midi/
2. Painel de saída: **Flybacks 2**, **Placa** (a da bancada), pinos, **USB**, 115200, **Conectar**.
   Ao lado do botão aparece `USB · 115200 · nov/2026` — a versão vem da resposta do ESP; sem ela,
   o ESP não respondeu (firmware antigo, ou compilado sem `CDCOnBoot=cdc`).
3. "testar" em cada canal: um lá de 0,6 s.
4. Abrir uma música e tocar. Com 2 flybacks a serial manda só os canais 1 e 2. Com o painel
   "Linhas enviadas" aberto, cada canal recebe um `E` antes do `R`, e cada `N` traz a força no
   fim. Trocar o envelope do canal no mixer (nenhum, corda, percussivo) e tocar de novo: o arco
   tem de mudar como o som do computador muda.
5. Desconectar no player (só uma página usa a porta por vez) e abrir o **gerador de tom**
   (https://joaohauch.github.io/flyback-midi/tom.html; Ctrl+F5 se acabou de sair versão nova). Em
   "Saída", **ESP32 pela serial**, **Placa ESP32** (a mesma do player) → **Conectar ESP32**.
6. Pelo ESP o gerador tem um canal só, o canal 1 do ESP, no **Pino do ESP** escolhido junto da
   frequência (GPIO 4). ▶: tom contínuo no pino, na frequência do slider; o osciloscópio à direita
   desenha o pulso. O volume vira a fração aberta ("aberto 50%" no volume máximo; menos volume,
   pulso mais estreito). Trocar o pino move o tom e apaga o anterior. Fechar a aba com o tom
   tocando: o ESP apaga em 2 s.

## 7b. Pelo Bluetooth

1. Desconectar a USB no site (o ESP pode continuar no cabo, só para a alimentação, ou numa fonte).
2. No seletor ao lado do Conectar, **Bluetooth** → **Conectar** → escolher **Flyback ESP32** na
   lista do navegador. Ao lado aparece `Bluetooth · Flyback ESP32 · nov/2026`.
3. "testar" em cada canal e uma música, como pela USB. As notas saem com 300 ms de antecedência
   (contra 100 ms pela USB), o que não atrasa nada entre os arcos.
4. No celular Android: Chrome, o mesmo endereço, a mesma sequência. Na primeira vez o Android pede
   a permissão de dispositivos próximos (ou de localização, nos mais antigos). iPhone não tem Web
   Bluetooth no Safari.
5. Desligar o Bluetooth do celular (ou sair do alcance) tocando: o ESP silencia na hora e volta a
   anunciar; "Conectar" de novo retoma.
6. O gerador de tom usa a mesma escolha (USB ou Bluetooth) do player.

## 8. Com os flybacks

Só depois de 5 e 7 funcionarem. ESP rodando e conectado → ligar a potência → "testar" →
música → parar → desligar a potência → só então tirar o USB.

Com a potência ligada, o gerador de tom pelo ESP é o jeito de achar o vale de cada flyback e
medir: frequência fixa num canal por vez, varredura, e o volume (a fração aberta) para ver quanto
o arco perde abaixo de 50%. Anote em Resultados o que ouvir e medir em cada canal — e, para o
envelope, **abaixo de que fração aberta o arco deixa de soar** (no gerador de tom, baixando o
volume até sumir): se for alto, o fim do decaimento some antes da hora, e o firmware precisa de
um mínimo.

## Teste sem computador (botão BOOT)

Com o firmware de 21/out, o botão **BOOT** da placa liga um tom de **440 Hz** em onda quadrada (50%,
o máximo do arco) no **GPIO 4**; apertar de novo desliga, e ele desliga sozinho em **2 min**. Serve
para medir o circuito (tensões, correntes, o vale de cada flyback) longe da página e da interferência
no cabo USB — o ESP pode ficar só na fonte. Um flyback por vez: troque o fio de NOTA de placa no
GPIO 4. Pino, frequência e tempo são `TESTE_PINO`, `TESTE_HZ` e `TESTE_MAX_MS`, no topo do sketch.

Com a serial aberta, o ESP avisa `teste: 440 Hz no GPIO 4...` e `teste: desligado`. Se a página
mandar algo durante o teste, ela assume: o tom para quando ela mandar silêncio ou tomar o canal.

## Se a serial cair com o arco ligado

Em 16/out a porta caiu poucos segundos depois de o gerador de tom começar, com o arco aberto sem parar;
tocando música, não. Para saber se o ESP **reiniciou** ou se só o **USB** caiu:

1. Depois da queda, abra `python firmware/monitor_serial.py COM5` e digite `?`. A resposta traz
   `ligado há N s` e `último reinício: ...`. **Não use o monitor do Arduino nem o site para isso:**
   eles puxam DTR/RTS ao abrir a porta, e nas placas com reset automático (o S3 com CH343, o ESP32
   com CP210x) o ESP reinicia nessa hora — o tempo zera e o motivo vira `energia ligada`, seja qual
   for a causa da queda. O `monitor_serial.py` abre sem mexer nessas linhas.
   - `ligado há` grande (não zerou): o ESP nem reiniciou — caiu só a ligação USB. É interferência no
     cabo: afaste o cabo USB do flyback, use cabo curto com ferrite, e o notebook na bateria.
   - `QUEDA DE TENSÃO (brownout)`: a alimentação do ESP afundou com o arco. Fonte do ESP separada da
     do flyback, capacitor junto do ESP, terra em estrela.
   - `TRAVAMENTO (...)`: erro no firmware — anote em Resultados o que estava tocando.
   - `energia ligada` ou `pino de reset`: o ESP desligou de verdade (alimentação ou reset por ruído).
2. Repita com a **potência do flyback desligada** (só o ESP, osciloscópio no pino): se a porta não cai
   assim, o problema é do circuito de potência, não do site nem do firmware.

Uma causa era do site e já saiu (21/out): o gerador de tom mandava o mapa de pinos inteiro, e com a
placa no padrão ESP32-S3 os canais 3 e 4 iam para os GPIO 6 e 7, que num ESP32 comum são da flash —
o ESP travava. Depois disso a porta ainda cai às vezes; a conclusão da bancada é interferência do
flyback no cabo USB (o ambiente de teste não tem isolamento). Para medir sem depender da serial,
use o teste pelo botão BOOT.

## Resultados

Preencher a cada sessão de bancada (data, o que funcionou, o que não, o que mudou no código).

### 25/nov/2026 — ESP32-S3 N16R8, Bluetooth e envelope

Sem a placa de potência: o ESP sozinho, conferido pela serial e medindo o próprio pino.

- **Placa:** ESP32-S3 (QFN56) rev v0.2, 16 MB de flash, 8 MB de PSRAM, na USB nativa (COM4) e
  depois na do CH343 (COM5). Pacote `esp32:esp32` 3.3.12 pelo `arduino-cli`.
- **O firmware que estava gravado não respondia pela USB nativa:** tinha sido compilado sem
  `CDCOnBoot=cdc`, com a serial na UART0. Com a opção, responde pelas duas entradas.
- **Envelope (nov/2026) confere na placa.** Uma versão de medição do firmware lia o GPIO 4 durante
  18 ms (4 períodos de 220 Hz) e contava a fração em ALTO; fração medida contra a conta do
  protocolo (d = asin(L)/π):

  | nota de 2 s | 0,05 s | 0,3 s | 0,6 s | 1 s | 1,5 s | 1,9 s | depois do F |
  |---|---|---|---|---|---|---|---|
  | reto | 495‰ (500) | 505 (500) | 505 (500) | 505 (500) | 505 (500) | 498 (500) | 0 |
  | corda | 391 (388) | 258 (252) | 163 (170) | 108 (106) | 61 (60) | 37 (38) | 0 |
  | força 30% | 87 (97) | 98 (97) | 98 (97) | 87 (97) | 97 (97) | 87 (97) | 0 |
  | percussivo | 253 (231) | 56 (55) | 34 (34) | 32 (32) | 32 (32) | 32 (32) | 0 |

  As diferenças de ~10‰ são da janela de medida, que pega fração de período. Falta medir na
  potência abaixo de que fração o arco deixa de soar.
- **Bluetooth:** o firmware anuncia `Flyback ESP32` e responde pela USB que está anunciando. O
  notebook da bancada não tem adaptador Bluetooth: a conexão sem fio foi testada só com o ESP
  simulado em `tools/testar_site.py` (pedaços de 20 bytes até o MTU, uma escrita por vez, queda).
  **Falta conectar de verdade** pelo celular ou por um PC com Bluetooth (passo 7b).
- **Achado: abrir a porta do CH343 mexia no ESP.** O circuito de reset automático liga DTR e RTS
  ao GPIO 0 e ao EN, e o `testar_serial.py` abria a porta do jeito padrão do pyserial, com os dois
  ligados. Numa vez o pulso no GPIO 0 foi lido como aperto do BOOT, e o tom de teste de 440 Hz no
  máximo ligou sozinho (com a potência ligada, o arco abriria por até 2 min se nada mandasse `X`);
  noutra, o S3 reiniciou em modo de gravação (`boot:0x0 DOWNLOAD... waiting for download`) e não
  respondia mais. Corrigido nos três lados: o BOOT só vale parado em BAIXO por 80 ms; o
  `testar_serial.py` e a página (só fora da USB nativa) abrem, soltam o GPIO 0 e dão um pulso no EN,
  e esperam o `pronto` (0,6 s no S3). Depois disso, duas rodadas seguidas com boot normal.
- **Depois, pelo site publicado (ainda sem a correção), os flybacks pararam:** o site conectava, o
  LED do CH343 piscava a cada nota, e nada no arco. O ESP estava parado no modo de gravação — o
  esptool conectou no ROM sem reiniciar — depois de o Chrome abrir e fechar a porta do CH343. Um
  pulso limpo no EN (GPIO 0 solto) o devolveu ao firmware. A página nova avisa quando o ESP não
  responde ao `?` em 2,5 s. Enquanto ela não estiver publicada: use a entrada USB nativa da placa,
  ou o site servido por `python tools/servir.py`.
- **Motivo do reinício no S3:** gravar ou abrir a USB nativa aparecia como `outro`; agora é
  `reinício pela USB nativa`. Pelo EN (o pulso do CH343) aparece `energia ligada`, que é como o
  chip registra.
