#!/usr/bin/env python3
"""Temas que todo mundo reconhece — jogos, desenhos, filmes, Brasil — para musicas/temas.

    python tools/baixar_temas.py               # mede os candidatos e lista a escolha, sem gravar
    python tools/baixar_temas.py --baixar      # grava a escolha no acervo, com crédito
    python tools/baixar_temas.py --so Nintendo # só o que tiver isto na pasta ou no título
    python tools/baixar_temas.py --navegador   # abre no navegador o que só se baixa à mão

Por que existe: o dono do projeto pediu música "marcante" (Undertale, a abertura de Gravity
Falls, o Top Gun do NES, o tema do Senna), e o acervo de bandas tem artista que ninguém conhece.
Aqui a lista é escrita à mão, em TEMAS, e para cada tema a ferramenta busca as versões em até
três fontes, mede cada uma e fica com a melhor para dois flybacks:

  vgmusic   https://www.vgmusic.com/   MIDIs de jogo sequenciados à mão, uma página por
            plataforma, com o nome de quem sequenciou. Música de NES e de Game Boy é feita de
            duas ondas quadradas e um triângulo: cabe inteira em dois flybacks. SNES, Mega
            Drive, N64 e PC têm 8 vozes ou mais, e ficam para a montagem de seis.
  pdmx      partituras do MuseScore marcadas como domínio público ou CC0 (o catálogo e os MIDIs
            ficam em ~/pdmx, os mesmos do baixar_pdmx.py).
  lakh      o acervo Lakh, pelo rawl.rocks, o mesmo das bandas: tem alguns temas de filme e TV.

O BitMidi tem muito tema de TV, mas o robots.txt dele proíbe robôs na pasta dos arquivos
(/uploads/), então dele a ferramenta não baixa nada: com --navegador ela abre a página no
navegador, o dono do projeto clica em baixar, e o arquivo que cair em Downloads vai para o acervo
com o crédito. A confirmação continua vindo de uma pessoa.

A medida é a do curar_acervo: quanto da música sobrevive em dois canais monofônicos
(aproveitamento) e em seis (aproveitamento_n). Arquivo de uma parte só perde para um de várias,
porque não há o que pôr no segundo flyback.

Os temas são obras protegidas, em transcrições de fã: valem as regras de crédito do
USO-EDUCACIONAL.md, como as bandas. Os downloads ficam em ~/.cache/flyback-temas, e a varredura
espera PAUSA segundos entre chamadas, com identificação no User-Agent.

Só usa a biblioteca padrão, mais o pandas para ler o catálogo do PDMX.
"""
import argparse
import html
import json
import re
import sys
import tarfile
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'tools'))
from curar_acervo import ler_midi, aproveitamento, aproveitamento_n  # noqa: E402

DESTINO = RAIZ / 'musicas' / 'temas'
CACHE = Path.home() / '.cache' / 'flyback-temas'
PDMX = Path.home() / 'pdmx'
UA = 'flyback-midi/1.0 (https://github.com/joaohauch/flyback-midi) python-urllib'
PAUSA = 1.0
VGM = 'https://www.vgmusic.com/music/'
PLATAFORMA = {
    'nes': 'console/nintendo/nes', 'snes': 'console/nintendo/snes', 'gameboy': 'console/nintendo/gameboy',
    'n64': 'console/nintendo/n64', 'genesis': 'console/sega/genesis', 'ps1': 'console/sony/ps1',
    'windows': 'computer/microsoft/windows', 'arcade': 'other/miscellaneous/arcade',
}
LAKH_INDEX = 'https://rawl.rocks/lakh-index.json'
LAKH_DADOS = 'https://rawl.rocks/lakh-data'
CREDITO_PDMX = 'via PDMX (Long et al., 2024, CC BY 4.0)'
LICENCA = 'obra protegida — uso educacional sem fins lucrativos'


def V(plataforma, jogo, faixa):
    return ('vgmusic', plataforma, jogo, faixa)


def P(titulo):
    return ('pdmx', titulo)


def L(artista, arquivo):
    return ('lakh', artista, arquivo)


def B(slug):
    """Página do BitMidi: só pelo navegador, com o clique do dono do projeto (ver --navegador)."""
    return ('bitmidi', slug)


# Remix, medley, mistura de músicas e arranjo para outro instrumento não são o tema que se
# reconhece: na primeira rodada, a melhor nota de Super Mario era "Overworld (Night Court Remix)"
# e a de Arquivo X, "X-Files lateralus".
RX_FORA = re.compile(r'remix|medley|mash.?up|lateralus|mmadd|composition project|\bcover\b|'
                     r'arrangement|\barr\.|violin part|for (tuba|trombone|clarinet|accordion)', re.I)
DUR_MAX = 6.5 * 60


# (pasta dentro de musicas/temas, título, quem compôs, fontes[, extras do crédito]). A pasta é a
# hierarquia que o site mostra: jogos/<empresa>/<franquia>, filmes e séries/<Filmes|Séries e TV|
# Desenhos e animes>. O título diz de onde é a música, porque a lista não mostra mais a pasta.
# O Hino Nacional e Brasileirinho saíram daqui em 25/nov/2026: estão em classicos e em bandas.
TEMAS = [
    # --- jogos
    # Five Nights at Freddy's (pedido do dono do projeto, 26/nov/2026): a música mais famosa é a da
    # The Living Tombstone, canção de fã que virou o tema da série; mais as outras dela e a caixinha
    # de música do Freddy no jogo, que é a Marcha do Toreador, da Carmen de Bizet
    ("jogos/Scott Cawthon/Five Nights at Freddy's", "Five Nights at Freddy's - The Living Tombstone", 'The Living Tombstone',
     [P(r"^five nights at freddy'?s - the living tombstone")]),
    ("jogos/Scott Cawthon/Five Nights at Freddy's", "FNaF 2 - It's Been So Long (The Living Tombstone)", 'The Living Tombstone',
     [P(r"^it'?s been so long")]),
    ("jogos/Scott Cawthon/Five Nights at Freddy's", 'FNaF 4 - I Got No Time (The Living Tombstone)', 'The Living Tombstone',
     [P(r'fnaf 4 i got no time')]),
    ("jogos/Scott Cawthon/Five Nights at Freddy's", 'FNaF - Stay Calm (Griffinilla)', 'Griffinilla',
     [P(r'^stay calm \(fnaf')]),
    ("jogos/Scott Cawthon/Five Nights at Freddy's", "Five Nights at Freddy's - caixinha do Freddy (Marcha do Toreador)", 'Georges Bizet',
     [P(r'^toreador march$')]),
    ('jogos/Toby Fox/Undertale', 'Undertale - Megalovania', 'Toby Fox',
     [('vgmusic', 'windows', '^Undertale$', '^Megalovania'), ('pdmx', 'megalovania')]),
    ('jogos/Toby Fox/Undertale', 'Undertale - Hopes and Dreams', 'Toby Fox',
     [('vgmusic', 'windows', '^Undertale$', '^Hopes and Dreams$')]),
    ('jogos/Toby Fox/Undertale', 'Undertale - Spider Dance', 'Toby Fox',
     [('vgmusic', 'windows', '^Undertale$', '^Spider Dance')]),
    ('jogos/Toby Fox/Undertale', 'Undertale - Bonetrousle', 'Toby Fox',
     [('vgmusic', 'windows', '^Undertale$', '^Bonetrousle')]),
    ('jogos/Toby Fox/Undertale', 'Undertale - Fallen Down', 'Toby Fox',
     [('vgmusic', 'windows', '^Undertale$', '^Fallen Down')]),
    ('jogos/Konami/Top Gun', 'Top Gun (NES) - abertura', 'Konami',
     [('vgmusic', 'nes', '^Top Gun$', 'demo|title')]),
    ('jogos/Konami/Top Gun', 'Top Gun (NES) - reabastecimento', 'Konami',
     [('vgmusic', 'nes', '^Top Gun$', 'fuel')]),
    ('jogos/Nintendo/Mario', 'Super Mario Bros. - tema principal', 'Koji Kondo',
     [('vgmusic', 'nes', '^Super Mario Bros\\.?$', 'overworld|ground|main'), ('pdmx', '^super mario bros\\.? theme')]),
    ('jogos/Nintendo/Mario', 'Super Mario Bros. - subterrâneo', 'Koji Kondo',
     [('vgmusic', 'nes', '^Super Mario Bros\\.?$', 'underground|underworld')]),
    ('jogos/Nintendo/Zelda', 'The Legend of Zelda - tema principal', 'Koji Kondo',
     [('vgmusic', 'nes', '^Legend of Zelda, The$', 'overworld|main|title')]),
    ('jogos/Nintendo/Tetris', 'Tetris - tipo A (Korobeiniki)', 'tradicional russo, arranjo de Hirokazu Tanaka',
     [('vgmusic', 'gameboy', '^Tetris$', 'type.?a|a.?type|music.?a|korobeiniki')], {'categorias': ['jogos', 'clássicas']}),
    ('jogos/Nintendo/Pokémon', 'Pokémon Red e Blue - abertura', 'Junichi Masuda',
     [('vgmusic', 'gameboy', '^Pok.mon \\(Red, Blue, Yellow\\)$', 'opening|title|intro')]),
    ('jogos/Nintendo/Pokémon', 'Pokémon Red e Blue - batalha', 'Junichi Masuda',
     [('vgmusic', 'gameboy', '^Pok.mon \\(Red, Blue, Yellow\\)$', 'battle')]),
    ('jogos/Capcom/Mega Man', 'Mega Man 2 - Dr. Wily, fase 1', 'Takashi Tateishi',
     [('vgmusic', 'nes', '^Mega Man (2|II)$', 'wily.{0,12}(stage )?1\\b|wily.?s castle')]),
    ('jogos/Konami/Castlevania', 'Castlevania - Vampire Killer', 'Kinuyo Yamashita',
     [('vgmusic', 'nes', '^Castlevania$', 'vampire killer|stage 1'), ('pdmx', 'vampire killer')]),
    ('jogos/Konami/Contra', 'Contra - fase da selva', 'Kazuki Muraoka',
     [('vgmusic', 'nes', '^Contra$', 'jungle|stage 1|level 1')]),
    ('jogos/Sega/Sonic', 'Sonic the Hedgehog - Green Hill Zone', 'Masato Nakamura',
     [('vgmusic', 'genesis', '^Sonic the Hedgehog$', 'green hill'), ('pdmx', 'green hill zone')]),
    ('jogos/Capcom/Street Fighter', 'Street Fighter II - tema do Guile', 'Yoko Shimomura',
     [('vgmusic', 'snes', 'Street Fighter II', 'guile'), ('vgmusic', 'arcade', 'Street Fighter II', 'guile'), ('pdmx', "guile'?s theme")]),
    ('jogos/Nintendo/Mario', 'Super Mario 64 - Bob-omb Battlefield', 'Koji Kondo',
     [('vgmusic', 'n64', '^Super Mario 64$', 'bob.?omb|main theme')]),
    ('jogos/Square/Final Fantasy', 'Final Fantasy VII - batalha', 'Nobuo Uematsu',
     [('vgmusic', 'ps1', '^Final Fantasy (7|VII)$', 'fighting|battle')]),
    ('jogos/Square/Chrono Trigger', 'Chrono Trigger - tema principal', 'Yasunori Mitsuda',
     [('vgmusic', 'snes', '^Chrono Trigger$', 'chrono trigger|main theme|title')]),
    ('jogos/Mojang/Minecraft', 'Minecraft - Sweden', 'C418',
     [('pdmx', 'sweden.*minecraft|minecraft.*sweden')]),
    # do histórico do YouTube Music do dono do projeto (25/nov/2026); Elden Ring e Metro Exodus não
    # existem em nenhuma das fontes
    ('jogos/Nintendo/Zelda', 'The Legend of Zelda: Ocarina of Time - Gerudo Valley', 'Koji Kondo',
     [V('n64', r'^Legend of Zelda, The: Ocarina of Time$', r'gerudo'), P(r'gerudo valley')]),
    ('jogos/CD Projekt/The Witcher', 'The Witcher 3 - Hunt or Be Hunted', 'Marcin Przybyłowicz', [B('the-witcher-3-hunt-or-be-hunted-mid')]),
    ('jogos/CD Projekt/The Witcher', 'The Witcher 3 - Ladies of the Woods', 'Marcin Przybyłowicz', [B('the-witcher-3-ladies-of-the-woods-mid')]),
    ('jogos/CD Projekt/The Witcher', 'The Witcher 3 - The Fields of Ard Skellig', 'Marcin Przybyłowicz e Percival', [B('the-witcher-3-the-fields-of-ard-skellig-mid')]),
    ('jogos/CD Projekt/The Witcher', 'The Witcher 3 - Blood and Wine', 'Marcin Przybyłowicz', [P(r'witcher 3 blood and wine')]),
    ('jogos/Bethesda/The Elder Scrolls', 'Skyrim - Dragonborn (tema principal)', 'Jeremy Soule', [P(r'skyrim|dragonborn')]),
    ('jogos/Firaxis/Civilization', 'Civilization IV - Baba Yetu', 'Christopher Tin', [P(r'baba yetu')]),
    # --- filmes e séries
    ('filmes e séries/Desenhos e animes', 'Cowboy Bebop - Tank! (abertura)', 'Yoko Kanno', [P(r'tank!.*cowboy bebop|^tank!')]),
    ('filmes e séries/Desenhos e animes', 'Cowboy Bebop - Too Good Too Bad', 'Yoko Kanno', [P(r'too bad too good|too good too bad')]),
    ('filmes e séries/Desenhos e animes', 'Cowboy Bebop - The Real Folk Blues (encerramento)', 'Yoko Kanno', [P(r'real folk blues')]),
    ('filmes e séries/Desenhos e animes', 'Lupin III - tema', 'Yuji Ohno', [P(r'lupin the third|lupin iii')]),
    ('filmes e séries/Desenhos e animes', 'Princesa Mononoke - The Legend of Ashitaka', 'Joe Hisaishi', [P(r'legend of ashitaka|mononoke')]),
    ('filmes e séries/Desenhos e animes', 'Initial D - Running in the 90s', 'Max Coveri', [P(r"running in the 90'?s")]),
    ('filmes e séries/Desenhos e animes', 'Initial D - Deja Vu', 'Dave Rodgers', [P(r'deja vu')]),
    ('filmes e séries/Séries e TV', 'The Witcher (série) - Toss a Coin to Your Witcher', 'Sonya Belousova e Giona Ostinelli', [P(r'toss a coin')]),
    ('filmes e séries/Filmes', 'Interestelar - Day One', 'Hans Zimmer', [P(r'interstellar')]),
    ('filmes e séries/Desenhos e animes', 'Gravity Falls - abertura', 'Brad Breeck',
     [('pdmx', 'gravity falls theme')]),
    ('filmes e séries/Desenhos e animes', 'Pokémon (anime) - abertura', 'John Siegler e John Loeffler',
     [('pdmx', 'pok.mon (tv show )?theme|indigo league')]),
    ('filmes e séries/Desenhos e animes', 'Os Cavaleiros do Zodíaco - Pegasus Fantasy (abertura)', 'Make-Up (Hiroaki Matsuzawa)',
     [('pdmx', 'pegasus fantasy')]),
    ('filmes e séries/Desenhos e animes', 'Os Simpsons - abertura', 'Danny Elfman',
     [('pdmx', '^the simpsons')]),
    ('filmes e séries/Desenhos e animes', 'A Pantera Cor-de-Rosa - tema', 'Henry Mancini',
     [('pdmx', 'pink panther')]),
    ('filmes e séries/Filmes', 'Missão Impossível - tema', 'Lalo Schifrin',
     [('pdmx', 'mission.? impossible')]),
    ('filmes e séries/Filmes', "Piratas do Caribe - He's a Pirate", 'Klaus Badelt e Hans Zimmer',
     [('pdmx', "he'?s a pirate|pirates of the caribbean")]),
    ('filmes e séries/Filmes', 'Jurassic Park - tema', 'John Williams',
     [('pdmx', 'jurassic park')]),
    ('filmes e séries/Filmes', 'Star Wars - tema principal', 'John Williams',
     [('pdmx', 'star wars (main )?theme|^star wars$')]),
    ('filmes e séries/Séries e TV', 'Game of Thrones - abertura', 'Ramin Djawadi',
     [('pdmx', 'game of thrones (main )?theme|^game of thrones$')]),
    ('filmes e séries/Filmes', 'Rocky - Gonna Fly Now', 'Bill Conti',
     [('pdmx', 'gonna fly now|rocky theme')]),
    ('filmes e séries/Filmes', 'Os Caça-Fantasmas - Ghostbusters', 'Ray Parker Jr.',
     [('lakh', '^Ray Parker Jr', 'ghostbusters'), ('pdmx', '^ghostbusters')]),
    ('filmes e séries/Filmes', 'Um Tira da Pesada - Axel F', 'Harold Faltermeyer',
     [('lakh', '^Harold Faltermeyer$', 'axel f'), ('pdmx', 'axel f')]),
    ('filmes e séries/Séries e TV', 'Arquivo X - abertura', 'Mark Snow',
     [('lakh', '^Television Theme Songs$', 'x-files'), ('pdmx', 'x.?files')]),
    ('filmes e séries/Séries e TV', 'Miami Vice - tema', 'Jan Hammer',
     [('lakh', '^Jan Hammer$', 'miami vice')]),
    ('filmes e séries/Filmes', '1492, A Conquista do Paraíso - Conquest of Paradise', 'Vangelis',
     [('lakh', '^Vangelis$', '1492')]),
    ('filmes e séries/Filmes', 'O Poderoso Chefão - tema', 'Nino Rota',
     [('lakh', '^101 Strings$', 'godfather'), ('pdmx', 'godfather')]),
    ('filmes e séries/Séries e TV', 'Fórmula 1 - Tema da Vitória (Ayrton Senna)', 'Eduardo Souto Neto',
     [('bitmidi', 'senna-mid')]),
]


def nfc(s):
    return unicodedata.normalize('NFC', s)


def abrir(url, binario=False):
    """Uma chamada, com cache em disco e PAUSA antes de ir à rede."""
    alvo = CACHE / urllib.parse.quote(url, safe='')[:180]
    if alvo.is_file() and alvo.stat().st_size:
        dados = alvo.read_bytes()
    else:
        time.sleep(PAUSA)
        p = urllib.parse.urlsplit(url)
        url = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path, safe='/%'), p.query, ''))
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=40) as r:
            dados = r.read()
        CACHE.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)
    return dados if binario else dados.decode('utf-8', 'replace')


# ------------------------------------------------------------------ fontes
_vgm = {}
RX_LINHA = re.compile(r'<td class="header" colspan="5">(?P<jogo>[^<]*)</td>|'
                      r'<td><a href="(?P<arq>[^"]+\.mid)">(?P<titulo>[^<]*)</a>\s*'
                      r'<td align="right">[^<]*\s*<td align="center">(?P<autor>[^<]*)', re.I)


def vgmusic(plataforma):
    """[(jogo, título, url, quem sequenciou)] de uma página de plataforma do VGMusic."""
    if plataforma not in _vgm:
        base = VGM + PLATAFORMA[plataforma] + '/'
        jogo, itens = '', []
        for m in RX_LINHA.finditer(abrir(base)):
            if m.group('jogo') is not None:
                jogo = html.unescape(m.group('jogo')).strip()
            else:
                itens.append((jogo, html.unescape(m.group('titulo')).strip(), base + m.group('arq'),
                              html.unescape(m.group('autor')).strip()))
        _vgm[plataforma] = itens
    return _vgm[plataforma]


_pdmx = None


def pdmx():
    global _pdmx
    if _pdmx is None:
        import pandas as pd
        d = pd.read_csv(PDMX / 'PDMX.csv', low_memory=False,
                        usecols=['metadata', 'mid', 'title', 'n_favorites', 'n_tracks', 'license',
                                 'license_conflict', 'is_draft', 'song_length.seconds'])
        _pdmx = d[d['mid'].notna() & (d.license_conflict != True) & (d.is_draft != True)  # noqa: E712
                  & (d['song_length.seconds'] > 40)]
    return _pdmx


_lakh = None


def lakh():
    global _lakh
    if _lakh is None:
        _lakh = json.loads(abrir(LAKH_INDEX)).get('artists', [])
    return _lakh


def candidatos(fontes):
    """Cada candidato: dict com fonte, rótulo, como pegar os bytes e o crédito de quem fez."""
    out = []
    for f in fontes:
        if f[0] == 'vgmusic':
            _, plat, rj, rf = f
            for jogo, titulo, url, autor in vgmusic(plat):
                if re.search(rj, jogo, re.I) and re.search(rf, titulo, re.I):
                    out.append(dict(fonte='vgmusic', rotulo=f'{plat} · {jogo} · {titulo}', url=url,
                                    quem=autor or 'autor não identificado', plataforma=plat))
        elif f[0] == 'pdmx':
            d = pdmx()
            m = d[d.title.fillna('').str.contains(f[1], case=False, regex=True)]
            for _, r in m.sort_values('n_favorites', ascending=False).head(6).iterrows():
                out.append(dict(fonte='pdmx', rotulo=f'MuseScore · {r.title}', mid=r['mid'], meta=r['metadata'],
                                licenca_edicao='CC0' if r.license == 'cc-zero' else 'domínio público'))
        elif f[0] == 'bitmidi':
            continue                               # só pelo navegador
        elif f[0] == 'lakh':
            for a in lakh():
                if re.search(f[1], a['name'], re.I):
                    for arq in a['tracks']:
                        if re.search(f[2], arq, re.I):
                            out.append(dict(fonte='lakh', rotulo=f"Lakh · {a['name']} · {arq}",
                                            url=f"{LAKH_DADOS}/{urllib.parse.quote(a['name'])}/{urllib.parse.quote(arq)}",
                                            quem='autor não identificado, publicada em rawl.rocks'))
    return out


def do_tar(arq, caminhos):
    quer = {c.lstrip('./'): c for c in caminhos}
    achou = {}
    if not quer:
        return achou
    with tarfile.open(arq) as t:
        for m in t:
            c = quer.get(m.name.lstrip('./'))
            if c:
                achou[c] = t.extractfile(m).read()
                if len(achou) == len(quer):
                    break
    return achou


def medir(dados):
    faixas = ler_midi(dados)
    fins = [t1 for f in faixas for _, t1, _ in f.notas]
    dur = (max(fins) if fins else 0) + .3
    partes = sum(1 for f in faixas if f.notas)
    return dict(partes=partes, dur=dur, ap2=aproveitamento(faixas, dur), ap6=aproveitamento_n(faixas, dur, 6))


def nota(m):
    """Para dois flybacks: o aproveitamento, com arquivo de uma parte só valendo menos."""
    return m['ap2'] * (.6 if m['partes'] < 2 else 1)


def tema_fontes(pasta, titulo):
    return next((t[3] for t in TEMAS if t[0] == pasta and t[1] == titulo), [])


def extras(t):
    return t[4] if len(t) > 4 else {}


def downloads():
    for p in (Path.home() / 'Downloads', Path.home() / 'Transferências'):
        if p.is_dir():
            return p
    return Path.home() / 'Downloads'


def pelo_navegador(temas, espera=180):
    """Abre a página de cada tema no navegador e espera o dono do projeto clicar em baixar.

    O site proíbe robôs na pasta dos arquivos, então quem baixa é a pessoa; daqui só se abre a
    página e se lê a pasta de Downloads. O arquivo novo que aparecer lá (.mid, .midi, .kar) vai
    para o acervo, com o crédito. O original fica em Downloads; salvo direto na pasta de temas,
    ele é movido para o lugar certo."""
    import webbrowser
    baixados = downloads()
    arq_cred = DESTINO / 'creditos.json'
    cred = json.loads(arq_cred.read_text(encoding='utf-8')) if arq_cred.is_file() else {}
    for t in temas:
        pasta, titulo, compositor, fontes = t[:4]
        for f in fontes:
            if f[0] != 'bitmidi':
                continue
            rel = nfc(f'{pasta}/{nome_arquivo(titulo)}.mid')
            if (DESTINO / rel).is_file():
                print(f'   {titulo}: já está no acervo')
                continue
            pagina = f'https://bitmidi.com/{f[1]}'
            # o navegador pode perguntar onde salvar: além de Downloads, olha musicas/ e a pasta de temas
            pastas = [baixados, DESTINO.parent, DESTINO] + [x for x in DESTINO.rglob('*') if x.is_dir()]
            antes = {x for q in pastas if q.is_dir() for x in q.iterdir()}
            inicio = time.time()
            print(f'   {titulo}: abri {pagina} — clique em baixar (espero {espera} s, em {baixados})', flush=True)
            webbrowser.open(pagina)
            novo = None
            while time.time() - inicio < espera and not novo:
                time.sleep(1)
                for x in (y for q in pastas if q.is_dir() for y in q.iterdir()):
                    if x not in antes and x.suffix.lower() in ('.mid', '.midi', '.kar') and x.stat().st_size:
                        novo = x
                        break
            if not novo:
                print('     nada chegou; fica para a próxima')
                continue
            time.sleep(1)                          # o navegador termina de gravar
            dados = novo.read_bytes()
            m = medir(dados)
            alvo = DESTINO / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(dados)
            if novo.resolve().is_relative_to(DESTINO.resolve()) and novo.resolve() != alvo.resolve():
                novo.unlink()                      # salvo direto no acervo: fica só no lugar certo
            cred[rel] = {'autor': compositor, 'artista': compositor, 'licenca': LICENCA, **extras(t),
                         'credito': f'composição de {compositor}; transcrição MIDI de autor não identificado, publicada no BitMidi',
                         'transcricao': 'autor não identificado, publicada no BitMidi', 'fonte': pagina,
                         'aproveitamento': round(m['ap2'] * 100), 'aproveitamento6': round(m['ap6'] * 100)}
            arq_cred.write_text(json.dumps(cred, ensure_ascii=False, indent=1), encoding='utf-8')
            print(f'     {novo.name} -> temas/{rel} ({m["partes"]} partes, 2 flybacks {m["ap2"] * 100:.0f}%)')


def nome_arquivo(s):
    return re.sub(r'\s{2,}', ' ', re.sub(r'[\\/:*?"<>|]', '-', s)).strip(' .')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--baixar', action='store_true', help='grava a escolha em musicas/temas, com crédito')
    ap.add_argument('--so', help='só o que tiver este texto na pasta ou no título')
    ap.add_argument('--navegador', action='store_true',
                    help='abre no navegador os temas de site que proíbe robôs; você clica em baixar')
    args = ap.parse_args()

    temas = [t for t in TEMAS if not args.so or args.so.lower() in (t[0] + ' ' + t[1]).lower()]
    if args.navegador:
        pelo_navegador(temas)
        return
    por_tema = []
    for tema in temas:
        try:
            cs = candidatos(tema[3])
        except Exception as e:                     # fonte fora do ar não derruba a lista toda
            print(f'  ! {tema[1]} — {tema[2]}: {e}', file=sys.stderr)
            cs = []
        por_tema.append((tema, cs))

    # os MIDIs do PDMX saem do .tar.gz numa passada só
    tar_mid = do_tar(PDMX / 'mid.tar.gz', [c['mid'] for _, cs in por_tema for c in cs if c['fonte'] == 'pdmx'])
    escolhas = []
    for tema, cs in por_tema:
        medidos = []
        for c in cs:
            if RX_FORA.search(c['rotulo']):
                continue
            try:
                dados = tar_mid.get(c['mid']) if c['fonte'] == 'pdmx' else abrir(c['url'], binario=True)
                if not dados:
                    continue
                m = medir(dados)
                if m['dur'] <= DUR_MAX:
                    medidos.append((nota(m), m, c, dados))
            except Exception as e:
                print(f'  ! {c["rotulo"]}: {e}', file=sys.stderr)
        medidos.sort(key=lambda x: -x[0])
        escolhas.append((tema, medidos))

    cat_ant = None
    for tema, medidos in escolhas:
        pasta, titulo = tema[0], tema[1]
        if pasta != cat_ant:
            print(f'\n== {pasta}')
            cat_ant = pasta
        if not medidos:
            manual = [f for f in tema_fontes(pasta, titulo) if f[0] == 'bitmidi']
            print(f'   {titulo}: ' + ('pelo navegador (--navegador)' if manual else 'NÃO ACHEI'))
            continue
        _, m, c, _ = medidos[0]
        print(f'   {titulo}: {m["partes"]:2d} partes, {m["dur"] / 60:4.1f} min, '
              f'2 flybacks {m["ap2"] * 100:3.0f}%, 6 flybacks {m["ap6"] * 100:3.0f}%  ← {c["rotulo"][:70]}'
              f'  ({len(medidos)} versões)')
    achados = sum(1 for _, ms in escolhas if ms)
    print(f'\n{achados} de {len(escolhas)} temas com versão.')
    if not args.baixar:
        print('Nada foi gravado. Rode com --baixar para valer.')
        return

    metas = do_tar(PDMX / 'metadata.tar.gz', [ms[0][2]['meta'] for _, ms in escolhas if ms and ms[0][2]['fonte'] == 'pdmx'])
    arq_cred = DESTINO / 'creditos.json'
    cred = json.loads(arq_cred.read_text(encoding='utf-8')) if arq_cred.is_file() else {}
    for tema, medidos in escolhas:
        if not medidos:
            continue
        pasta, titulo, compositor = tema[:3]
        _, m, c, dados = medidos[0]
        rel = nfc(f'{pasta}/{nome_arquivo(titulo)}.mid')
        alvo = DESTINO / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)
        if c['fonte'] == 'pdmx':
            meta = json.loads(metas.get(c['meta'], b'{}')).get('data', {}).get('score', {})
            usuario = (meta.get('user') or {}).get('name') or 'autor no MuseScore'
            transcricao = f'partitura de {usuario} no MuseScore (edição {c["licenca_edicao"]}); {CREDITO_PDMX}'
            fonte = meta.get('url') or ''
        else:
            transcricao = f'sequenciada por {c["quem"]}' + (' no VGMusic' if c['fonte'] == 'vgmusic' else '')
            fonte = c['url']
        cred[rel] = {
            'autor': compositor,
            'artista': compositor,
            'licenca': LICENCA,
            'credito': f'composição de {compositor}; {transcricao}',
            'transcricao': transcricao,
            **extras(tema),
            'fonte': fonte,
            'aproveitamento': round(m['ap2'] * 100),
            'aproveitamento6': round(m['ap6'] * 100),
        }
    arq_cred.write_text(json.dumps(cred, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'gravados em {DESTINO}')


if __name__ == '__main__':
    main()
