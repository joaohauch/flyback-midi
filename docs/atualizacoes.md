# Atualizações

O que mudou no site, no firmware e no acervo desde o primeiro roteiro de bancada (11/out/2026), do
mais recente para o mais antigo, com o porquê de cada mudança. É para a sessão do computador da
bancada ler depois do `git pull`. O passo a passo de gravar e testar continua em
`docs/bancada-esp32.md`.

**Antes de testar:** `git pull` e grave o firmware de novo (passos 2 a 4 do roteiro). O firmware
de nov/2026 é o primeiro com envelope e força nas notas; o boot e o `?` dizem `nov/2026 · envelope`.
Desde 25/nov, `nov/2026 · envelope · bluetooth`.

## 25/nov — Bluetooth, e o ESP32-S3 na bancada

Feito no computador da bancada, com o ESP32-S3 no USB. Resultados em `docs/bancada-esp32.md`.

- **O que mudou:** a conexão com o ESP passa a ser **USB ou Bluetooth**, escolhida num seletor ao
  lado do Conectar, no player e no gerador de tom (a escolha fica em `flyback:esp`, com a placa).
  O Bluetooth é BLE com o serviço UART da Nordic: Chrome e Edge no computador e Chrome no Android
  (o celular não tem Web Serial, então lá o padrão é o Bluetooth). O protocolo é o mesmo, linha a
  linha; detalhes em `docs/protocolo-serial.md`, "Transporte". Sem o cabo, também some a
  interferência do flyback pela USB, que derrubava a serial.
- **Firmware:** ouve a USB, a UART0 (a segunda entrada USB das DevKit S3, pelo CH343) e o
  Bluetooth ao mesmo tempo, e responde pelos três. Se cai o Bluetooth de quem estava tocando,
  silencia na hora. O `?` diz o estado do Bluetooth e o MTU, que a página usa para o tamanho dos
  pacotes (20 bytes até negociar).
- **A página lê o que o ESP responde:** pergunta `?` ao conectar e mostra a versão do firmware ao
  lado do estado (`USB · 115200 · nov/2026`); as respostas aparecem em "Linhas enviadas", com ←.
- **Botão BOOT só vale apertado por 80 ms**, e a página e o `testar_serial.py` reiniciam o ESP
  limpo ao abrir a porta do CH343: abrir com DTR e RTS ligados chegou a ligar o tom de teste
  sozinho e a deixar o S3 em modo de gravação.
- **Envelope medido na placa** (no pino, sem potência): bate com a conta, ver a tabela em
  Resultados.
- **Respiro entre notas para todas as notas próximas**, escolhido ao lado de "envelope no arco"
  (0 a 60 ms, 25 por padrão). No tema do Rocky as notas repetidas emendavam no arco: o MIDI acaba
  cada nota 1 ms antes da seguinte, e o respiro só valia com pausa zero.
- **"Envelope no arco" virou opção**, ao lado de "ouvir no computador", desligada por padrão:
  desligada, a nota sai inteira no máximo, como antes do envelope.
- **A serial voltou a cair com o arco tocando**, agora pela USB nativa: o mais provável é a
  interferência de sempre (o notebook perto do flyback). O Bluetooth tira o cabo do caminho.
- **S3:** compilar com `CDCOnBoot=cdc` (passo 2 do roteiro), senão nada sai pela USB nativa.
- **A medir ainda:** o Bluetooth de verdade (o notebook da bancada não tem adaptador) e, com a
  potência, abaixo de que fração o arco deixa de soar.

## nov/2026 — envelope e força no arco

- **O que mudou:** até aqui o arco tocava toda nota no máximo (onda quadrada de 50%) do começo ao
  fim; envelope e "Dinâmica" do mixer só valiam no som do computador. Agora a página manda a
  receita do envelope de cada canal (`E c atk tau sus rel`, antes de cada `R`) e a força de cada
  nota (`N c t f a`), e o firmware desenha a curva a cada 1 ms pela fração aberta do período,
  d = asin(nível)/π — a mesma conta do volume do gerador de tom. Detalhes e tabela em
  `docs/protocolo-serial.md`, seção "Envelope".
- **Compatível nos dois sentidos:** firmware antigo ignora o `E` e a força e toca como antes;
  firmware novo com página antiga também.
- **Compilado** com PlatformIO (pacote espressif32, Arduino) para ESP32 e ESP32-S3, sem erro nem
  aviso; ainda não rodou numa placa.
- **Testar:** `python firmware/testar_serial.py COM5` agora toca três lás de 2 s no canal 1:
  reto (pulso parado em 50%), "corda" (pulso estreitando até ~4% no fim) e força 30% (~10%
  parado). Pelo site, a mesma música com envelope "nenhum" e "corda" no mixer.
- **A medir na bancada:** abaixo de que fração aberta o arco deixa de soar. Se a nota sumir antes
  da hora no fim do decaimento, o conserto é um mínimo de fração no firmware enquanto a nota
  soa — anotar o valor em Resultados.
- **Site:** favoritas no acervo (estrela em cada música, botão "favoritas"), guardadas no
  navegador.

## 21/out — teste sem computador

- **Firmware: botão BOOT liga um tom de teste.** Apertar o BOOT (GPIO 0, no ESP32 comum e no S3)
  liga 440 Hz em onda quadrada (50%, o máximo do arco) no **GPIO 4**; apertar de novo desliga, e ele
  desliga sozinho em 2 min. Para medir o circuito sem a página e sem o cabo USB perto do flyback.
  Um flyback por vez: troque o fio de NOTA de placa no GPIO 4. Ajustes no topo do sketch:
  `TESTE_PINO`, `TESTE_HZ`, `TESTE_MAX_MS`. Se o canal 1 estava em outro pino, volta para ele no
  fim; se a página mandou algo durante o teste, o mapa passa a ser o dela.
- **Firmware: GPIO 4 em silêncio desde o boot.** No ESP32 comum ele não é pino padrão de canal
  nenhum e ficava solto até a página mandar o mapa.

## 16 a 21/out — a serial caía

O sintoma: no gerador de tom, poucos segundos depois de o tom começar, a porta caía; tocando música,
não. Eram duas coisas.

- **Site: o gerador de tom travava o ESP (corrigido).** Ele mandava o mapa de pinos inteiro, e com a
  placa no padrão ESP32-S3 os canais 3 e 4 iam para os GPIO 6 e 7 — num ESP32 comum, pinos da
  memória flash. Ligar o PWM neles trava o chip. Agora o gerador configura **só o canal 1**, no
  pino escolhido, e libera os outros (`P c -1`). Na música isso não aparecia porque, com 2
  flybacks, o player só manda os canais 1 e 2.
- **Firmware: pino perigoso é recusado.** `P` para pino da flash (GPIO 6 a 11 no ESP32; 26 a 37 no
  S3), da USB nativa (19 e 20 no S3), da serial (1 e 3; 43 e 44 no S3), só de entrada (34 a 39) ou
  inexistente é ignorado, com aviso. Nenhum mapa errado trava o ESP mais.
- **Firmware: motivo do último reinício.** O `?` e a mensagem de boot dizem há quanto tempo o ESP
  está ligado e por que reiniciou da última vez (queda de tensão, travamento, energia ligada...).
  Se a porta cai e o tempo ligado não zerou, foi só o USB.
- **O que sobrou é interferência.** Mesmo com o site corrigido a porta ainda cai às vezes, com o arco
  aberto sem parar. A bancada não tem o isolamento que deveria — aceito por enquanto. Ajuda: cabo
  USB curto e com ferrite, longe do flyback; notebook na bateria; fonte do ESP separada da do
  flyback. Para medir sem depender da serial: o botão BOOT.
- **Site: placa e pino no gerador de tom.** A caixa "Saída" escolhe a placa (ESP32 ou ESP32-S3), a
  mesma do painel do player — o que se escolhe num vale no outro; o pino que recebe o tom se
  escolhe em "Pino do ESP", junto da frequência. Antes, sem nada salvo, o player usava o S3 (canal 1
  no GPIO 4) e o gerador o ESP32 comum (GPIO 18): a música saía no 4 e o tom no 18.

## 14 a 16/out — o que o arco toca

Achado ouvindo várias músicas pelos flybacks.

- **Nota repetida ganhou respiro.** Duas notas iguais coladas iam pela serial só com o `N` da
  segunda, na mesma frequência, e o arco não desligava: a cavalgada de semicolcheias virava uma nota
  só. Agora a primeira desliga 25 ms antes da segunda (no máximo 40% dela) — pela serial, um `F`
  entre as duas.
- **Nota curta sem estalo.** Trecho curto no arco é estalo. Saem: a nota antiga que reaparece no
  respiro entre duas da melodia (o MIDI do MuseScore termina cada nota um pouco antes da seguinte),
  o resto de acorde dedilhado (as cordas entram 5 a 20 ms uma depois da outra; o acorde agora se
  escolhe com 35 ms de folga) e a nota nova de menos de 35 ms no MIDI. A curta seguida de silêncio se
  estende até 60 ms. Ataque novo de verdade nunca sai — uma versão anterior apagava a cavalgada da
  guitarra abafada e foi corrigida.
- **Percussão fora do canal 10.** Programas General MIDI 113 e 115 a 118 (agogô, woodblock, taiko,
  tom melódico, bateria eletrônica) tocam como batida; 119 a 127 (prato invertido, efeitos) não
  tocam. Eram 146 faixas tocadas como nota ("batidas estranhas").
- **Montagem fixa: arco vazio para quem traz detalhe novo.** Os arcos que sobram vão para a faixa com
  mais ataques que nenhum arco toca, e não para a que soa mais tempo. Nos clássicos a cobertura de
  detalhe foi de 75% para 85% (mediana).

## Transcrições

- **Orientação 2 congelava blocos.** O MuScriptor transcreve em blocos de 5 s; com orientação 2 o
  `large` às vezes parava no meio de um bloco, e tudo segurava a mesma nota por 2 a 9 s com a bateria
  sumindo (Eye of the Tiger em 1:27). 24 de 65 transcrições feitas assim tinham isso. O lote voltou à
  orientação 1, e `tools/emendar_blocos.py` trocou só os blocos estragados pelos de uma transcrição
  de orientação 1, mantendo a voz: 19 músicas emendadas, 2 refeitas inteiras (Total Eclipse of the
  Heart, Seven Nation Army).
- **Ainda congelam** (a de orientação 1 congela no mesmo lugar): Rock N Roll Train, Live And Let Die,
  November Rain, Run to the Hills, Thriller, Roxanne; e parte dos trechos de War Pigs, Paradise City
  e il vento d'oro.
- **Limites do modelo, sem conserto aqui:** a introdução de Eye of the Tiger não tem os acordes do
  riff em configuração nenhuma (a versão de fã em `bandas/Survivor` tem); em Never Gonna Give You Up o
  riff de sintetizador foi escrito na faixa de baixo.
- **Acervo:** 45 músicas novas em `transcritas` (95 ao todo); os clássicos viraram 65 obras
  orquestrais conhecidas com 6 partes ou mais (44 do PDMX, 21 do Mutopia), no lugar de 590 peças de
  piano e solo.

## Pendente e a decidir

- **Mudanças no site que o dono do projeto quer fazer** — anotar aqui quando vierem.
- **Reconectar a serial sozinho** quando ela cai: o Web Serial deixa reabrir uma porta já autorizada
  sem pedir de novo. Não feito.
- **Nota grave curta**: em Dude Looks Like a Lady o baixo tem notas de 47 ms a 49 Hz — dois ciclos
  no arco. Se incomodar, mínimo em ciclos em vez de milissegundos.
- **Decisões:** testar Eye of the Tiger no Mirelo (gasta crédito); trazer as três versões de fã de
  Never Gonna Give You Up do acervo Lakh.
- **Placa V5:** `docs/envelope-v5.md` (protocolo v2, envelope pelo pino ENV), quando a placa existir.
