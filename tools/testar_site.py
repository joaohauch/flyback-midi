"""Abre o index.html num Chrome de verdade e exercita o player: 2 e 6 flybacks, o
roteamento, a separação do WAV e a serial com uma porta simulada.

    python tools/testar_site.py            # roda tudo e diz o que falhou
    python tools/testar_site.py --telas    # e guarda capturas de tela em quatro tamanhos

Opcional, como o transcrever.py: precisa de `pip install playwright` e de um Chrome ou Edge
instalado (não baixa navegador; usa o do sistema). Nada no site depende disto.

Existe porque a página é um arquivo único de JavaScript escrito à mão, sem build e sem
tipagem: um erro de digitação num caminho pouco usado só aparece quando alguém clica ali.
Rode antes de publicar qualquer mudança no index.html.
"""
import argparse
import functools
import http.server
import os
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
falhas = []

# Porta Web Serial falsa: guarda o texto que a página escreve, para conferir o protocolo
# sem ESP32 nenhum ligado.
SERIAL_FALSA = """
(() => {
  const dec = new TextDecoder(), enc = new TextEncoder();
  window.__serial = { bytes: '', aberta: null, fechada: false };
  let ctl = null;
  const porta = {
    async open(o){ window.__serial.aberta = o; },
    async close(){ window.__serial.fechada = true; },
    /* o "?" tem resposta, como o firmware: a página mostra a versão gravada */
    readable: new ReadableStream({ start(c){ ctl = c; } }),
    writable: { getWriter(){ return {
      async write(b){
        const t = dec.decode(b);
        window.__serial.bytes += t;
        if (t === '?\\n' && !window.__serial.mudo) setTimeout(() => ctl.enqueue(enc.encode('nov/2026 · envelope · bluetooth · lógica direta · 4 canais · pinos 4 5 6 7 -1 -1 · bluetooth anunciando "Flyback ESP32" · pergunta pela USB\\r\\n')), 20);
      }, releaseLock(){} }; } }
  };
  const alvo = new EventTarget();
  alvo.requestPort = async () => porta;
  Object.defineProperty(navigator, 'serial', { value: alvo });
})();
"""

# ESP falso pelo Bluetooth: o serviço UART da Nordic, com o MTU de 23 (20 bytes por escrita) até o
# "?" responder "mtu 185". Cada escrita demora 5 ms e conta quantas estão no ar ao mesmo tempo: o
# Web Bluetooth recusa duas juntas, e a página tem de mandar uma por vez.
BLE_FALSO = """
(() => {
  const dec = new TextDecoder(), enc = new TextEncoder();
  const b = window.__ble = { bytes: '', escritas: [], noAr: 0, maxNoAr: 0, mtu: 23, grande: 0, conectado: false, feitas: 0 };
  const tx = new EventTarget();
  const notifica = txt => { const u = enc.encode(txt); for (let i = 0; i < u.length; i += b.mtu - 3) {
    tx.value = new DataView(u.slice(i, i + b.mtu - 3).buffer); tx.dispatchEvent(new Event('characteristicvaluechanged')); } };
  const rx = {
    async writeValueWithoutResponse(u){
      b.noAr++; b.maxNoAr = Math.max(b.maxNoAr, b.noAr);
      if (u.length > b.mtu - 3) b.grande++;
      await new Promise(ok => setTimeout(ok, 5));
      b.noAr--; b.escritas.push(u.length);
      b.bytes += dec.decode(u);
      const linhas = b.bytes.split('\\n'); linhas.pop();
      for (; b.feitas < linhas.length; b.feitas++) if (linhas[b.feitas] === '?') { b.mtu = 185;
        setTimeout(() => notifica('nov/2026 · envelope · bluetooth · lógica direta · 4 canais · pinos 4 5 6 7 -1 -1 · bluetooth conectado, mtu 185 · pergunta pela Bluetooth\\r\\n'), 20); }
    }
  };
  tx.startNotifications = async () => tx;
  const dev = new EventTarget();
  dev.name = 'Flyback ESP32';
  dev.gatt = {
    get connected(){ return b.conectado; },
    async connect(){ b.conectado = true; return { getPrimaryService: async () => ({ getCharacteristic: async u => u.startsWith('6e400002') ? rx : tx }) }; },
    disconnect(){ if (!b.conectado) return; b.conectado = false; dev.dispatchEvent(new Event('gattserverdisconnected')); }
  };
  b.cair = () => dev.gatt.disconnect();
  Object.defineProperty(navigator, 'bluetooth', { value: { requestDevice: async o => { b.filtros = o; return dev; } } });
})();
"""


def confere(cond, msg):
    print(('  ok     ' if cond else '  FALHA  ') + msg)
    if not cond:
        falhas.append(msg)


def servir():
    """Servidor HTTP numa porta livre, em segundo plano, na raiz do repositório."""
    class Calado(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Calado, directory=str(RAIZ)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}/'


def estado(pg):
    return pg.evaluate("""() => ({
        n: nCanais(), faixas: tracks.length, assign: assign.slice(), nomes: tracks.map(t => t.name),
        segs: ch.slice(0, nCanais()).map(c => c.segs.length),
        pistas: document.querySelectorAll('#lanes .lane').length,
        canais: document.querySelectorAll('#strips .strip').length,
        presets: [...document.querySelectorAll('#presets button')].map(b => b.textContent),
        tocando: playing, pos: position() })""")


def abrir(pg, base, caminho):
    pg.goto(base + '?m=' + urllib.parse.quote(caminho))
    pg.wait_for_selector('#tracks .trk', timeout=30000)
    time.sleep(.3)


def player(nav, base, telas):
    pg = nav.new_page(viewport={'width': 1920, 'height': 1080})
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.on('console', lambda m: erros.append(m.text) if m.type == 'error' else None)
    pg.goto(base)
    pg.evaluate('localStorage.clear()')

    print('dois flybacks, pelo P2')
    abrir(pg, base, 'exemplos/Korobeiniki.mid')
    e = estado(pg)
    confere(e['n'] == 2 and e['pistas'] == 2 and e['canais'] == 2, 'começa com dois flybacks, duas pistas e dois canais')
    confere(e['faixas'] == 4 and any(e['segs']), f'MIDI formato 0 separado por canal: {e["faixas"]} faixas')
    confere(len(e['presets']) == 6, 'os seis presets de dois canais')
    pg.click('#play'); time.sleep(1.5)
    e = estado(pg)
    confere(e['tocando'] and e['pos'] > 1, f'toca ({e["pos"]:.1f} s)')
    confere(any(t != '—' for t in pg.eval_on_selector_all('#lanes .nota', 'x => x.map(e => e.textContent)')), 'pista mostra a nota')
    pg.keyboard.press('Space'); time.sleep(.2)
    confere(not estado(pg)['tocando'], 'espaço pausa')
    r = pg.evaluate("""async () => {
        assign = assign.map(() => 0); assign[0] = 1; rebuild();
        const b = await renderWav(), pico = c => b.getChannelData(c).reduce((m, v) => Math.max(m, Math.abs(v)), 0);
        return [b.numberOfChannels, pico(0), pico(1)]; }""")
    confere(r[0] == 2 and r[1] > .1 and r[2] == 0, f'WAV estéreo com separação dura: o lado sem faixa sai zero ({r})')

    print('seis flybacks')
    abrir(pg, base, 'transcritas/Victor & Leo - Borboletas (Mirelo).mid')
    pg.select_option('#espN', '6'); time.sleep(.3)
    e = estado(pg)
    confere(e['pistas'] == 6 and e['canais'] == 6, 'seis pistas e seis canais')
    rotas = {e['nomes'][k]: [i + 1 for i in range(6) if m >> i & 1] for k, m in enumerate(e['assign'])}
    confere(rotas.get('voice', [0])[0] == 1 and rotas.get('electric_bass') == [2] and rotas.get('acoustic_guitar', [0])[0] == 3
            and rotas.get('drums') == [4] and 5 in rotas.get('synth_pad', []) + rotas.get('acoustic_piano', []),
            f'montagem fixa: 1 voz, 2 baixo, 3 violão, 4 bateria, 5 teclado ({rotas})')
    g = pg.evaluate("ch.slice(0, 6).map(c => c.ctl.ganho)")
    confere(g == [70] * 6, f'ganho padrão de 70% em todo flyback, num navegador sem nada salvo ({g})')
    env = pg.evaluate("ch.slice(0, 6).map(c => c.ctl.env)")
    confere(env[0] == 'medio' and env[2] == 'corda' and env[3] == 'percussivo',
            f'som padrão da montagem: voz em médio, violão em corda, bateria em batida ({env})')
    ritmo = pg.evaluate("ch[3].segs.map(s => s.n)")
    confere(ritmo and set(ritmo) <= {33, 40, 45, 50, 55, 60},
            f'bateria vira estouros de bumbo, caixa e tons, sem chimbal nem prato ({sorted(set(ritmo))})')
    # o som segue o instrumento: o da guitarra vale para todas as músicas e todo arco com guitarra
    pg.select_option('#env2', 'sustentado')
    abrir(pg, base, 'transcritas/AC-DC - Thunderstruck.mid')
    r = pg.evaluate("ch.slice(0, 6).map(c => [c.som, c.ctl.env])")
    confere(all(e == 'sustentado' for f, e in r if f == 'guitarra') and r[0] == ['voz', 'medio'],
            f'o envelope da guitarra mudado numa música vale em outra, em todo arco com guitarra ({r})')
    pg.evaluate("sons.guitarra.agudo = 400; rebuild()")
    alto = pg.evaluate("Math.max(...ch[2].segs.map(s => s.f))")
    confere(alto <= 400, f'limite de agudo desce as notas de oitava até caber ({alto:.0f} Hz)')
    pg.evaluate("sons.guitarra.agudo = AGUDO_LIVRE; sons.guitarra.env = 'corda'; store.set('sons', sons); rebuild()")
    pg.select_option('#env2', 'corda')
    abrir(pg, base, 'transcritas/Victor & Leo - Borboletas (Mirelo).mid')
    pg.select_option('#espN', '4'); time.sleep(.2)
    e = estado(pg)
    confere(e['pistas'] == 4 and all(m < 16 for m in e['assign']), 'quatro flybacks: nenhuma rota além do canal 4')
    antes = e['assign'][1]
    pg.click('#tracks .trk:nth-child(2) .seg button:nth-child(5)')
    confere(estado(pg)['assign'][1] == antes | 8, 'uma faixa em dois canais')
    pg.select_option('#espN', '2'); time.sleep(.2)
    confere(all(m <= 3 for m in estado(pg)['assign']), 'dois flybacks têm configuração própria')
    pg.select_option('#espN', '4'); time.sleep(.2)
    confere(estado(pg)['assign'][1] == antes | 8, 'voltar a quatro recupera a rota manual')
    pg.click('#strips .strip:nth-child(2) .strip-h button:nth-child(2)')
    confere(pg.evaluate('!soa(1) && soa(0)'), 'silenciar um canal')
    pg.click('#strips .strip:nth-child(2) .strip-h button:nth-child(2)')
    n = pg.evaluate('(async () => (await renderWav()).numberOfChannels)()')
    confere(n == 4, f'WAV com um canal por flyback ({n})')

    print('acorde em vários flybacks')
    pg.select_option('#espN', '6')
    abrir(pg, base, 'transcritas/AC-DC - Back In Black.mid')
    r = pg.evaluate("""() => { const g = tracks.findIndex(t => /guitar/.test(t.name));
        return { canais: canaisDe(assign[g]).map(i => i + 1), picks: canaisDe(assign[g]).map(i => ch[i].ctl.pick) }; }""")
    confere(r['canais'] == [3] and r['picks'] == ['lo'],
            f'a guitarra fica no arco dela, na nota grave: arco vazio não recebe pedaço de acorde ({r})')
    abrir(pg, base, 'transcritas/Scorpions - Still Loving You.mid')
    r = pg.evaluate("""() => tracks.map((t, k) => [t.name, canaisDe(assign[k]).map(i => i + 1), canaisDe(assign[k]).map(i => ch[i].ctl.pick)])""")
    rotas = {n: (a, p) for n, a, p in r}
    dist, voz = rotas.get('distorted electric guitar'), rotas.get('voice')
    confere(dist and len(dist[0]) == 1 and dist[0][0] in (5, 6) and dist[1] == ['lo']
            and voz and voz[0][0] == 1 and len(voz[0]) == 2 and set(voz[1]) == {'div'},
            f'a segunda guitarra ganha arco próprio, na nota grave, e a segunda voz reparte com o 1 ({rotas})')
    # repartir à mão: a guitarra de Iron Man em três arcos
    abrir(pg, base, 'transcritas/Black Sabbath - Iron Man.mid')
    r = pg.evaluate("""() => { juntarLinhas(tracks.find(t => /guitar/.test(t.name) && !t.linha).name);
        const g = tracks.findIndex(t => /guitar/.test(t.name)), v = prio.indexOf(3);
        assign[g] = (1 << 2) | (1 << 4) | (1 << 5); [2, 4, 5].forEach(i => { ch[i].ctl.pick = 'div'; }); rebuild();
        const teto = avgPitch(tracks[v]) - 5;
        const acima = [4, 5].flatMap(i => ch[i].segs.filter(s => s.n > teto)).length;
        let igual = 0;
        [[2, 4], [2, 5], [4, 5]].forEach(([i, j]) => ch[i].segs.forEach(a => ch[j].segs.forEach(b => {
          if (a.n === b.n){ const x = Math.max(a.start, b.start), y = Math.min(a.end, b.end); if (y > x) igual += y - x; } })));
        return { notas: [2, 4, 5].map(i => ch[i].segs.length), acima, igual: +igual.toFixed(2) }; }""")
    confere(all(r['notas']) and not r['acima'] and r['igual'] == 0,
            f'repartir à mão: cada arco com notas suas, nada acima do teto nos extras, nenhuma nota repetida ({r})')
    # o baixo toca a mais grave que soa, mesmo com acorde de synth na faixa dele
    abrir(pg, base, 'transcritas/Rick Astley - Never Gonna Give You Up.mid')
    r = pg.evaluate("""() => { const b = tracks.findIndex(t => familia(t) === 'baixo'); let erros = 0, total = 0;
        ch[1].segs.forEach(s => { const m = (s.start + s.end) / 2;
          const soando = tracks[b].notes.filter(x => x.t0 <= m && x.t1 > m).map(x => x.n);
          if (soando.length){ total++; if (s.n !== Math.min(...soando)) erros++; } });
        return { total, erros, juntas: +polifonia(tracks[b]).toFixed(2) }; }""")
    confere(r['total'] > 100 and r['erros'] <= r['total'] * .02,
            f'o arco do baixo toca a nota mais grave que soa na faixa ({r})')
    # a oitava é da música
    abrir(pg, base, "transcritas/Guns N' Roses - Sweet Child O' Mine.mid")
    pg.select_option('#oct0', '1')
    abrir(pg, base, 'transcritas/AC-DC - Back In Black.mid')
    outra = pg.evaluate('ch[0].ctl.oct')
    abrir(pg, base, "transcritas/Guns N' Roses - Sweet Child O' Mine.mid")
    volta = pg.evaluate('ch[0].ctl.oct')
    confere(outra == 0 and volta == 1, f'a oitava mudada numa música fica nela e não passa para outra ({outra}, {volta})')
    abrir(pg, base, 'transcritas/Victor & Leo - Borboletas.mid')
    r = pg.evaluate("""() => { const v = prio.indexOf(3), arcos = canaisDe(assign[v]);
        const media = i => { const s = ch[i].segs; return s.reduce((a, x) => a + x.n, 0) / s.length; };
        return { nome: tracks[v].name, arcos: arcos.map(i => i + 1), alturas: arcos.map(i => Math.round(media(i))) }; }""")
    confere(r['nome'] == 'voice' and len(r['arcos']) == 2 and r['arcos'][0] == 1 and r['alturas'][0] > r['alturas'][1],
            f'a segunda voz da dupla vai para outro arco, e a de cima fica no 1 ({r})')
    a = r['arcos'][1] - 1
    r = pg.evaluate(f"[ch[{a}].som, ch[{a}].ctl.env, ch[0].ctl.env, document.querySelectorAll('#strips .strip')[{a}].textContent]")
    confere(r[0] == 'voz' and r[1] == r[2] and 'som de voz' in r[3],
            f'o arco da segunda voz soa como voz, e o mixer diz isso ({r})')
    abrir(pg, base, 'transcritas/Victor & Leo - Borboletas (Mirelo).mid')
    pg.click('#presets button:nth-child(1)')      # Montagem fixa, por cima do ajuste salvo antes
    r = pg.evaluate("() => tracks.filter((t, k) => assign[k] >> 4 & 1).map(t => [t.name, prio[tracks.indexOf(t)]])")
    dono = max(r, key=lambda x: x[1])[0] if r else None
    confere(dono == 'acoustic_piano', f'no teclado manda a faixa com mais ataques, o piano, não o pad ({r})')

    print('linhas')
    abrir(pg, base, 'transcritas/Dave Rodgers - Deja Vu.mid')
    botao = pg.locator('#tracks .trk', has_text='electric piano').first.locator('button.mini')
    r = pg.evaluate("""() => { const teto = avgPitch(tracks[prio.indexOf(3)]) - 5;
        return tracks.filter(t => t.acorde && assign[tracks.indexOf(t)]).map(t => [t.name, Math.round(avgPitch(t)), Math.round(teto)]); }""")
    confere(r and all(a <= t for _, a, t in r), f'a montagem põe as notas de cima do acorde do teclado no arco vazio, só abaixo da voz ({r})')
    if botao.inner_text() == 'juntar as linhas':
        botao.click(); time.sleep(.3)
    pg.locator('#tracks .trk', has_text='electric piano').first.locator('button.mini').click(); time.sleep(.5)
    r = pg.evaluate("""() => tracks.filter(t => t.linha === 'electric piano').map(t => [Math.round(avgPitch(t)), +polifonia(t).toFixed(2), assign[tracks.indexOf(t)]])""")
    alturas = [a for a, _, _ in r]
    confere(len(r) >= 4 and alturas == sorted(alturas, reverse=True) and len(set(alturas)) == len(alturas),
            f'o teclado de seis notas vira linhas, da mais aguda à mais grave, sem repetir registro ({alturas})')
    confere(all(p <= 1.05 for _, p, _ in r) and all(a == 0 for _, _, a in r),
            f'cada linha toca uma nota por vez, e entra desligada ({r})')
    pg.evaluate("""() => { const k = tracks.findIndex(t => t.linha && t.nLinha === 2); assign[k] = 1 << 5; rebuild(); renderTracks(); saveCfg(); }""")
    abrir(pg, base, 'transcritas/AC-DC - Back In Black.mid')
    abrir(pg, base, 'transcritas/Dave Rodgers - Deja Vu.mid')
    r = pg.evaluate("() => tracks.filter((t, k) => t.linha && assign[k]).map(t => [t.nLinha, canaisDe(assign[tracks.indexOf(t)])])")
    confere(r == [[2, [5]]], f'a música reabre com as linhas separadas e a rota de cada uma ({r})')
    pg.locator('#tracks .trk', has_text='electric piano').first.locator('button.mini').click(); time.sleep(.3)
    confere(pg.evaluate('!tracks.some(t => t.linha) && !separadas.length'), 'juntar as linhas tira as linhas da lista')
    pg.evaluate("store.del(cfgChave())")

    print('juntar versões')
    abrir(pg, base, "transcritas/Bon Jovi - Livin' On A Prayer.mid")
    opcoes = pg.eval_on_selector_all('#juntarSel option', 'x => x.map(o => o.value)')
    confere("transcritas/Bon Jovi - Livin' On A Prayer (Mirelo).mid" in opcoes, f'a versão do Mirelo aparece para juntar ({opcoes})')
    antes = pg.evaluate('tracks.length')
    pg.select_option('#juntarSel', "transcritas/Bon Jovi - Livin' On A Prayer (Mirelo).mid"); time.sleep(1.5)
    r = pg.evaluate("""() => ({ n: tracks.length, desvio: juntas[0] && juntas[0].desvio,
        novas: tracks.filter(t => t.junta).map((t, j) => [t.name, assign[tracks.indexOf(t)]]) })""")
    confere(r['n'] > antes and all(a == 0 for _, a in r['novas']) and all(' · Mirelo' in n for n, _ in r['novas']),
            f'as faixas da outra versão entram desligadas e com o nome dela ({r["novas"]})')
    confere(r['desvio'] is not None and abs(abs(r['desvio']) - .84) < .05,
            f'e alinhadas no tempo: o áudio do Mirelo está 0,84 s deslocado ({r["desvio"]})')
    pg.evaluate("""() => { const v = tracks.findIndex(t => t.name === 'voice · Mirelo'), m = tracks.findIndex(t => t.name === 'voice');
        assign[v] = assign[m]; assign[m] = 0; rebuild(); saveCfg(); }""")
    abrir(pg, base, 'transcritas/AC-DC - Back In Black.mid')
    abrir(pg, base, "transcritas/Bon Jovi - Livin' On A Prayer.mid")
    r = pg.evaluate("() => tracks.filter((t, k) => assign[k] & 1).map(t => t.name)")
    confere(r == ['voice · Mirelo'], f'reabrir traz a versão juntada e a escolha de faixa ({r})')
    with pg.expect_download() as d:
        pg.click('#midiDown')
    dados = list(Path(d.value.path()).read_bytes())
    volta = pg.evaluate("b => parseMidi(new Uint8Array(b).buffer).map(t => [t.name, t.notes.length])", dados)
    usadas = pg.evaluate("tracks.filter((t, k) => assign[k]).map(t => t.notes.length)")
    confere(sorted(n for _, n in volta) == sorted(usadas) and 'voice' in [n for n, _ in volta],
            f'"Baixar MIDI" grava só as faixas em uso, com o nome limpo ({volta})')
    pg.evaluate("store.del(cfgChave())")

    print('origem')
    pg.click('#libA button[data-vista=transcritas]')
    ia = pg.eval_on_selector_all('#libList button .tag', 'x => x.map(e => e.textContent)')
    confere(ia and all(' · MuScriptor' in t or ' · Mirelo' in t for t in ia),
            f'a vista "transcritas" mostra só as feitas por IA ({sum("MuScriptor" in t for t in ia)} MuScriptor, '
            f'{sum("Mirelo" in t for t in ia)} Mirelo)')
    artistas = pg.eval_on_selector_all('#libF option', 'x => x.map(o => o.textContent)')
    confere(any('AC/DC' in a for a in artistas), f'seletor de artista nas transcritas ({len(artistas) - 1} artistas)')
    pg.click('#libFiltros'); pg.check('#fVoz')
    voz = pg.eval_on_selector_all('#libList button .tag', 'x => x.map(e => e.textContent)')
    confere(voz and all('vocal' in t for t in voz), f'filtro "com voz" no menu ({len(voz)})')
    pg.uncheck('#fVoz'); pg.keyboard.press('Escape')
    confere(pg.is_hidden('#libPop'), 'o menu de filtros fecha com Esc')
    pg.click('#libA button[data-vista=rock]')
    rock = pg.eval_on_selector_all('#libList button .tag', 'x => x.map(e => e.textContent)')
    confere(rock and all(' · nativo' in t for t in rock), f'o rock aparece como MIDI nativo ({len(rock)})')
    cabs = pg.eval_on_selector_all('#libList li.grp', 'x => x.map(e => e.textContent)')
    confere(all(c.startswith(('mais ', 'nada ')) for c in cabs), f'sem cabeçalho de pasta em cima das músicas ({cabs})')
    pg.click('#libA button[data-vista="jogos"]')
    grupos = pg.evaluate("[...document.querySelectorAll('#libF optgroup')].map(g => g.label + ': ' + [...g.children].map(o => o.textContent).join(', '))")
    confere(any(g.startswith('Nintendo: ') and 'Mario' in g for g in grupos), f'nos jogos, o grupo é Nintendo › Mario ({grupos[:3]})')
    pg.click('#libA button[data-vista=""]')

    print('favoritas')
    pg.evaluate("store.del('favoritas'); store.del('soFav')")
    pg.reload(); pg.wait_for_selector('#libList button.fav')
    alvo = pg.eval_on_selector('#libList li.mus:nth-child(3) button[data-path]', 'b => b.dataset.path')
    pg.click('#libList li.mus:nth-child(3) button.fav')
    confere(pg.get_attribute('#libList li.mus:nth-child(3) button.fav', 'aria-pressed') == 'true', 'a estrela marca a música')
    pg.reload(); pg.wait_for_selector('#libList button.fav')
    pg.click('#libFav')
    so = pg.eval_on_selector_all('#libList button[data-path]', 'x => x.map(b => b.dataset.path)')
    confere(so == [alvo], f'a favorita continua marcada depois de recarregar, e o botão mostra só ela ({so})')
    confere('(1)' in pg.text_content('#libFav'), 'o botão conta as favoritas')
    pg.click('#libList button.fav')
    vazio = pg.eval_on_selector_all('#libList li.grp', 'x => x.map(e => e.textContent)')
    confere(vazio and vazio[0].startswith('nada '), f'desmarcada, a lista de favoritas fica vazia e diz como marcar ({vazio})')
    pg.click('#libFav')
    pg.evaluate("store.del('favoritas'); store.del('soFav')")

    print('outros arquivos')
    gp = pg.evaluate("lib.filter(it => it.tipo === 'GP').map(it => it.arquivo)")
    if gp:
        try:
            abrir(pg, base, gp[0])
            confere(estado(pg)['faixas'] > 0, 'Guitar Pro abre: ' + gp[0])
        except Exception:
            print('  (Guitar Pro não abriu: o leitor vem de CDN e precisa de internet)')
    banda = sorted((RAIZ / 'musicas' / 'bandas' / 'AC-DC').glob('*.mid'))
    if banda:
        abrir(pg, base, 'bandas/AC-DC/' + banda[0].name)
        confere(estado(pg)['faixas'] >= 6, f'arranjo de banda: {banda[0].name}')

    if telas:
        destino = Path(tempfile.gettempdir()) / 'flyback-telas'
        destino.mkdir(exist_ok=True)
        abrir(pg, base, 'transcritas/Victor & Leo - Borboletas (Mirelo).mid')
        for w, h in [(1920, 1080), (1366, 768), (1280, 720), (900, 1000)]:
            pg.set_viewport_size({'width': w, 'height': h}); time.sleep(.3)
            larg = pg.evaluate('document.documentElement.scrollWidth')
            confere(larg <= w, f'{w}x{h} sem rolagem horizontal')
            pg.screenshot(path=str(destino / f'{w}x{h}.png'), full_page=w < 1100)
        print(f'  capturas em {destino}')
    confere(not erros, 'nenhum erro no console' + ('' if not erros else ': ' + '; '.join(erros[:3])))
    pg.close()


def serial(nav, base):
    print('serial, com porta simulada')
    pg = nav.new_page(viewport={'width': 1600, 'height': 1000})
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.add_init_script(SERIAL_FALSA)
    pg.goto(base)
    pg.evaluate("localStorage.clear(); localStorage.setItem('flyback:esp', JSON.stringify({n: 6}))")
    abrir(pg, base, 'exemplos/Korobeiniki.mid')
    linhas = lambda: pg.evaluate('window.__serial.bytes').splitlines()
    confere(pg.is_disabled('#pinos button'), '"testar" desabilitado antes de conectar')
    confere(pg.is_visible('#via') and pg.input_value('#via') == 'usb' and pg.is_visible('#baud'), 'sem nada salvo, conecta pela USB, com a velocidade à mostra')
    pg.click('#serGo'); time.sleep(.3)
    confere(linhas()[:8] == ['?', 'X', 'P 0 4', 'P 1 5', 'P 2 6', 'P 3 7', 'P 4 15', 'P 5 16'], 'ao conectar: ? (a versão), X e os seis pinos')
    confere('nov/2026' in pg.inner_text('#serMsg') and pg.is_disabled('#via'),
            f'a resposta do ESP mostra a versão do firmware ({pg.inner_text("#serMsg")!r})')
    pg.click('#pinos .pino:nth-child(3) button')
    confere(linhas()[-4:] == ['E 2 4 0 1000 6', 'R', 'N 2 0 440.00', 'F 2 600'], 'testar o canal 3: envelope reto, sem decair')
    pg.select_option('#pinos .pino:nth-child(2) select', '21')
    confere('P 1 21' in linhas()[-6:], 'trocar o pino reenvia o mapa')
    pg.evaluate('window.__serial.bytes = ""')
    pg.click('#play'); time.sleep(1.2); pg.click('#play'); time.sleep(.2)
    l = linhas()
    t = [int(x.split()[2]) for x in l if x.startswith('N ')]
    envs = [x for x in l if x.startswith('E ')]
    confere(l[:6] == ['P 0 4', 'P 1 21', 'P 2 6', 'P 3 7', 'P 4 15', 'P 5 16'] and l[6:13] == envs + ['R']
            and l[-1] == 'X' and len(t) > 5 and t == sorted(t),
            f'tocar: o mapa de pinos de novo, o envelope de cada canal, R, {len(t)} notas em ordem, X')
    forcas = [x.split() for x in l if x.startswith('N ')]
    confere(not pg.is_checked('#envArco') and all(e.endswith(' 4 0 1000 6') for e in envs) and all(x[4] == '1000' for x in forcas),
            f'"envelope no arco" desligado (o padrão): nota reta e no máximo ({envs[:1]}, {forcas[0]})')
    pg.check('#envArco')
    pg.evaluate('window.__serial.bytes = ""')
    pg.click('#play'); time.sleep(1.2); pg.click('#play'); time.sleep(.2)
    l = linhas()
    envs = [x for x in l if x.startswith('E ')]
    env_js = pg.evaluate("[0,1,2,3,4,5].map(c => { const e = envOf(c); return 'E ' + c + ' 4 ' + (e ? Math.round(e.tau * 1000) : 0) + ' ' + (e ? Math.round(e.sus * 1000) : 1000) + ' 6'; })")
    confere(envs == env_js, f'o "E" de cada canal é o envelope do mixer ({envs[:2]})')
    forcas = [x.split() for x in l if x.startswith('N ')]
    confere(all(len(x) == 5 and 250 <= int(x[4]) <= 1000 for x in forcas), f'cada "N" leva a força, de 250 a 1000 ‰ ({forcas[0]})')
    pg.evaluate('window.__serial.bytes = ""')
    pg.select_option('#espN', '2')
    l = linhas()
    confere('P 1 21' in l and 'P 2 -1' in l, 'com dois flybacks o mapa vai com os outros quatro canais liberados')
    pg.click('#play'); time.sleep(.6); pg.click('#play')
    canais = {int(x.split()[1]) for x in linhas() if x.startswith('N ')}
    confere(canais and canais <= {0, 1}, f'com dois flybacks a serial continua, só nos canais 0 e 1 ({sorted(canais)})')
    pg.click('#serGo'); time.sleep(.2)
    confere(pg.evaluate('window.__serial.fechada'), 'desconectar fecha a porta')
    # o ESP parado no modo de gravação: a porta abre, mas ninguém responde ao "?"
    pg.evaluate('window.__serial.mudo = true')
    pg.click('#serGo'); time.sleep(2.8)
    confere('não respondeu' in pg.inner_text('#serMsg'), f'sem resposta do ESP, a página avisa ({pg.inner_text("#serMsg")!r})')
    pg.click('#serGo'); time.sleep(.2)
    confere(not erros, 'nenhum erro na página')
    pg.close()


def bluetooth(nav, base):
    print('Bluetooth (BLE), com ESP simulado')
    pg = nav.new_page(viewport={'width': 1600, 'height': 1000})
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.add_init_script(BLE_FALSO)
    pg.goto(base)
    pg.evaluate("localStorage.clear(); localStorage.setItem('flyback:esp', JSON.stringify({n: 6}))")
    abrir(pg, base, 'exemplos/Korobeiniki.mid')
    linhas = lambda: pg.evaluate('window.__ble.bytes').splitlines()
    pg.select_option('#via', 'ble')
    confere(not pg.is_visible('#baud') and pg.evaluate("JSON.parse(localStorage.getItem('flyback:esp')).via") == 'ble',
            'escolher Bluetooth esconde a velocidade e fica lembrado')
    pg.click('#serGo'); time.sleep(.6)
    f = pg.evaluate('window.__ble.filtros')
    confere(any('6e400001-b5a3-f393-e0a9-e50e24dcca9e' in (x.get('services') or []) for x in f['filters']),
            'procura o serviço UART da Nordic')
    confere(linhas()[:8] == ['?', 'X', 'P 0 4', 'P 1 5', 'P 2 6', 'P 3 7', 'P 4 15', 'P 5 16'], 'ao conectar: ?, X e os seis pinos, pelo Bluetooth')
    confere('Bluetooth · Flyback ESP32 · nov/2026' in pg.inner_text('#serMsg'), f'o estado diz Bluetooth, o nome e a versão ({pg.inner_text("#serMsg")!r})')
    pg.click('#pinos .pino:nth-child(2) button'); time.sleep(.3)
    confere(linhas()[-4:] == ['E 1 4 0 1000 6', 'R', 'N 1 0 440.00', 'F 1 600'], '"testar" funciona pelo Bluetooth')
    pg.click('#play'); time.sleep(1.5); pg.click('#play'); time.sleep(.4)
    l = linhas()
    t = [int(x.split()[2]) for x in l if x.startswith('N ') and x != 'N 1 0 440.00']
    confere(len(t) > 5 and t == sorted(t) and l[-1] == 'X', f'tocar: {len(t)} notas em ordem, inteiras, e X no fim')
    b = pg.evaluate('window.__ble')
    confere(b['maxNoAr'] == 1, f'uma escrita por vez ({b["maxNoAr"]} no ar ao mesmo tempo)')
    confere(b['grande'] == 0 and max(b['escritas'][:3]) <= 20 and max(b['escritas']) > 20,
            f'pedaços de 20 bytes até o ESP dizer o MTU, maiores depois (maior: {max(b["escritas"])})')
    pg.evaluate('window.__ble.cair()'); time.sleep(.2)
    confere(pg.inner_text('#serMsg') == 'o Bluetooth caiu' and pg.inner_text('#serGo') == 'Conectar' and not pg.is_disabled('#via'),
            'a queda do Bluetooth aparece, e dá para conectar de novo')
    confere(not erros, f'nenhum erro na página {erros[:2]}')
    # o gerador de tom herda a escolha do player (flyback:esp) e manda o "D" pelo Bluetooth
    pg.goto(base + 'tom.html')
    pg.click('#modoEsp')
    confere(pg.input_value('#via') == 'ble' and not pg.is_visible('#baud'), 'o gerador de tom herda o Bluetooth escolhido no player')
    pg.click('#serGo'); time.sleep(.5)
    pg.evaluate("ch[0].ganho = 100; mostrarTudo()")
    pg.click('#play'); time.sleep(1.3); pg.click('#play'); time.sleep(.3)
    l = linhas()
    confere(l[:2] == ['?', 'X'] and 'P 0 4' in l and l.count('D 0 500 440.00') >= 2 and l[-1] == 'D 0 0 440.00',
            f'gerador de tom pelo Bluetooth: pino, o "D" repetido e fração 0 ao parar ({l.count("D 0 500 440.00")} D)')
    confere('Bluetooth · Flyback ESP32 · nov/2026' in pg.inner_text('#serMsg'), 'e mostra a versão do firmware')
    confere(not erros, f'nenhum erro no gerador de tom {erros[:2]}')
    pg.close()


def tom(nav, base):
    print('gerador de tom pelo ESP (V3.6), com porta simulada')
    pg = nav.new_page(viewport={'width': 1300, 'height': 900})
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.add_init_script(SERIAL_FALSA)
    linhas = lambda: [x for x in pg.evaluate('window.__serial.bytes').splitlines() if x != '?']
    # sem nada salvo, os pinos padrão do player: o tom saía no GPIO 18 e a música no 4
    pg.goto(base + 'tom.html'); pg.evaluate('localStorage.clear()'); pg.goto(base + 'tom.html')
    pg.click('#modoEsp'); pg.click('#serGo'); time.sleep(.3)
    confere(linhas()[1:7] == ['P 0 4', 'P 1 -1', 'P 2 -1', 'P 3 -1', 'P 4 -1', 'P 5 -1'],
            f'sem painel salvo, o pino padrão do player, e os outros canais livres — nada nos GPIO 6 e 7, que num '
            f'ESP32 comum são da flash ({linhas()[1:4]})')
    pg.select_option('#placa', 'esp32'); time.sleep(.2)
    confere('P 0 18' in linhas()[-8:] and pg.evaluate("JSON.parse(localStorage.getItem('flyback:esp')).placa") == 'esp32',
            'trocar a placa manda o pino padrão dela e fica salvo para o player')
    pg.select_option('#gpio', '13'); time.sleep(.2)
    confere('P 0 13' in linhas()[-8:] and pg.inner_text('#chipA') == 'GPIO 13', 'o pino se escolhe junto da frequência')
    pg.click('#serGo'); time.sleep(.2)
    pg.evaluate("localStorage.clear(); localStorage.setItem('flyback:esp', JSON.stringify({placa: 'esp32', pinos: [18, 19, 21, 22, 23, 25]}))")
    pg.goto(base + 'tom.html')
    pg.click('#modoEsp'); pg.click('#serGo'); time.sleep(.3)
    confere(linhas()[:7] == ['X', 'P 0 18', 'P 1 -1', 'P 2 -1', 'P 3 -1', 'P 4 -1', 'P 5 -1'],
            'ao conectar: X e o pino do canal 1 do player; os outros livres')
    pg.evaluate("ch[0].ganho = 100; mostrarTudo()")
    pg.click('#play'); time.sleep(1.3)
    d = [x for x in linhas() if x == 'D 0 500 440.00']
    confere(len(d) >= 3, f'tocando, o "D" do canal se repete a cada 500 ms, com fração 50% no volume máximo ({len(d)})')
    confere(pg.evaluate('ch[0].gn.gain.value') == 0 and not pg.is_visible('#w0'),
            'pelo ESP o áudio do computador fica mudo e a forma de onda some: é sempre quadrada')
    caixa = lambda sel: pg.locator(sel).bounding_box()
    confere(not pg.is_visible('#on1') and not pg.is_visible('#g1') and caixa('#cv')['x'] > caixa('#gpio')['x'] + caixa('#gpio')['width'],
            'pelo ESP um canal só: a saída e os controles à esquerda, o osciloscópio à direita')
    pg.select_option('#gpio', '21'); time.sleep(.2)
    # pelo índice, e não pela posição no fim: o "D" de manutenção (a cada 500 ms) pode cair depois
    l = linhas()
    i = len(l) - 1 - l[::-1].index('P 0 21') if 'P 0 21' in l else -1
    confere(i >= 0 and l[i + 1:i + 7] == ['P 1 -1', 'P 2 -1', 'P 3 -1', 'P 4 -1', 'P 5 -1', 'D 0 500 440.00']
            and l[-1] == 'D 0 500 440.00',
            f'trocar o pino muda o canal de GPIO (o firmware apaga o antigo) e o tom segue ({l[-8:]})')
    pg.click('#play'); time.sleep(.3)
    confere(linhas()[-1] == 'D 0 0 440.00', 'parar manda fração 0')
    confere(caixa('#play')['y'] > caixa('#cv')['y'] + caixa('#cv')['height'] and caixa('#g0')['x'] > caixa('#play')['x'],
            'o play e o volume ficam logo abaixo do osciloscópio')
    pg.click('#modoAudio'); time.sleep(.2)
    confere(linhas()[-1] == 'X', 'voltar ao áudio silencia o ESP')
    pg.click('#w1 [data-onda="sawtooth"]')
    confere(pg.evaluate('ch[1].onda') == 'sawtooth' and pg.get_attribute('#w1 [data-onda="sawtooth"]', 'aria-pressed') == 'true'
            and pg.is_visible('#g1'), 'no áudio, a forma de onda é um botão por forma, e os dois volumes aparecem')
    confere(not erros, 'nenhum erro na página')
    pg.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--telas', action='store_true', help='guardar capturas de tela')
    args = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit('precisa do playwright:  pip install playwright')
    if not (RAIZ / 'musicas' / 'index.json').is_file():
        sys.exit('falta musicas/index.json — rode antes:  python tools/gerar_acervo.py')
    srv, base = servir()
    try:
        with sync_playwright() as p:
            nav = None
            for canal in ('chrome', 'msedge'):
                try:
                    nav = p.chromium.launch(channel=canal, headless=True, args=['--autoplay-policy=no-user-gesture-required'])
                    break
                except Exception:
                    continue
            if not nav:
                sys.exit('não achei Chrome nem Edge instalados')
            player(nav, base, args.telas)
            serial(nav, base)
            bluetooth(nav, base)
            tom(nav, base)
            nav.close()
    finally:
        srv.shutdown()
    print('\n' + ('tudo certo' if not falhas else f'{len(falhas)} falha(s):\n  ' + '\n  '.join(falhas)))
    sys.exit(1 if falhas else 0)


if __name__ == '__main__':
    if os.name == 'nt':
        sys.stdout.reconfigure(encoding='utf-8')
    main()
