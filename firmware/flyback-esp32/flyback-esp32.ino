/*
  flyback-esp32 — o firmware dos flybacks para o site flyback-midi.

  Recebe pela serial o protocolo de docs/protocolo-serial.md (P, E, R, N, F, X, D e ?) e toca cada
  canal como onda quadrada na frequência da nota, num GPIO que interrompe o oscilador do flyback.
  O volume da nota — força (velocity) e envelope (ataque, decaimento, sustentação, soltura) — sai
  pela fração do período em que o arco fica aberto, recalculada a cada 1 ms (ver ENVELOPE abaixo).
  Sem computador, o botão BOOT liga e desliga um tom de teste de 440 Hz no GPIO 4 (ver TESTE_*).

  Testado com: ESP32 comum ("ESP32 Dev Module" no Arduino). Compila também para o ESP32-S3,
  mas lá só os canais 1 a 4 tocam — ver CANAIS abaixo.

  Antes de gravar, confira LOGICA_INVERTIDA para o seu circuito.
*/
#include <Arduino.h>
#include "driver/ledc.h"
#include "esp_system.h"
#include <math.h>

// Aparece no boot e no "?": para saber, pelo monitor serial, qual versão está gravada na placa.
const char *VERSAO = "nov/2026 · envelope";

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
    Serial.printf("canal %d: o GPIO %d não serve (flash, USB, serial, só entrada ou inexistente) — ignorado\n", c + 1, g);
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
    Serial.printf("canal %d: esta placa só tem timer para %d canais\n", c + 1, CANAIS);
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
    Serial.printf("canal %d: o GPIO %d não serve de saída\n", c + 1, g);
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
      Serial.printf("%s · lógica %s · %d canais · pinos", VERSAO, LOGICA_INVERTIDA ? "invertida" : "direta", CANAIS);
      for (int i = 0; i < 6; i++) Serial.printf(" %d", canal[i].pino);
      Serial.print(" · envelopes");
      for (int i = 0; i < 6; i++)
        Serial.printf(" [%u %lu %u %u]", canal[i].atk, (unsigned long)canal[i].tau, canal[i].sus, canal[i].rel);
      Serial.printf(" · eventos perdidos %lu · ligado há %lu s · último reinício: %s\n", (unsigned long)perdidos,
                    (unsigned long)(millis() / 1000), motivoReinicio());
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
  Serial.println("teste: desligado");
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
    Serial.printf("teste: o GPIO %d não pôde virar saída\n", TESTE_PINO);
    return;
  }
  tomDireto(c, 500, TESTE_HZ);
  canal[c].diretoAte = canal[c].desde + TESTE_MAX_MS;
  testeCanal = c;
  Serial.printf("teste: %.0f Hz no GPIO %d por até %lu s — BOOT de novo desliga\n", TESTE_HZ, TESTE_PINO,
                (unsigned long)(TESTE_MAX_MS / 1000));
}

static void testeBotao() {
  static int antes = HIGH;           // solto: o pull-up segura em ALTO
  static uint32_t mudou = 0;
  int agora = digitalRead(TESTE_BOTAO);
  if (agora != antes && millis() - mudou > 50) {     // 50 ms: o repique do botão
    mudou = millis();
    antes = agora;
    if (agora == LOW) {
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
  for (int i = 0; i < CANAIS; i++) fixaPino(i, PINOS_PADRAO[i]);
  Serial.printf("flyback-esp32 pronto · %s · lógica %s · %d canais · reinício: %s\n", VERSAO,
                LOGICA_INVERTIDA ? "invertida (ALTO corta o arco)" : "direta (ALTO libera o arco)", CANAIS, motivoReinicio());
}

void loop() {
  static char linha[64];
  static int tam = 0;
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n') { linha[tam] = 0; trata(linha); tam = 0; }
    else if (ch != '\r' && tam < (int)sizeof(linha) - 1) linha[tam++] = ch;
  }
  executa();
  testeBotao();
}
