# Protocolo serial para o ESP32

Com o ESP32 conectado, o `index.html` envia — pela USB (Web Serial) ou pelo Bluetooth (Web
Bluetooth) — os segmentos monofônicos de cada canal, os mesmos `ch[i].segs` que alimentam a
síntese. São de 1 a 6 canais, um por flyback. O firmware só precisa enfileirar e executar no
instante certo. O firmware está em `firmware/flyback-esp32/` (ver **Firmware**, no fim).

No modo **Estéreo · P2** nada vai pela serial: os dois flybacks são acionados pelo áudio do
computador.

## Transporte

As mesmas linhas por dois caminhos, escolhidos no seletor ao lado do Conectar (no player e no
gerador de tom; a escolha fica em `flyback:esp`, com a placa e os pinos):

- **USB** — Web Serial, 8N1, sem controle de fluxo. Velocidade escolhida na página: 115200
  (padrão), 230400, 460800 ou 921600. Chrome e Edge no computador.
- **Bluetooth** — Web Bluetooth (BLE), serviço UART da Nordic (NUS), que o firmware anuncia com o
  nome `Flyback ESP32`. A página procura pelo serviço ou por nome começando com `Flyback`.
  Chrome e Edge no computador (com adaptador Bluetooth) e **Chrome no Android**; o Safari do
  iPhone não tem Web Bluetooth. Sem fio, também some o caminho da interferência do flyback pelo
  cabo USB.

| Característica | UUID | Uso |
|---|---|---|
| serviço | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | |
| RX | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | a página escreve as linhas (com ou sem resposta) |
| TX | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | o ESP notifica o que responde (o `?`, os avisos) |

- Texto ASCII, uma mensagem por linha, terminada em `\n`. Uma linha pode chegar em vários
  pacotes e um pacote pode trazer várias linhas: o firmware monta a linha de cada caminho
  separada.
- Pelo Bluetooth cada escrita leva no máximo MTU − 3 bytes: 20 até o MTU ser negociado (o Chrome
  do Android não negocia), até 244 depois (o firmware aceita 247). A página pergunta `?` ao
  conectar, e a resposta pelo Bluetooth traz `bluetooth conectado, mtu N`: dali em diante as
  linhas vão juntas em pedaços de N − 3. Uma escrita por vez — duas ao mesmo tempo dão erro no
  Web Bluetooth.
- O firmware ouve a USB e o Bluetooth ao mesmo tempo e responde pelos dois. Se cai o Bluetooth
  de quem estava tocando, o firmware silencia tudo na hora e volta a anunciar.
- Safari e Firefox não têm nem Web Serial nem Web Bluetooth, e a página avisa; o caminho sem
  suporte no navegador aparece desabilitado no seletor.

## Mensagens

| Linha | Significado |
|---|---|
| `P c g` | O canal `c` passa a acionar o GPIO `g`. `g = -1` libera o canal. |
| `R` | Zera o relógio: o instante em que a linha chega é t = 0. Esvazia as filas. |
| `E c atk tau sus rel` | Receita do envelope do canal `c`, mandada antes de cada `R` de tocar: ataque de `atk` ms até o pico, decaimento com constante `tau` ms (0 = sem decaimento) até o patamar `sus` ‰ do pico, e soltura de `rel` ms depois do `F`. Vale da próxima nota em diante. |
| `N c t f a` | No instante `t` ms, o canal `c` passa a tocar `f` Hz com força `a` ‰ (de 0 a 1000). Sem `a`, vale 1000. |
| `F c t` | No instante `t` ms, o canal `c` começa a soltura e depois silencia. |
| `X` | Silencia todos os canais agora e esvazia as filas. |
| `?` | Pergunta o estado. A resposta é uma linha: versão, lógica, canais, pinos, envelopes, eventos perdidos, tempo ligado, motivo do último reinício, o Bluetooth (`anunciando "Flyback ESP32"` ou `conectado, mtu N`) e por onde veio a pergunta. A página manda ao conectar e mostra a versão (o começo, até ` · lógica`) ao lado do estado. |
| `D c d f` | Tom contínuo, do gerador de tom: o canal `c` toca `f` Hz com o arco aberto `d` ‰ de cada período (500 = onda quadrada, o máximo; 0 termina). Dura 2 s, e cada `D` novo renova: se a página parar, o arco apaga sozinho. Esvazia a fila do canal; `N`, `F`, `R` ou `X` cancelam. |

- `c` é o índice do canal, de `0` a `5` — o "Canal 1" da página é o `0`.
- `t` é inteiro, em milissegundos desde o último `R`.
- `f` tem duas casas decimais, por exemplo `440.00`. A oitava escolhida na página
  já vem aplicada.
- Duas notas seguidas no mesmo canal chegam como dois `N` sem `F` entre eles.
  O `F` só aparece quando há silêncio de verdade.
- `a` é inteiro e sai da mesma conta que o áudio da página usa (`forca` no `index.html`): com
  "Dinâmica" ligada no canal, 250 + 750·(v/127)^1,4, onde v é a velocity da nota (96 quando
  falta); desligada, 1000. O ganho do mixer **não** entra: é o volume do computador, e o arco vai
  até o máximo dele.

### Envelope

Só com **"envelope no arco"** ligado, ao lado de "ouvir no computador" (desligado por padrão,
guardado em `flyback:esp`). Desligado, todo canal recebe `E c 4 0 1000 6` e todo `N` leva força
1000: a nota sai inteira no máximo, como no firmware antigo. Ligado, a página manda um `E` por
canal antes de cada `R` de tocar, traduzido de `ENVELOPES` no
`index.html`: `tau = env.tau·1000`, `sus = env.sus·1000`, com `atk` = 4 (o `ATAQUE`) e `rel` = 6 (a
rampa final do áudio). Envelope novo na página passa a valer no arco sem mexer no firmware.

| Envelope no mixer | Linha |
|---|---|
| nenhum | `E c 4 0 1000 6` |
| percussivo | `E c 4 120 100 6` |
| médio | `E c 4 450 350 6` |
| sustentado | `E c 4 1200 700 6` |
| corda | `E c 4 900 0 6` |

O firmware desenha a curva a cada 1 ms — nível L = a/1000 × envelope — e a aplica pela **fração
aberta** do período da nota, d = asin(L)/π, a mesma conta do volume do gerador de tom: o volume do
arco na V3.6 segue sen(π·d), máximo em d = 50% (a onda quadrada). Uma nota de 2 s em "corda" sai
com 50% no começo, 19% em 0,5 s, 11% em 1 s e 3,5% no fim; força 300 dá 10% parado.

**Compatibilidade:** firmware antigo ignora o `E` e lê só os três primeiros campos do `N` — toca
como sempre, a nota inteira em 50%. Firmware novo sem `E` (página antiga) fica com o envelope
reto, e sem `a`, com força 1000: também como sempre.

### Pinos

A página manda o mapa inteiro, os seis `P`, ao conectar, sempre que muda o pino de um
canal, a placa ou o número de flybacks, e antes de cada `R` de tocar ou testar — muitas
placas ESP32 reiniciam quando a porta serial é aberta, e o que chega durante o boot se perde. Canal acima do número de flybacks escolhido vai com
`-1`. O firmware deve silenciar o canal antes de trocar o pino dele, e ignorar `N` e `F` de
canal sem pino.

A página só oferece pinos de saída livres em módulo comum — sem os de boot (strapping), os
da memória flash e PSRAM, os da USB nativa e os da UART0:

| Placa | Pinos oferecidos | Padrão para os canais 1 a 6 |
|---|---|---|
| ESP32 | 4, 13, 14, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33 | 18, 19, 21, 22, 23, 25 |
| ESP32-S3 | 1, 2, 4–18, 21, 38–42, 47, 48 | 4, 5, 6, 7, 15, 16 |

O MCPWM chega a qualquer GPIO pela matriz, então qualquer pino da lista serve para qualquer
canal. Em módulo WROVER do ESP32 clássico, 16 e 17 são da PSRAM; em algumas placas S3, 38 ou
48 têm o LED RGB.

### Teste de canal

O botão "testar" de cada canal, com a página parada, envia:

```
R
N c 0 440.00
F c 600
```

Um lá de 0,6 s naquele canal, para achar qual flyback é qual ao montar a bancada. Antes do `R`
vai `E c 4 0 1000 6`: o teste é reto, no máximo, seja qual for o envelope da última música.

## Tempo

- A página manda cada evento cerca de 100 ms antes do instante `t` — 300 ms pelo Bluetooth,
  que demora mais a entregar. O firmware deve manter uma fila por canal, ordenada por `t`.
  O relógio do ESP começa quando o `R` chega, então a demora constante do caminho atrasa tudo
  por igual e não desalinha as notas entre si.
- Evento com `t` já passado executa na hora.
- Tocar, pular para outro ponto, silenciar um canal ou retomar depois de pausar gera `R` e
  recomeça a contagem. Pausar, parar, ou trocar para o modo estéreo gera `X`.
- Com a aba em segundo plano o navegador atrasa os temporizadores e os eventos
  podem chegar tarde. Deixe a página visível enquanto toca.

## Ver o que seria enviado

O painel "Linhas enviadas", na saída ESP32, mostra as últimas linhas — **também sem ESP
conectado**: com ele aberto, tocar a música gera o mesmo fluxo que iria para a porta. É o
jeito de conferir o protocolo enquanto o firmware não existe.

## Exemplo

Conectando com seis flybacks num ESP32-S3 e tocando o início do Korobeiniki do acervo, com o
preset "um instrumento por flyback":

```
X
P 0 4
P 1 5
P 2 6
P 3 7
P 4 15
P 5 16
E 0 4 900 0 6
E 1 4 900 0 6
E 2 4 900 0 6
E 3 4 900 0 6
E 4 4 900 0 6
E 5 4 900 0 6
R
N 0 60 659.26 825
N 1 60 82.41 825
N 2 60 207.65 825
N 1 260 164.81 825
```

## Recepção no firmware, em esboço

```c
// uma linha por vez, já sem o '\n'
switch (linha[0]) {
  case 'P': sscanf(linha + 2, "%d %d", &c, &g);         silencia(c); fixa_pino(c, g); break;
  case 'R': t0 = millis(); limpa_filas(); break;
  case 'X': silencia_todos(); limpa_filas(); break;
  case 'E': sscanf(linha + 2, "%d %ld %ld %ld %ld", &c, &atk, &tau, &sus, &rel); receita(c, ...); break;
  case 'N': a = 1000; sscanf(linha + 2, "%d %lu %f %d", &c, &t, &f, &a); enfileira(c, t0 + t, f, a); break;
  case 'F': sscanf(linha + 2, "%d %lu", &c, &t);        enfileira(c, t0 + t, 0, 0); break;
}
```

A seção 3.16 de `hardware-decisoes.md` explica por que a geração da nota no ESP
deve habilitar o gerador do MCPWM, ou contar pulsos, em vez de alternar o GPIO.

## Firmware

`firmware/flyback-esp32/flyback-esp32.ino`, para a Arduino IDE ou o `arduino-cli`, placa "ESP32
Dev Module" (o ESP32 comum, o "S1" de `hardware-decisoes.md`). Só usa o que vem com o pacote
`esp32` da Espressif.

- **Nota pelo LEDC**, um timer por canal: cada canal tem a sua frequência. O ESP32 comum tem 8
  timers e cobre os 6 canais; o S3 tem 4, e lá só os canais 1 a 4 tocam. Onda quadrada de 50%,
  resolução de 13 bits — de 9,5 Hz a 9,7 kHz; com 10 bits nada abaixo de 76 Hz sairia.
- **Envelope e força** (nov/2026): cada canal guarda a receita do `E`, e a cada 1 ms o firmware
  recalcula o nível da nota soando e escreve o duty do LEDC só quando ele muda. Nível 1 é a onda
  quadrada de antes (50%); abaixo disso, pulso mais estreito, na polaridade do circuito. O `D`
  e o botão BOOT não passam pelo envelope. A versão gravada aparece no boot e no `?`
  (`nov/2026 · envelope`), junto com o envelope de cada canal.
- **Polaridade** é a constante `LOGICA_INVERTIDA`, no topo do sketch. Na placa **V3.6** é
  `false`: a nota entra pelo 6N136 e passa pelo Q1 até o RESET do 555, as duas inversões se
  anulam, e GPIO em ALTO libera o arco. Na V3.5 antiga (um NPN direto no pino 4) é `true`. Fica no
  firmware, e não na página, porque o silêncio tem de estar certo também sem a página: no boot,
  com o navegador fechado, com a aba travada. Na nota em 50%, a polaridade não muda nada; abaixo
  disso, o firmware inverte o duty na lógica invertida.
- **Tom contínuo** (`D`): o gerador de tom (`tom.html`), no modo "ESP32 pela serial", põe só o
  canal 1 no pino escolhido (`P 0 g`, e `P c -1` nos outros) e manda um `D 0` a cada 500 ms; o
  volume da página vira a fração aberta d, e o volume do arco segue sen(π·d), máximo em 50%.
- **Pinos proibidos**: `P` para pino da memória flash (GPIO 6 a 11 no ESP32 comum; 26 a 37 no S3),
  da USB nativa (19 e 20 no S3), da serial (1 e 3; 43 e 44 no S3), só de entrada (34 a 39) ou
  inexistente é ignorado, com aviso na serial. Ligar o LEDC num pino da flash trava o ESP: foi o
  que derrubou a serial em 16/out, quando o gerador de tom mandava o mapa do S3 (com 6 e 7) a um
  ESP32 comum.
- **Teste sem computador**: o botão BOOT (GPIO 0) liga e desliga 440 Hz em onda quadrada no GPIO
  4, por até 2 min (`TESTE_PINO`, `TESTE_HZ`, `TESTE_MAX_MS` no topo do sketch). Se a página
  manda algo durante o teste, o mapa passa a ser o dela.
- **Pinos padrão** iguais aos da página (18, 19, 21, 22, 23, 25 no ESP32), parados no silêncio
  antes até de a serial abrir, e o de teste (4) também: se o mapa se perder no boot, o firmware já
  está no lugar.
- **Nota presa**: passou de 20 s sem nenhum evento novo no canal, silencia — é o caso de o
  navegador travar no meio de uma nota e o `F` nunca chegar.
- `?` pelo monitor serial responde a lógica, os pinos, os eventos perdidos, há quanto tempo o ESP
  está ligado e o motivo do último reinício (queda de tensão, travamento, energia ligada...) — o
  boot também diz o motivo. É o que separa, quando a serial cai com o arco ligado, a queda só do
  USB (o tempo ligado não zera) de um reinício do ESP.

**Na V3.6 o lado seguro é o natural:** ESP desligado, em boot ou com o cabo solto deixa o LED do
6N136 apagado, e o arco cortado. **Na V3.5 antiga é o contrário:** a falta de sinal libera o arco: enquanto o ESP
reinicia (uns 300 ms), trava ou está desligado com a placa de potência ligada, o 555 oscila e o
flyback fica ligado direto. Ligue a potência só com o ESP já rodando, desligue antes de tirar o
USB, e prefira um resistor de pull-up (10 kΩ ao 3,3 V) no pino, que mantém o arco cortado durante
o boot. Na próxima revisão da placa, vale inverter: sem sinal, arco desligado.

Com o 555 reiniciado a cada liberação do pino 4, cada rajada começa do mesmo jeito; a distorção da
seção 3.16, de cortar uma portadora gerada pelo próprio ESP, não se aplica aqui.
