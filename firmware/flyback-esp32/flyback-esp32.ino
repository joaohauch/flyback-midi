/*
  flyback-esp32 — o firmware dos flybacks para o site flyback-midi.

  Recebe o protocolo de docs/protocolo-serial.md (P, E, R, N, F, X, D e ?) pela USB ou pelo
  Bluetooth (BLE), os dois ao mesmo tempo, e toca cada canal como onda quadrada na frequência da
  nota, num GPIO que interrompe o oscilador do flyback.
  O volume da nota — força (velocity) e envelope (ataque, decaimento, sustentação, soltura) — sai
  pela fração do período em que o arco fica aberto, recalculada a cada 1 ms (ver ENVELOPE abaixo).
  Sem computador, o botão BOOT liga e desliga um tom de teste de 440 Hz no GPIO 4 (ver TESTE_*).

  Placas: ESP32 comum ("ESP32 Dev Module" no Arduino) e ESP32-S3 (lá só os canais 1 a 4 tocam —
  ver CANAIS abaixo). O comando de compilar de cada uma está em docs/bancada-esp32.md: o S3 precisa
  de "USB CDC On Boot" ligado (CDCOnBoot=cdc), senão a serial não sai pela USB nativa.

  Antes de gravar, confira LOGICA_INVERTIDA para o seu circuito.
*/
#include <Arduino.h>
#include "driver/ledc.h"
#include "esp_system.h"
#include <math.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include "freertos/stream_buffer.h"

#if CONFIG_IDF_TARGET_ESP32S3 && ARDUINO_USB_MODE && !ARDUINO_USB_CDC_ON_BOOT
#warning "ESP32-S3 sem USB CDC On Boot: a serial vai para a UART0, e nada sai pela USB nativa. Compile com CDCOnBoot=cdc."
#endif

// Aparece no boot e no "?": para saber, pelo monitor serial, qual versão está gravada na placa.
const char *VERSAO = "nov/2026 · envelope · bluetooth";

// ------------------------------------------------------------------ ajuste para o seu circuito

// false: GPIO em ALTO LIBERA o arco. É a placa V3.6: a NOTA entra pelo 6N136 e passa pelo Q1 até o
//        RESET do 555, e as duas inversões se anulam. ESP desligado, em boot ou com o cabo solto
//        deixa o LED do 6N136 apagado, e o arco cortado: o lado seguro sozinho.
// true:  GPIO em ALTO CORTA o arco. É a V3.5 antiga, com um NPN direto no pino 4 do 555: sem
//        sinal nenhum, o 555 oscila e o arco fica ligado.
// A polaridade fica aqui, e não na página, porque o silêncio tem de estar certo também quando a
// página não está conectada: no boot, com o navegador fechado, com a aba travada.
const bool LOGICA_INVERTIDA = false;

const uint32_t BAUD = 115200;        // o mesmo escolhido na página (115200 é o padrão dela)

// Bluetooth: o nome que aparece na lista do navegador ao conectar. A página procura pelo serviço
// (o UART da Nordic, abaixo) e por nome começando com "Flyback"; para duas placas na mesma sala,
// dê um nome a cada uma, mantendo o começo.
const char *NOME_BLE = "Flyback ESP32";

// Pinos de cada canal até a página mandar o mapa ("P c g"). São os padrões da página, para o
// firmware já funcionar se as primeiras linhas se perderem: muitas placas reiniciam quando a
// porta serial é aberta, e o que chega durante o boot some.
#if CONFIG_IDF_TARGET_ESP32S3
const int PINOS_PADRAO[6] = {4, 5, 6, 7, 15, 16};
#else
const int PINOS_PADRAO[6] = {18, 19, 21, 22, 23, 25};
#endif

// Nota que passa disso sem nenhum evento novo no canal é cortada: se o navegador travar no
// meio de uma nota, o "F" dela nunca chega, e o arco não pode ficar ligado para sempre.
const uint32_t NOTA_MAXIMA_MS = 20000;

// "D c d f", o tom contínuo do gerador de tom: dura isto e cada "D" novo renova. Se a página parar
// de repetir (aba travada, cabo solto), o arco apaga sozinho.
const uint32_t DIRETO_MS = 2000;

// Teste sem computador: o botão BOOT da placa liga e desliga um tom de TESTE_HZ, em onda quadrada
// (o máximo do arco), no GPIO TESTE_PINO, por até TESTE_MAX_MS. Para medir o circuito longe da página
// — e da interferência do flyback no cabo USB, que derruba a serial. Um flyback por vez: troque o fio
// de NOTA de placa no pino de teste.
const int TESTE_BOTAO = 0;           // BOOT, no ESP32 comum e no S3
const int TESTE_PINO = 4;
const float TESTE_HZ = 440.0;
const uint32_t TESTE_MAX_MS = 120000;

// ------------------------------------------------------------------ USB e Bluetooth
// O mesmo protocolo de linhas chega por três caminhos, e cada um tem a sua linha em montagem:
// - a USB do "Serial" — no S3, a USB nativa (USB-Serial/JTAG); no ESP32 comum, o conversor
//   CP210x/CH340 da placa;
// - no S3 com CDC On Boot, também a UART0 (Serial0), que é a outra entrada USB das DevKit com duas
//   (a do CH343): funciona em qualquer das duas;
// - o Bluetooth (BLE), pelo serviço UART da Nordic (NUS): a página escreve no RX e lê o TX por
//   notificação. É o Web Bluetooth do Chrome e do Edge no computador e do Chrome no Android. O S3
//   só tem BLE; o ESP32 comum também tem o Bluetooth clássico, mas o navegador não fala com ele. Sem
//   fio, também some o caminho da interferência do flyback pelo cabo USB, que derrubava a serial.
// O que o firmware responde (o "?", os avisos) sai pelos três.
#define NUS_SERVICO "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
#define NUS_RX      "6e400002-b5a3-f393-e0a9-e50e24dcca9e"   // a página escreve aqui
#define NUS_TX      "6e400003-b5a3-f393-e0a9-e50e24dcca9e"   // e lê daqui, por notificação

enum Fonte { DA_USB, DA_UART, DO_BLE, FONTES };
static const char *NOME_FONTE[FONTES] = {"USB", "UART", "Bluetooth"};
static int ultimaFonte = -1;                   // quem mandou a última linha

static BLEServer *bleServidor = nullptr;
static BLECharacteristic *bleTx = nullptr;
// O BLE entrega cada escrita numa tarefa dele; o loop lê daqui, sem disputar nada com ela.
static StreamBufferHandle_t bleEntrada = nullptr;
static volatile bool bleConectado = false, bleCaiu = false;
static uint16_t bleMtu = 23;                   // 23 até o navegador negociar: 20 bytes por pacote
static char bleSaida[1024];                    // o texto a notificar, mandado aos pedaços no loop
static size_t bleSaidaN = 0;

class AoConectar : public BLEServerCallbacks {
  void onConnect(BLEServer *s) override { (void)s; bleConectado = true; }
  void onDisconnect(BLEServer *s) override { (void)s; bleConectado = false; bleCaiu = true; }
#if defined(CONFIG_BLUEDROID_ENABLED)
  // pede intervalo de 7,5 a 15 ms: com o padrão do Android (30 a 50 ms) a nota chega mais tarde
  void onConnect(BLEServer *s, esp_ble_gatts_cb_param_t *p) override {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    s->requestConnParams(p->connect.remote_bda, 6, 12, 0, 400);
#else
    s->updateConnParams(p->connect.remote_bda, 6, 12, 0, 400);
#endif
  }
#endif
};
class AoEscrever : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    auto v = c->getValue();                     // String no pacote 3.x, std::string no 2.x
    if (v.length() && bleEntrada) xStreamBufferSend(bleEntrada, v.c_str(), v.length(), 0);
  }
};

// Print que escreve nas três saídas. Na USB nativa do S3, sem a porta aberta no computador, a
// escrita não pode esperar (setTxTimeoutMs(0) no setup): tocando pelo Bluetooth com o cabo só na
// fonte, o loop travaria a cada linha.
class Eco : public Print {
public:
  size_t write(uint8_t b) override { return write(&b, 1); }
  size_t write(const uint8_t *p, size_t n) override {
    Serial.write(p, n);
#if ARDUINO_USB_CDC_ON_BOOT
    Serial0.write(p, n);
#endif
    if (bleConectado) {
      size_t cabe = sizeof(bleSaida) - bleSaidaN, m = n < cabe ? n : cabe;   // cheio: o resto se perde
      memcpy(bleSaida + bleSaidaN, p, m);
      bleSaidaN += m;
    }
    return n;
  }
};
static Eco diz;

static void bleInicia() {
  bleEntrada = xStreamBufferCreate(4096, 1);
  BLEDevice::init(NOME_BLE);
  BLEDevice::setMTU(247);                      // aceita até 244 bytes por pacote, se o navegador pedir
  bleServidor = BLEDevice::createServer();
  bleServidor->setCallbacks(new AoConectar());
  BLEService *srv = bleServidor->createService(NUS_SERVICO);
  bleTx = srv->createCharacteristic(NUS_TX, BLECharacteristic::PROPERTY_NOTIFY);
#if defined(CONFIG_BLUEDROID_ENABLED)
  bleTx->addDescriptor(new BLE2902());         // no NimBLE ele vem sozinho
#endif
  BLECharacteristic *rx = srv->createCharacteristic(NUS_RX, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  rx->setCallbacks(new AoEscrever());
  srv->start();
  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(NUS_SERVICO);
  adv->setScanResponse(true);                  // o nome vai na resposta se não couber com o serviço
  BLEDevice::startAdvertising();
}

// Notificações aos pedaços de MTU − 3 bytes, um a cada 5 ms: em rajada a pilha do BLE descarta.
static void bleEnvia() {
  static uint32_t ultimo = 0;
  if (!bleConectado) { bleSaidaN = 0; return; }
  if (!bleSaidaN || millis() - ultimo < 5) return;
  ultimo = millis();
  uint16_t m = bleServidor->getPeerMTU(bleServidor->getConnId());
  if (m >= 23) bleMtu = m;
  size_t n = bleSaidaN < (size_t)(bleMtu - 3) ? bleSaidaN : (size_t)(bleMtu - 3);
  bleTx->setValue((uint8_t *)bleSaida, n);
  bleTx->notify();
  memmove(bleSaida, bleSaida + n, bleSaidaN - n);
  bleSaidaN -= n;
}

// ------------------------------------------------------------------ geração do tom (LEDC)
// Cada canal tem um timer só dele, para cada um ter a sua frequência. O ESP32 comum tem 4
// timers rápidos e 4 lentos: os 6 canais cabem. O S3 tem 4 timers: 4 canais.
#ifdef SOC_LEDC_SUPPORT_HS_MODE
const int CANAIS = 6;
static ledc_mode_t modoDe(int c) { return c < 4 ? LEDC_HIGH_SPEED_MODE : LEDC_LOW_SPEED_MODE; }
#else
const int CANAIS = 4;
static ledc_mode_t modoDe(int c) { (void)c; return LEDC_LOW_SPEED_MODE; }
#endif
static ledc_timer_t timerDe(int c) { return (ledc_timer_t)(c % 4); }
static ledc_channel_t canalDe(int c) { return (ledc_channel_t)c; }

// 13 bits: com o relógio de 80 MHz o divisor do LEDC vai até 1024, então a faixa é de 9,5 Hz
// a 9,7 kHz. Com 10 bits nada abaixo de 76 Hz sairia — o baixo inteiro.
const ledc_timer_bit_t RESOLUCAO = LEDC_TIMER_13_BIT;
const uint32_t CHEIO = 1u << 13;              // duty de 100%: saída parada em ALTO
const uint32_t METADE = CHEIO / 2;            // onda quadrada
const uint32_t SILENCIO = LOGICA_INVERTIDA ? CHEIO : 0;

// ------------------------------------------------------------------ filas
struct Evento { uint32_t quando; float f; uint16_t a; };   // f = 0: silêncio; a: força em ‰
const int FILA = 96;
struct Canal {
  int pino = -1;
  bool soando = false;
  bool direto = false;                         // tocando um "D"
  uint32_t desde = 0, diretoAte = 0;
  // envelope ("E c atk tau sus rel"): o padrão é reto, o arco no máximo a nota inteira, que é como
  // o firmware tocava antes do envelope — e como toca se a página for antiga e não mandar o "E"
  uint16_t atk = 0, sus = 1000, rel = 0;
  uint32_t tau = 0;
  float pico = 1;                              // força da nota, 0 a 1 (o "a" do N)
  bool soltando = false;                       // depois do F, na rampa de soltura
  uint32_t soltouEm = 0;
  float nivelSolto = 0;                        // o nível no instante do F
  float nivel = 0;                             // o nível de agora, 0 a 1
  uint32_t dutyAgora = 0xFFFFFFFF;             // o último duty escrito, para só escrever quando muda
  Evento fila[FILA];
  int n = 0;
};
static Canal canal[6];
static uint32_t t0 = 0;                        // o instante do último "R"
static uint32_t perdidos = 0;                  // eventos que não couberam na fila

static void pinoSeguro(int g) {                // pino solto do LEDC, parado no silêncio
  pinMode(g, OUTPUT);
  digitalWrite(g, LOGICA_INVERTIDA ? HIGH : LOW);
}

static void duty(int c, uint32_t d) {
  if (canal[c].dutyAgora == d) return;
  canal[c].dutyAgora = d;
  ledc_set_duty(modoDe(c), canalDe(c), d);
  ledc_update_duty(modoDe(c), canalDe(c));
}

static void silencia(int c) {
  canal[c].direto = false;
  canal[c].soltando = false;
  if (canal[c].pino < 0) return;
  duty(c, SILENCIO);
  canal[c].soando = false;
}

// Fração aberta em ‰ → duty do LEDC, na polaridade do circuito
static uint32_t dutyAberto(uint32_t milesimos) {
  uint32_t aberto = milesimos * CHEIO / 1000;
  return LOGICA_INVERTIDA ? CHEIO - aberto : aberto;
}

// "D c d f": tom contínuo de f Hz com o arco aberto d ‰ de cada período (500 = onda quadrada, o
// volume máximo; menos que isso, mais baixo). d = 0 termina o tom. Esvazia a fila do canal.
static void tomDireto(int c, int d, float f) {
  if (c < 0 || c > 5 || canal[c].pino < 0) return;
  Canal &k = canal[c];
  k.n = 0;
  uint32_t hz = (uint32_t)lroundf(f);
  if (d <= 0 || hz < 10 || ledc_set_freq(modoDe(c), timerDe(c), hz) != ESP_OK) { silencia(c); return; }
  if (d > 900) d = 900;
  duty(c, dutyAberto((uint32_t)d));
  k.soando = true; k.direto = true;
  k.desde = millis(); k.diretoAte = k.desde + DIRETO_MS;
}

// ------------------------------------------------------------------ ENVELOPE
// O volume do arco na V3.6 segue sen(π·d), onde d é a fração do período da nota em que o arco fica
// aberto: máximo em d = 50% (a onda quadrada) e zero em d = 0 (simulação da conversa do circuito,
// FlybachSimulations/sim_envelope.py). Para um nível L de 0 a 1, d = asin(L)/π — a mesma conta que
// o gerador de tom (tom.html) já usa para o volume. O nível é a força da nota vezes a curva do
// envelope, igual à do áudio da página: rampa de atk ms até 1, depois decai com constante tau até
// sus, e no F desce em rel ms até 0. Recalculado a cada 1 ms em executa().
static uint32_t abertoDe(float L) {           // nível 0..1 → fração aberta em ‰ (0..500)
  if (L <= 0) return 0;
  if (L >= 1) return 500;
  return (uint32_t)lroundf(1000.0f * asinf(L) / (float)M_PI);
}
static float curva(int c, uint32_t agora) {   // por índice: o Arduino declara as funções antes do struct
  const Canal &k = canal[c];
  uint32_t t = agora - k.desde;
  float e;
  if (t < k.atk) e = (float)t / k.atk;
  else if (!k.tau) e = 1;
  else {
    float s = k.sus / 1000.0f;
    e = s + (1 - s) * expf(-(float)(t - k.atk) / (float)k.tau);
  }
  return k.pico * e;
}
static void envelope(int c, uint32_t agora) {
  Canal &k = canal[c];
  if (!k.soando || k.direto || k.pino < 0) return;
  float L;
  if (k.soltando) {
    uint32_t t = agora - k.soltouEm;
    if (t >= k.rel) { silencia(c); return; }
    L = k.nivelSolto * (1 - (float)t / k.rel);
  } else L = curva(c, agora);
  k.nivel = L;
  uint32_t d = abertoDe(L);
  duty(c, d >= 500 ? METADE : dutyAberto(d));   // 50%: tanto faz a polaridade
}
static void toca(int c, float f, uint16_t a) {
  Canal &k = canal[c];
  if (k.pino < 0) return;
  uint32_t hz = (uint32_t)lroundf(f);
  if (hz < 10 || ledc_set_freq(modoDe(c), timerDe(c), hz) != ESP_OK) { silencia(c); return; }
  k.pico = (a > 1000 ? 1000 : a) / 1000.0f;
  k.soando = true; k.soltando = false;
  k.desde = millis();
  envelope(c, k.desde);                         // com ataque, começa em 0 e sobe nos próximos ms
}
// F: começa a soltura; sem soltura, silencia já
static void solta(int c) {
  Canal &k = canal[c];
  if (!k.soando || k.direto || !k.rel) { silencia(c); return; }
  k.soltando = true; k.soltouEm = millis(); k.nivelSolto = k.nivel;
}
// "E c atk tau sus rel": a receita do envelope do canal; vale da próxima nota em diante
static void receita(int c, long atk, long tau, long sus, long rel) {
  if (c < 0 || c > 5) return;
  Canal &k = canal[c];
  k.atk = (uint16_t)constrain(atk, 0L, 1000L);
  k.tau = (uint32_t)constrain(tau, 0L, 60000L);
  k.sus = (uint16_t)constrain(sus, 0L, 1000L);
  k.rel = (uint16_t)constrain(rel, 0L, 2000L);
}

static int donoDoPino(int g, int fora) {
  for (int i = 0; i < 6; i++) if (i != fora && canal[i].pino == g) return i;
  return -1;
}

// Pinos que não podem virar saída: os da memória flash (e da PSRAM, no S3), os da USB nativa, os da
// serial que fala com a página, os que só servem de entrada e os que não existem. Ligar o LEDC num
// pino da flash trava o ESP: o gerador de tom mandava o mapa de pinos do S3 (4, 5, 6, 7, 15, 16) a um
// ESP32 comum, os canais 3 e 4 caíam nos GPIO 6 e 7, e a serial caía poucos segundos depois.
static bool pinoProibido(int g) {
#if CONFIG_IDF_TARGET_ESP32S3
  return g < 0 || g > 48 || g == 19 || g == 20 || (g >= 22 && g <= 37) || g == 43 || g == 44;
#else
  return g < 0 || g > 33 || g == 1 || g == 3 || (g >= 6 && g <= 11) || g == 20 || g == 24 || (g >= 28 && g <= 31);
#endif
}

// "P c g": o canal c passa a acionar o GPIO g; g = -1 libera o canal
static void fixaPino(int c, int g) {
  if (c < 0 || c > 5) return;
  if (g >= 0 && pinoProibido(g)) {
    diz.printf("canal %d: o GPIO %d não serve (flash, USB, serial, só entrada ou inexistente) — ignorado\n", c + 1, g);
    return;
  }
  Canal &k = canal[c];
  if (k.pino == g) return;                     // a página manda o mapa inteiro de novo: nada muda
  if (k.pino >= 0) {
    silencia(c);
    if (donoDoPino(k.pino, c) < 0) pinoSeguro(k.pino);
  }
  k.pino = -1; k.n = 0; k.soando = false;
  if (g < 0) return;
  if (c >= CANAIS) {
    diz.printf("canal %d: esta placa só tem timer para %d canais\n", c + 1, CANAIS);
    pinoSeguro(g);
    return;
  }
  int outro = donoDoPino(g, c);                // dois canais no mesmo pino: fica o último
  if (outro >= 0) { silencia(outro); canal[outro].pino = -1; canal[outro].n = 0; }

  ledc_timer_config_t tc = {};
  tc.speed_mode = modoDe(c);
  tc.duty_resolution = RESOLUCAO;
  tc.timer_num = timerDe(c);
  tc.freq_hz = 440;
  tc.clk_cfg = LEDC_AUTO_CLK;
  ledc_channel_config_t cc = {};
  cc.gpio_num = g;
  cc.speed_mode = modoDe(c);
  cc.channel = canalDe(c);
  cc.intr_type = LEDC_INTR_DISABLE;
  cc.timer_sel = timerDe(c);
  cc.duty = SILENCIO;
  cc.hpoint = 0;
  if (ledc_timer_config(&tc) != ESP_OK || ledc_channel_config(&cc) != ESP_OK) {
    diz.printf("canal %d: o GPIO %d não serve de saída\n", c + 1, g);
    return;
  }
  k.pino = g;
  duty(c, SILENCIO);
}

// insere mantendo a fila em ordem de tempo; a página manda quase sempre em ordem
static void enfileira(int c, uint32_t quando, float f, uint16_t a) {
  if (c < 0 || c > 5 || canal[c].pino < 0) return;
  Canal &k = canal[c];
  if (k.direto) silencia(c);                   // nota de música cancela o tom contínuo
  if (k.n >= FILA) { perdidos++; return; }
  int i = k.n;
  while (i > 0 && (int32_t)(k.fila[i - 1].quando - quando) > 0) { k.fila[i] = k.fila[i - 1]; i--; }
  k.fila[i] = {quando, f, a};
  k.n++;
}

static void executa() {
  static uint32_t ultimoMs = 0;
  uint32_t agora = millis();
  bool novoMs = agora != ultimoMs;               // o envelope anda de 1 em 1 ms
  ultimoMs = agora;
  for (int c = 0; c < 6; c++) {
    Canal &k = canal[c];
    while (k.n && (int32_t)(agora - k.fila[0].quando) >= 0) {
      Evento e = k.fila[0];
      for (int i = 1; i < k.n; i++) k.fila[i - 1] = k.fila[i];
      k.n--;
      if (e.f > 0) toca(c, e.f, e.a); else solta(c);
    }
    if (novoMs) envelope(c, agora);
    if (k.direto) { if ((int32_t)(agora - k.diretoAte) > 0) silencia(c); }
    else if (k.soando && !k.n && agora - k.desde > NOTA_MAXIMA_MS) silencia(c);
  }
}

// Por que o ESP reiniciou da última vez. Para separar, quando a serial cai com o arco ligado, queda
// de tensão (BROWNOUT) e travamento (PANIC, WDT) de uma queda só do USB, em que o ESP nem reinicia
// e o tempo ligado continua contando: no gerador de tom, com o arco aberto sem parar, a porta caía
// em poucos segundos, e na música, não.
static const char *motivoReinicio() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:   return "energia ligada";
    case ESP_RST_EXT:       return "pino de reset";
    case ESP_RST_SW:        return "reinício pelo programa (ou porta serial aberta)";
    case ESP_RST_PANIC:     return "TRAVAMENTO (panic)";
    case ESP_RST_INT_WDT:   return "TRAVAMENTO (watchdog de interrupção)";
    case ESP_RST_TASK_WDT:  return "TRAVAMENTO (watchdog de tarefa)";
    case ESP_RST_WDT:       return "TRAVAMENTO (watchdog)";
    case ESP_RST_BROWNOUT:  return "QUEDA DE TENSÃO (brownout)";
    case ESP_RST_DEEPSLEEP: return "volta do sono";
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 1, 0)
    case ESP_RST_USB:       return "reinício pela USB nativa (gravação ou porta aberta)";
#endif
    default:                return "outro";
  }
}

static bool paginaFalou = false;     // a página mandou algo durante o teste: ela manda nos pinos agora

static void trata(char *s) {
  int c, g; long t; float f;
  if (s[0] && s[0] != '?') paginaFalou = true;
  switch (s[0]) {
    case 'P': if (sscanf(s + 1, "%d %d", &c, &g) == 2) fixaPino(c, g); break;
    case 'R': t0 = millis(); for (int i = 0; i < 6; i++) canal[i].n = 0; break;
    case 'X': for (int i = 0; i < 6; i++) { silencia(i); canal[i].n = 0; } break;
    // a força é opcional: página antiga manda "N c t f", e a nota vai no máximo, como antes
    case 'N': { int a = 1000; if (sscanf(s + 1, "%d %ld %f %d", &c, &t, &f, &a) >= 3 && t >= 0)
                  enfileira(c, t0 + (uint32_t)t, f, (uint16_t)constrain(a, 0, 1000)); break; }
    case 'F': if (sscanf(s + 1, "%d %ld", &c, &t) == 2 && t >= 0) enfileira(c, t0 + (uint32_t)t, 0, 0); break;
    case 'E': { long atk, tau, sus, rel; if (sscanf(s + 1, "%d %ld %ld %ld %ld", &c, &atk, &tau, &sus, &rel) == 5)
                  receita(c, atk, tau, sus, rel); break; }
    case 'D': { int d; if (sscanf(s + 1, "%d %d %f", &c, &d, &f) == 3) tomDireto(c, d, f); break; }
    case '?':                                  // para conferir pelo monitor serial
      diz.printf("%s · lógica %s · %d canais · pinos", VERSAO, LOGICA_INVERTIDA ? "invertida" : "direta", CANAIS);
      for (int i = 0; i < 6; i++) diz.printf(" %d", canal[i].pino);
      diz.print(" · envelopes");
      for (int i = 0; i < 6; i++)
        diz.printf(" [%u %lu %u %u]", canal[i].atk, (unsigned long)canal[i].tau, canal[i].sus, canal[i].rel);
      diz.printf(" · eventos perdidos %lu · ligado há %lu s · último reinício: %s", (unsigned long)perdidos,
                    (unsigned long)(millis() / 1000), motivoReinicio());
      // a página lê o "mtu N" para saber o tamanho dos pacotes que pode mandar pelo Bluetooth
      if (bleConectado) diz.printf(" · bluetooth conectado, mtu %u", bleServidor->getPeerMTU(bleServidor->getConnId()));
      else diz.printf(" · bluetooth anunciando \"%s\"", NOME_BLE);
      diz.printf(" · pergunta pela %s\n", ultimaFonte >= 0 ? NOME_FONTE[ultimaFonte] : "?");
      break;
  }
}

// ------------------------------------------------------------------ teste pelo botão BOOT
// O canal que já está no pino de teste toca nele; se nenhum está, o canal 1 vai para lá durante o
// teste e volta ao pino de antes no fim. Acaba no segundo aperto, no fim de TESTE_MAX_MS ou quando a
// página toma o canal (X, R, N, F, D). Se a página mandou qualquer coisa durante o teste, o pino não
// volta: o mapa agora é o dela.
static int testeCanal = -1;
static int testeAntes = -2;          // -2: o canal já estava no pino de teste, nada a devolver

static void testeDesliga() {
  int c = testeCanal;
  testeCanal = -1;
  silencia(c);
  if (testeAntes != -2 && !paginaFalou) fixaPino(c, testeAntes);
  diz.println("teste: desligado");
}

static void testeLiga() {
  int c = donoDoPino(TESTE_PINO, -1);
  testeAntes = -2;
  paginaFalou = false;
  if (c < 0) {
    c = 0;
    testeAntes = canal[0].pino;
    fixaPino(0, TESTE_PINO);
  }
  if (canal[c].pino != TESTE_PINO) {
    diz.printf("teste: o GPIO %d não pôde virar saída\n", TESTE_PINO);
    return;
  }
  tomDireto(c, 500, TESTE_HZ);
  canal[c].diretoAte = canal[c].desde + TESTE_MAX_MS;
  testeCanal = c;
  diz.printf("teste: %.0f Hz no GPIO %d por até %lu s — BOOT de novo desliga\n", TESTE_HZ, TESTE_PINO,
                (unsigned long)(TESTE_MAX_MS / 1000));
}

// O aperto só vale com o botão parado em BAIXO por 80 ms. Antes valia a primeira descida, e nas
// placas com a segunda USB pelo CH343 (ou CP210x) o circuito de reset automático liga o DTR ao
// GPIO 0: abrir a porta (o testar_serial.py, um monitor serial) dava um pulso curto em BAIXO, lido
// como aperto — o tom de teste ligava no máximo, por até 2 min, sem ninguém tocar na placa. Visto
// na bancada em 25/nov. Um dedo segura bem mais que 80 ms; o pulso do DTR, poucos ms.
static void testeBotao() {
  static int estavel = HIGH, lido = HIGH;    // solto: o pull-up segura em ALTO
  static uint32_t desde = 0;
  int agora = digitalRead(TESTE_BOTAO);
  if (agora != lido) { lido = agora; desde = millis(); }
  else if (agora != estavel && millis() - desde >= 80) {
    estavel = agora;
    if (estavel == LOW) {
      if (testeCanal >= 0) testeDesliga(); else testeLiga();
    }
  }
  if (testeCanal >= 0 && !canal[testeCanal].direto) testeDesliga();   // acabou o tempo, ou a página assumiu
}

void setup() {
  // primeiro de tudo, antes até da serial: os pinos no silêncio, arco cortado — o de teste também,
  // que no ESP32 comum não é padrão de canal nenhum e ficaria solto até a página mandar o mapa
  for (int i = 0; i < 6; i++) pinoSeguro(PINOS_PADRAO[i]);
  if (!pinoProibido(TESTE_PINO)) pinoSeguro(TESTE_PINO);
  pinMode(TESTE_BOTAO, INPUT_PULLUP);
  Serial.begin(BAUD);
#if ARDUINO_USB_MODE && ARDUINO_USB_CDC_ON_BOOT
  Serial.setTxTimeoutMs(0);                    // USB nativa sem a porta aberta: não espera (ver Eco)
#endif
#if ARDUINO_USB_CDC_ON_BOOT
  Serial0.begin(BAUD);
#endif
  for (int i = 0; i < CANAIS; i++) fixaPino(i, PINOS_PADRAO[i]);
  bleInicia();
  diz.printf("flyback-esp32 pronto · %s · lógica %s · %d canais · bluetooth \"%s\" · reinício: %s\n", VERSAO,
                LOGICA_INVERTIDA ? "invertida (ALTO corta o arco)" : "direta (ALTO libera o arco)", CANAIS, NOME_BLE,
                motivoReinicio());
}

// uma linha em montagem por caminho: um pedaço de linha da USB não se mistura com um do Bluetooth
static void recebe(int fonte, char ch) {
  static char linha[FONTES][64];
  static int tam[FONTES] = {0};
  if (ch == '\n') {
    linha[fonte][tam[fonte]] = 0;
    if (tam[fonte]) ultimaFonte = fonte;
    trata(linha[fonte]);
    tam[fonte] = 0;
  } else if (ch != '\r' && tam[fonte] < (int)sizeof(linha[0]) - 1) linha[fonte][tam[fonte]++] = ch;
}

void loop() {
  while (Serial.available()) recebe(DA_USB, (char)Serial.read());
#if ARDUINO_USB_CDC_ON_BOOT
  while (Serial0.available()) recebe(DA_UART, (char)Serial0.read());
#endif
  char buf[128];
  size_t n;
  while ((n = xStreamBufferReceive(bleEntrada, buf, sizeof(buf), 0)) > 0)
    for (size_t i = 0; i < n; i++) recebe(DO_BLE, buf[i]);
  // Caiu o Bluetooth de quem estava tocando: silêncio já, sem esperar a fila acabar ou os 20 s da
  // nota presa. Se quem toca é a USB, a queda de um celular conectado não a interrompe.
  if (bleCaiu) {
    bleCaiu = false;
    BLEDevice::startAdvertising();             // volta a anunciar, para reconectar
    if (ultimaFonte == DO_BLE) {
      for (int i = 0; i < 6; i++) { silencia(i); canal[i].n = 0; }
      diz.println("bluetooth: caiu a conexão — silêncio");
    } else diz.println("bluetooth: desconectado");
  }
  bleEnvia();
  executa();
  testeBotao();
}
